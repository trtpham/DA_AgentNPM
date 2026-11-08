"""D-1: sort the 450 public candidates into review groups A/B/C. The group is never a label.

Host:      py -3.14 -m data.scripts.triage_candidates [--batch N]
           runs this file in a disposable container, 18 candidates per batch, resumable.
Container: for each candidate reads the registry manifest, downloads the tarball, checks the
           npm sha512 integrity, extracts it safely to /tmp (tmpfs) and runs the project's static
           tools (read only). No package script is ever run; nothing is unpacked on the host.

Groups (plan docs/ke-hoach/KE_HOACH_DU_LIEU_400.md, 3.1):
  A  install path has no risky sign: local files only, or a native build (node-gyp, prebuild...)
  B  something a reviewer must read: risky indicators, code fetched from outside, endpoints,
     secret/env -> network flows, obfuscation hints, binaries not in the package
  C  cannot be triaged: download/integrity/archive/manifest problems or unreadable install source
"""

import argparse
import base64
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

# Repository root on the host; inside the container this file is /app/triage.py and ROOT is unused.
_PARENTS = Path(__file__).resolve().parents
ROOT = _PARENTS[2] if len(_PARENTS) > 2 else _PARENTS[0]
METADATA = ROOT / "data" / "review_450" / "metadata_review_450.csv"
OUT_DIR = ROOT / "data" / "review_450" / "triage"
SUMMARY = ROOT / "data" / "review_450" / "triage_450.csv"
BATCH_SIZE = 18
IMAGE = "python:3.12-slim"
HOST = "registry.npmjs.org"
MAX_ARCHIVE = 60 * 1024 * 1024
NATIVE_BUILD = frozenset({"node-gyp", "prebuild-install", "node-pre-gyp", "prebuild", "cmake-js"})
FIELDS = ("package", "version", "group", "reasons", "hooks", "external", "risky", "hosts", "flows",
          "files", "entries", "tarball", "tarball_sha256")


def _download(url: str) -> bytes:
    if urllib.parse.urlsplit(url).hostname != HOST or not url.startswith("https://"):
        raise ValueError("only https://registry.npmjs.org is allowed")
    with urllib.request.urlopen(url, timeout=60) as response:  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        data = response.read(MAX_ARCHIVE + 1)
    if len(data) > MAX_ARCHIVE:
        raise ValueError("archive too large")
    return data


def triage(package_dir: str) -> dict:
    """Static summary and group of one extracted package (reads files only)."""
    from tools.explore import file_stats, inspect_scripts, list_endpoints, trace_flow, trace_requires
    from tools.static import RISK_INDICATORS, LIFECYCLE, external_commands, extract_indicators, read_manifest

    manifest = read_manifest(package_dir)
    if not manifest["ok"]:
        return {"group": "C", "reasons": [f"manifest: {manifest['error'][:100]}"]}
    data = manifest["data"]
    scripts = data["scripts"]["content"]
    hooks = {hook: scripts[hook][:200] for hook in LIFECYCLE if hook in scripts}
    result = {"hooks": hooks, "manifest": f"{data['name']}@{data['version']}"}
    if not hooks and not data["has_binding_gyp"]:
        return {**result, "group": "C", "reasons": ["no install hook in the tarball"]}
    c_reasons, b_reasons = [], []
    external = sorted(external_commands(scripts))
    fetchers = [command for command in external if command not in NATIVE_BUILD]
    if fetchers:
        b_reasons.append("hook runs code from outside the package: " + ", ".join(fetchers))
    # The indicator regexes read JavaScript; shell scripts and inline commands (`env`, `printenv`,
    # `node -e ...`) must be read by a person (found on @ma.vu/virus, labelled suspicious).
    hook_rows = (inspect_scripts(package_dir)["data"] or {}).get("hooks", [])
    commands = [command for hook in hook_rows for command in hook["commands"]]
    # Where a reviewer starts reading: each file a hook runs (with its line count), or the
    # package.json line of a hook whose code is inline.
    entries = []
    for hook in hook_rows:
        files = sorted({file for command in hook["commands"] for file in command["runs_file"]})
        for file in files:
            try:
                count = len((Path(package_dir) / file).read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                count = None
            entries.append({"hook": hook["hook"], "file": file, "lines": count})
        if not files and hook["line"]:
            entries.append({"hook": hook["hook"], "file": "package.json", "line": hook["line"]})
    result["entries"] = entries[:10]
    shell_files = sorted({file for command in commands for file in command["runs_file"]
                          if file.endswith((".sh", ".bash", ".bat", ".cmd", ".ps1"))})
    if shell_files:
        b_reasons.append("shell script on the install path: " + ", ".join(shell_files[:3]))
    if any(command["inline_code"] for command in commands):
        b_reasons.append("inline code in a lifecycle hook")
    if any(command["pipes_to_shell"] for command in commands):
        b_reasons.append("hook pipes output into a shell")
    indicators = extract_indicators(package_dir)
    risky: Counter = Counter()
    if indicators["ok"]:
        risky = Counter(item["type"] for item in indicators["data"]["indicators"] if item["type"] in RISK_INDICATORS)
        for reason in indicators["data"]["incomplete"]:
            (c_reasons if reason.startswith("install source not readable") else b_reasons).append(reason[:120])
    else:
        c_reasons.append(f"indicator scan failed: {indicators['error'][:100]}")
    if risky:
        b_reasons.append("risky indicators: " + ", ".join(f"{kind}={count}" for kind, count in sorted(risky.items())))
    endpoints = list_endpoints(package_dir)
    hosts = sorted({item["host"] for item in (endpoints["data"] or {}).get("endpoints", []) if item["host"]})[:10]
    if hosts:
        b_reasons.append(f"{len(hosts)} endpoint host(s) on the install path")
    traced = trace_requires(package_dir)
    flows, hints = [], []
    for file in (traced["data"] or {}).get("files", [])[:20]:
        if not file.endswith((".js", ".cjs", ".mjs")):
            continue
        for flow in (trace_flow(package_dir, file)["data"] or {}).get("flows", []):
            if flow["source_kind"] in ("secret_file", "env") and flow["sink_kind"] in ("network", "process", "eval"):
                flows.append(f"{file}:{flow['source_line']}->{flow['sink_line']} {flow['source_kind']}->{flow['sink_kind']}")
        stats = file_stats(package_dir, file)["data"] or {}
        if stats.get("obfuscated_hint") or stats.get("minified_hint"):
            hints.append(f"{file}: {', '.join(stats['reasons'])}")
    if flows:
        b_reasons.append(f"{len(flows)} secret/env flow(s) to network/process/eval")
    if hints:
        b_reasons.append("obfuscated or minified install file: " + "; ".join(hints[:3]))
    group = "C" if c_reasons else "B" if b_reasons else "A"
    return {**result, "group": group, "reasons": c_reasons + b_reasons, "external": external,
            "risky": dict(sorted(risky.items())), "hosts": hosts, "flows": flows[:5],
            "files": len(traced["data"]["files"]) if traced["ok"] else None}


def inspect(row: dict, work: Path) -> dict:
    """Container side: download, verify, extract under `work`, triage, clean up."""
    from tools.fetch import _extract

    result = {"package": row["package"], "version": row["version"]}
    try:
        meta = json.loads(_download(row["source_url"]))
        if meta.get("name") != row["package"] or meta.get("version") != row["version"]:
            raise ValueError(f"registry manifest is {meta.get('name')}@{meta.get('version')}")
        tarball = _download(meta["dist"]["tarball"])
        algorithm, digest = meta["dist"]["integrity"].split("-", 1)
        if algorithm != "sha512" or hashlib.sha512(tarball).digest() != base64.b64decode(digest):
            raise ValueError("tarball does not match registry integrity")
        result["tarball_sha256"] = hashlib.sha256(tarball).hexdigest()
        result["tarball"] = meta["dist"]["tarball"]
        shutil.rmtree(work, ignore_errors=True)
        (work / "package").mkdir(parents=True)
        (work / "pkg.tgz").write_bytes(tarball)
        _extract(work / "pkg.tgz", work / "package")
        result.update(triage(str(work / "package")))
        if result.get("manifest") not in (None, f"{row['package']}@{row['version']}"):
            result["group"] = "C"
            result["reasons"] = [f"tarball manifest is {result['manifest']}"] + result["reasons"]
    except Exception as error:  # report and continue with the next candidate
        result.update(group="C", reasons=[f"{type(error).__name__}: {str(error)[:150]}"])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return result


def candidates(metadata: Path = METADATA) -> list[dict]:
    with metadata.open(encoding="utf-8-sig", newline="") as stream:
        return [{"package": row["package"], "version": row["version"], "source_url": row["source_url"]}
                for row in csv.DictReader(stream)]


def container_command() -> list[str]:
    return ["docker", "run", "--rm", "-i", "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=512m",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "1g", "--pids-limit", "64",
            "--user", "10001:10001",
            "--mount", f"type=bind,source={ROOT / 'tools'},target=/app/tools,readonly",
            "--mount", f"type=bind,source={ROOT / 'agent'},target=/app/agent,readonly",
            "--mount", f"type=bind,source={Path(__file__).resolve()},target=/app/triage.py,readonly",
            IMAGE, "python", "-I", "/app/triage.py", "--inside"]


def run_batch(number: int, rows: list[dict], out_dir: Path = OUT_DIR, runner=subprocess.run) -> Path | None:
    """Triage one batch in a fresh container; an existing complete batch file is kept (resume)."""
    output = out_dir / f"batch-{number:02}.jsonl"
    if output.is_file() and len(output.read_text(encoding="utf-8").splitlines()) == len(rows):
        return None
    completed = runner(container_command(), input="\n".join(json.dumps(row) for row in rows),
                       capture_output=True, text=True, encoding="utf-8", timeout=3600, check=False)
    results = [json.loads(line) for line in (completed.stdout or "").splitlines() if line.strip()]
    if completed.returncode or len(results) != len(rows):
        raise RuntimeError(f"batch {number}: container failed or incomplete ({len(results)}/{len(rows)}): "
                           f"{(completed.stderr or '')[-300:]}")
    out_dir.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in results), encoding="utf-8")
    return output


def summarize(out_dir: Path = OUT_DIR, summary: Path = SUMMARY) -> dict:
    items = [json.loads(line) for path in sorted(out_dir.glob("batch-*.jsonl"))
             for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    with summary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for item in items:
            writer.writerow({"package": item["package"], "version": item["version"], "group": item["group"],
                             "reasons": " | ".join(item.get("reasons", [])),
                             "hooks": json.dumps(item.get("hooks", {}), ensure_ascii=False),
                             "external": " ".join(item.get("external", [])),
                             "risky": json.dumps(item.get("risky", {})), "hosts": " ".join(item.get("hosts", [])),
                             "flows": " | ".join(item.get("flows", [])), "files": item.get("files"),
                             "entries": json.dumps(item.get("entries", []), ensure_ascii=False),
                             "tarball": item.get("tarball", ""), "tarball_sha256": item.get("tarball_sha256", "")})
    return {"rows": len(items), "groups": dict(sorted(Counter(item["group"] for item in items).items()))}


def main() -> None:
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Sort public candidates into review groups (never labels)")
    parser.add_argument("--batch", type=int, help="run only this batch (1-based)")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside:
        sys.path.insert(0, "/app")
        for line in sys.stdin:
            if line.strip():
                print(json.dumps(inspect(json.loads(line), Path("/tmp/work")), ensure_ascii=False), flush=True)
        return
    rows = candidates()
    batches = [rows[start:start + BATCH_SIZE] for start in range(0, len(rows), BATCH_SIZE)]
    for number, batch in enumerate(batches, 1):
        if args.batch and number != args.batch:
            continue
        written = run_batch(number, batch)
        print(json.dumps({"batch": number, "status": "done" if written else "skipped"}), flush=True)
    print(json.dumps(summarize(), ensure_ascii=False))


if __name__ == "__main__":
    main()
