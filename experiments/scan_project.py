"""Fast multi-tier prefilter (Tier 0 hook check, Tier 1 OSV + integrity cache) and CLI wrapper.

Helps bridge experimental batch evaluation to practical project/package scanning:
- Reads `package-lock.json` / `package.json` or ad-hoc `--package` specs outside fixed datasets.
- Tier 0 skips packages guaranteed to have no install hooks in `< 0.1s`.
- Tier 1 checks OSV (`MAL-`) and local integrity cache before spending GPU/container time.
- Tier 2 (with `--scan`) dispatches only remaining hook-bearing packages to `experiments.run_isolated`.
- Always keeps `apply_decision(..., dry_run=True)` and never executes package scripts on the host.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.parse

from experiments import run_batch as batch
from experiments.run_isolated import _get, run as run_isolated
from tools.actions import apply_decision
from tools.intel import NAME, VERSION, osv_lookup
from tools.static import LIFECYCLE, read_manifest

HOOK_SCRIPTS = frozenset(LIFECYCLE)


def _http_json(url: str) -> dict:
    return json.loads(_get(url))


def _node_module_dir(project_dir: Path, name: str, rel_key: str = "") -> Path | None:
    root = (project_dir / "node_modules").resolve()
    candidates = []
    if rel_key and "node_modules/" in rel_key:
        candidates.append((project_dir / Path(*rel_key.split("/"))).resolve())
    candidates.append((root / Path(*name.split("/"))).resolve())
    for candidate in candidates:
        if candidate.is_relative_to(root) and (candidate / "package.json").is_file():
            return candidate
    return None


def _local_hook_info(pkg_dir: Path | None) -> tuple[bool | None, list[str]]:
    if pkg_dir is None:
        return None, []
    manifest = read_manifest(str(pkg_dir))
    if not manifest.get("ok"):
        return None, []
    data = manifest["data"]
    scripts_obj = data.get("scripts") or {}
    scripts = scripts_obj.get("content") if isinstance(scripts_obj, dict) and "content" in scripts_obj else scripts_obj
    scripts = scripts if isinstance(scripts, dict) else {}
    hooks = [name for name in LIFECYCLE if name in scripts]
    has_hook = bool(hooks or data.get("has_binding_gyp"))
    return has_hook, hooks


def _extract_pkg_name(rel_path: str) -> str:
    parts = rel_path.split("node_modules/")
    tail = parts[-1].strip("/")
    return tail


def collect_packages_from_project(project_dir: Path) -> list[dict]:
    """Extract unique resolved packages from `package-lock.json` (or `package.json` fallback)."""
    root = project_dir.resolve()
    lock_path = root / "package-lock.json"
    entries: dict[tuple[str, str], dict] = {}

    def record(name: str, version: str, *, resolved: str = "", integrity: str = "",
               has_hook: bool | None = None, hooks: list[str] | None = None, rel_key: str = "") -> None:
        if not NAME.fullmatch(name) or not VERSION.fullmatch(version):
            return
        key = (name, version)
        existing = entries.get(key)
        local_has, local_hooks = _local_hook_info(_node_module_dir(root, name, rel_key))
        final_hook = local_has if local_has is not None else has_hook
        final_hooks = local_hooks or list(hooks or [])
        if final_hook is True and existing:
            existing["has_hook"] = True
            if final_hooks:
                existing["hooks"] = sorted(set(existing["hooks"]) | set(final_hooks))
        elif existing is None:
            entries[key] = {
                "name": name,
                "version": version,
                "source": resolved,
                "integrity": integrity,
                "has_hook": final_hook,
                "hooks": final_hooks,
            }

    if lock_path.is_file():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        lock_ver = int(lock.get("lockfileVersion") or 1)
        packages = lock.get("packages")
        if isinstance(packages, dict):
            for key, meta in packages.items():
                if not key or "node_modules/" not in key or not isinstance(meta, dict):
                    continue
                if meta.get("link") or meta.get("extraneous"):
                    continue
                pkg_name = str(meta.get("name") or _extract_pkg_name(key))
                ver = str(meta.get("version") or "")
                resolved = str(meta.get("resolved") or "")
                integrity = str(meta.get("integrity") or "")
                has_hook = bool(meta.get("hasInstallScript")) if lock_ver >= 2 else None
                record(pkg_name, ver, resolved=resolved, integrity=integrity, has_hook=has_hook, rel_key=key)
        elif isinstance(lock.get("dependencies"), dict):
            def walk_v1(deps: dict) -> None:
                for pkg_name, meta in deps.items():
                    if not isinstance(meta, dict):
                        continue
                    record(
                        str(pkg_name),
                        str(meta.get("version") or ""),
                        resolved=str(meta.get("resolved") or ""),
                        integrity=str(meta.get("integrity") or ""),
                        has_hook=None,
                    )
                    if isinstance(meta.get("dependencies"), dict):
                        walk_v1(meta["dependencies"])
            walk_v1(lock["dependencies"])
        return sorted(entries.values(), key=lambda item: (item["name"], item["version"]))

    pkg_json = root / "package.json"
    if not pkg_json.is_file():
        raise FileNotFoundError(f"neither package-lock.json nor package.json found in {root}")
    manifest = json.loads(pkg_json.read_text(encoding="utf-8"))
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        for pkg_name, spec in (manifest.get(section) or {}).items():
            ver = str(spec).lstrip("^~=").strip()
            record(str(pkg_name), ver, has_hook=None)
    return sorted(entries.values(), key=lambda item: (item["name"], item["version"]))


def resolve_package_tier0(spec: str, fetch_json=_http_json) -> dict:
    """Resolve `name[@version]` via registry.npmjs.org and detect install hooks without running code."""
    text = (spec or "").strip()
    if not text:
        raise ValueError("package spec cannot be empty")
    if text.startswith("@"):
        name, _, version = text.rpartition("@") if "@" in text[1:] else (text, "", "")
    else:
        name, _, version = text.partition("@")
    if not NAME.fullmatch(name):
        raise ValueError(f"invalid npm package name: {name!r}")
    if version and not VERSION.fullmatch(version):
        raise ValueError(f"invalid npm package version: {version!r}")

    quoted_name = urllib.parse.quote(name, safe="")
    if not version:
        listing = fetch_json(f"https://registry.npmjs.org/{quoted_name}")
        version = str((listing.get("dist-tags") or {}).get("latest") or "")
        if not VERSION.fullmatch(version):
            raise ValueError(f"no valid latest version for {name}")
    meta = fetch_json(f"https://registry.npmjs.org/{quoted_name}/{urllib.parse.quote(version, safe='')}")
    dist = meta.get("dist") or {}
    tarball = str(dist.get("tarball") or "")
    parsed = urllib.parse.urlsplit(tarball)
    if parsed.scheme != "https" or parsed.hostname != "registry.npmjs.org":
        raise ValueError("tarball host not allowed")
    scripts = meta.get("scripts") if isinstance(meta.get("scripts"), dict) else {}
    hooks = [hook for hook in LIFECYCLE if hook in scripts]
    has_hook = bool(hooks or meta.get("gypfile"))
    return {
        "name": name,
        "version": version,
        "source": tarball,
        "integrity": str(dist.get("integrity") or dist.get("shasum") or ""),
        "has_hook": has_hook,
        "hooks": hooks,
    }


def _cache_path(cache_dir: Path, name: str, version: str, integrity: str, variant: str) -> Path:
    digest = hashlib.sha256(f"{name}@{version}|{integrity}|{variant}".encode("utf-8")).hexdigest()[:16]
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", f"{name}_{version}")[:80]
    return cache_dir / f"{slug}__{digest}.json"


def _read_cache(cache_dir: Path | None, row: dict, variant: str) -> dict | None:
    if cache_dir is None:
        return None
    path = _cache_path(cache_dir, row["name"], row["version"], row.get("integrity") or "", variant)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("package") == f"{row['name']}@{row['version']}" and isinstance(data.get("decision"), dict):
            return data
    except (OSError, ValueError):
        return None
    return None


def _write_cache(cache_dir: Path | None, row: dict, variant: str, result: dict) -> None:
    if cache_dir is None or result.get("status") != "ok" or not isinstance(result.get("decision"), dict):
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, row["name"], row["version"], row.get("integrity") or "", variant)
    payload = {
        "package": result.get("package"),
        "integrity": row.get("integrity") or "",
        "variant": variant,
        "decision": result["decision"],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def prefilter_packages(
    entries: list[dict],
    *,
    variant: str = "A-LLM-X",
    cache_dir: Path | None = None,
    osv_fn=osv_lookup,
    check_osv: bool = True,
    osv_all: bool = False,
) -> dict:
    """Apply Tier 0 (lifecycle hook presence) and Tier 1 (OSV + integrity cache) before agent runs."""
    results: list[dict] = []
    needs_agent: list[dict] = []
    counts = {
        "total": len(entries),
        "tier0_no_hook": 0,
        "tier1_osv_malicious": 0,
        "tier1_cached": 0,
        "tier2_needs_agent": 0,
    }

    for entry in entries:
        pkg = f"{entry['name']}@{entry['version']}"
        has_hook = entry.get("has_hook")

        should_check_osv = check_osv and (osv_all or has_hook is not False)
        if should_check_osv:
            osv = osv_fn(entry["name"], entry["version"])
            if osv.get("ok") and (osv.get("data") or {}).get("malicious"):
                counts["tier1_osv_malicious"] += 1
                results.append({
                    "package": pkg,
                    "tier": "tier1_osv_malicious",
                    "has_hook": has_hook,
                    "hooks": entry.get("hooks") or [],
                    "decision": {"final_label": "malicious", "action": "deny", "rule": "OSV_MAL"},
                    "vulns": (osv["data"].get("vulns") or [])[:5],
                })
                continue

        if has_hook is False:
            counts["tier0_no_hook"] += 1
            results.append({
                "package": pkg,
                "tier": "tier0_no_hook",
                "has_hook": False,
                "hooks": [],
                "decision": {"final_label": "benign", "action": "approve", "rule": "TIER0_NO_HOOK"},
            })
            continue

        cached = _read_cache(cache_dir, entry, variant)
        if cached:
            counts["tier1_cached"] += 1
            results.append({
                "package": pkg,
                "tier": "tier1_cached",
                "has_hook": has_hook,
                "hooks": entry.get("hooks") or [],
                "decision": cached["decision"],
            })
            continue

        counts["tier2_needs_agent"] += 1
        needs_agent.append(entry)
        results.append({
            "package": pkg,
            "tier": "tier2_needs_agent",
            "has_hook": has_hook,
            "hooks": entry.get("hooks") or [],
            "decision": None,
        })

    return {"counts": counts, "results": results, "needs_agent": needs_agent}


def scan_target(
    *,
    project_dir: Path | None = None,
    package_specs: list[str] | None = None,
    variant: str = "A-LLM-X",
    run_id: str | None = None,
    reports_dir: Path = Path("reports"),
    cache_dir: Path | None = Path("reports/scan-cache"),
    run_agent: bool = False,
    check_osv: bool = True,
    osv_all: bool = False,
    resolve_fn=resolve_package_tier0,
    osv_fn=osv_lookup,
    runner_fn=run_isolated,
) -> dict:
    """Run Tier 0-1 prefilter and optional Tier 2 isolated agent inspection for real targets."""
    if project_dir is None and not package_specs:
        raise ValueError("specify project_dir or at least one package spec")

    entries: list[dict] = []
    if project_dir is not None:
        entries.extend(collect_packages_from_project(project_dir))
    for spec in package_specs or []:
        entries.append(resolve_fn(spec))

    # Deduplicate merged entries cleanly if both --project and --package name the same version.
    deduped: dict[tuple[str, str], dict] = {}
    for entry in entries:
        deduped[(entry["name"], entry["version"])] = entry
    entries_list = list(deduped.values())

    plan = prefilter_packages(
        entries_list,
        variant=variant,
        cache_dir=cache_dir,
        osv_fn=osv_fn,
        check_osv=check_osv,
        osv_all=osv_all,
    )

    effective_run_id = run_id or f"scan-live-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    agent_stats = None
    if run_agent and plan["needs_agent"]:
        rows = [
            {
                "name": item["name"],
                "version": item["version"],
                "source": item.get("source") or (
                    f"https://registry.npmjs.org/{urllib.parse.quote(item['name'], safe='')}"
                    f"/-/{item['name'].split('/')[-1]}-{item['version']}.tgz"
                ),
            }
            for item in plan["needs_agent"]
        ]
        agent_stats = runner_fn(effective_run_id, variant, rows, reports_dir)
        run_dir = reports_dir / effective_run_id
        by_pkg = {item["package"]: item for item in plan["results"]}
        for item in plan["needs_agent"]:
            pkg = f"{item['name']}@{item['version']}"
            rfile = run_dir / batch.result_name(pkg)
            if rfile.is_file():
                saved = json.loads(rfile.read_text(encoding="utf-8"))
                _write_cache(cache_dir, item, variant, saved)
                if pkg in by_pkg and isinstance(saved.get("decision"), dict):
                    by_pkg[pkg]["tier"] = "tier2_agent"
                    by_pkg[pkg]["status"] = saved.get("status")
                    by_pkg[pkg]["decision"] = saved["decision"]
                    by_pkg[pkg]["elapsed_s"] = saved.get("elapsed_s")

    if project_dir is not None and (project_dir / "package.json").is_file():
        for item in plan["results"]:
            dec = item.get("decision")
            if isinstance(dec, dict) and dec.get("action") in ("approve", "deny"):
                applied = apply_decision(str(project_dir), item["package"], dec, dry_run=True)
                if applied.get("ok"):
                    item["npm_command"] = applied["data"].get("command")

    return {
        "run_id": effective_run_id if run_agent and plan["needs_agent"] else None,
        "variant": variant,
        "counts": plan["counts"],
        "agent_stats": agent_stats,
        "results": plan["results"],
    }


def _format_summary(report: dict) -> str:
    c = report["counts"]
    lines = [
        f"Prefilter ({report['variant']}): total={c['total']} | tier0_no_hook={c['tier0_no_hook']} "
        f"| tier1_osv_malicious={c['tier1_osv_malicious']} | tier1_cached={c['tier1_cached']} "
        f"| tier2_needs_agent={c['tier2_needs_agent']}",
    ]
    if report.get("run_id"):
        lines.append(f"Container run_id: {report['run_id']} (view live at http://127.0.0.1:8765/#run={report['run_id']})")
    for item in report["results"]:
        dec = item.get("decision") or {}
        action = dec.get("action") or "pending_agent"
        rule = dec.get("rule") or ""
        cmd = " ".join(item["npm_command"]) if item.get("npm_command") else ""
        suffix = f" -> `{cmd}` (dry-run)" if cmd else ""
        lines.append(f"- {item['package']}: [{item['tier']}] {action} {rule}{suffix}".rstrip())
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(
        description="Tier 0-1 prefilter and isolated Tier 2 scanner for real projects or npm packages",
    )
    parser.add_argument("--project", type=Path, help="Project directory containing package-lock.json / package.json")
    parser.add_argument("--package", action="append", default=[], help="Public npm package (name or name@version)")
    parser.add_argument("--variant", default="A-LLM-X", help="Agent config variant (default: A-LLM-X)")
    parser.add_argument("--run-id", help="Optional run_id for reports/<run_id> when --scan is enabled")
    parser.add_argument("--reports", type=Path, default=Path("reports"), help="Reports directory (default: reports)")
    parser.add_argument("--cache-dir", type=Path, default=Path("reports/scan-cache"), help="Tier 1 cache directory")
    parser.add_argument("--scan", action="store_true", help="Invoke Tier 2 isolated container agent for uncached hook packages")
    parser.add_argument("--no-osv", action="store_true", help="Skip OSV lookup in Tier 1")
    parser.add_argument("--osv-all", action="store_true", help="Check OSV even for packages without install hooks")
    parser.add_argument("--json", action="store_true", help="Print structured JSON instead of text summary")
    args = parser.parse_args()

    if args.project is None and not args.package:
        parser.error("provide --project <dir> or at least one --package <spec>")

    report = scan_target(
        project_dir=args.project,
        package_specs=args.package,
        variant=args.variant,
        run_id=args.run_id,
        reports_dir=args.reports,
        cache_dir=args.cache_dir,
        run_agent=args.scan,
        check_osv=not args.no_osv,
        osv_all=args.osv_all,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_format_summary(report))


if __name__ == "__main__":
    main()
