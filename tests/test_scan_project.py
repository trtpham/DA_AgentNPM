"""Tests for fast Tier 0-1 prefiltering and isolated project/package scanning CLI."""

import json
from pathlib import Path
import pytest

from experiments import run_batch as batch
from experiments.scan_project import (
    collect_packages_from_project,
    prefilter_packages,
    resolve_package_tier0,
    scan_target,
)


def _no_osv(_name: str, _version: str) -> dict:
    return {"ok": True, "data": {"vulns": [], "malicious": False}, "error": None}


def test_collect_packages_from_lockfile_v3_and_local_hook(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"name": "demo-app", "version": "1.0.0"}', encoding="utf-8")
    (tmp_path / "package-lock.json").write_text(
        json.dumps(
            {
                "name": "demo-app",
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "demo-app", "version": "1.0.0"},
                    "node_modules/chalk": {
                        "version": "5.3.0",
                        "resolved": "https://registry.npmjs.org/chalk/-/chalk-5.3.0.tgz",
                        "integrity": "sha512-clean",
                    },
                    "node_modules/@scope/native-mod": {
                        "version": "1.2.3",
                        "resolved": "https://registry.npmjs.org/@scope/native-mod/-/native-mod-1.2.3.tgz",
                        "integrity": "sha512-hook",
                        "hasInstallScript": True,
                    },
                    "node_modules/chalk/node_modules/hidden-hook": {
                        "version": "0.1.0",
                        "resolved": "https://registry.npmjs.org/hidden-hook/-/hidden-hook-0.1.0.tgz",
                        "integrity": "sha512-local",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    local_mod = tmp_path / "node_modules" / "hidden-hook"
    local_mod.mkdir(parents=True)
    (local_mod / "package.json").write_text(
        json.dumps({"name": "hidden-hook", "version": "0.1.0", "scripts": {"postinstall": "node setup.js"}}),
        encoding="utf-8",
    )

    entries = {item["name"]: item for item in collect_packages_from_project(tmp_path)}
    assert entries["chalk"]["has_hook"] is False
    assert entries["@scope/native-mod"]["has_hook"] is True
    assert entries["hidden-hook"]["has_hook"] is True
    assert entries["hidden-hook"]["hooks"] == ["postinstall"]


def test_collect_packages_fallback_to_package_json(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "app", "dependencies": {"lodash": "^4.17.21"}, "devDependencies": {"esbuild": "0.24.0"}}),
        encoding="utf-8",
    )
    entries = {item["name"]: item for item in collect_packages_from_project(tmp_path)}
    assert entries["lodash"]["version"] == "4.17.21"
    assert entries["lodash"]["has_hook"] is None
    assert entries["esbuild"]["version"] == "0.24.0"


def test_resolve_package_tier0_detects_hooks_and_blocks_bad_host() -> None:
    def fake_fetch(url: str) -> dict:
        if url.endswith("/chalk"):
            return {"dist-tags": {"latest": "5.3.0"}}
        if url.endswith("/5.3.0"):
            return {
                "dist": {"tarball": "https://registry.npmjs.org/chalk/-/chalk-5.3.0.tgz", "integrity": "sha512-abc"},
                "scripts": {"test": "xo"},
            }
        if url.endswith("/1.0.0"):
            return {
                "dist": {"tarball": "https://registry.npmjs.org/evil-pkg/-/evil-pkg-1.0.0.tgz", "integrity": "sha512-xyz"},
                "scripts": {"postinstall": "node install.js"},
            }
        return {"dist": {"tarball": "https://evil.invalid/pkg.tgz"}}

    clean = resolve_package_tier0("chalk", fetch_json=fake_fetch)
    assert clean["version"] == "5.3.0"
    assert clean["has_hook"] is False

    hooked = resolve_package_tier0("evil-pkg@1.0.0", fetch_json=fake_fetch)
    assert hooked["has_hook"] is True
    assert hooked["hooks"] == ["postinstall"]

    with pytest.raises(ValueError):
        resolve_package_tier0("bad-host@2.0.0", fetch_json=fake_fetch)


def test_prefilter_tier0_osv_and_cache(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    entries = [
        {"name": "chalk", "version": "5.3.0", "integrity": "sha512-clean", "has_hook": False, "hooks": []},
        {"name": "known-bad", "version": "1.0.0", "integrity": "sha512-bad", "has_hook": True, "hooks": ["install"]},
        {"name": "new-hook", "version": "2.0.0", "integrity": "sha512-new", "has_hook": True, "hooks": ["postinstall"]},
    ]

    def fake_osv(name: str, _ver: str) -> dict:
        if name == "known-bad":
            return {"ok": True, "data": {"malicious": True, "vulns": [{"id": "MAL-2026-1"}]}, "error": None}
        return _no_osv(name, _ver)

    plan = prefilter_packages(entries, variant="A-LLM-X", cache_dir=cache_dir, osv_fn=fake_osv)
    assert plan["counts"] == {
        "total": 3,
        "tier0_no_hook": 1,
        "tier1_osv_malicious": 1,
        "tier1_cached": 0,
        "tier2_needs_agent": 1,
    }
    assert [row["name"] for row in plan["needs_agent"]] == ["new-hook"]


def test_scan_target_dispatches_only_needs_agent_then_uses_cache(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "package.json").write_text('{"name": "proj", "version": "1.0.0"}', encoding="utf-8")
    (project / "package-lock.json").write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "proj", "version": "1.0.0"},
                    "node_modules/pure-js": {"version": "1.0.0", "integrity": "sha512-pure"},
                    "node_modules/build-tool": {
                        "version": "1.2.0",
                        "resolved": "https://registry.npmjs.org/build-tool/-/build-tool-1.2.0.tgz",
                        "integrity": "sha512-tool",
                        "hasInstallScript": True,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    reports = tmp_path / "reports"
    cache_dir = tmp_path / "cache"
    dispatched: list[list[str]] = []

    def fake_runner(run_id: str, variant: str, rows: list[dict], out_reports: Path) -> dict:
        dispatched.append([f"{r['name']}@{r['version']}" for r in rows])
        run_dir = out_reports / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        for r in rows:
            pkg = f"{r['name']}@{r['version']}"
            (run_dir / batch.result_name(pkg)).write_text(
                json.dumps(
                    {
                        "package": pkg,
                        "status": "ok",
                        "elapsed_s": 4.2,
                        "decision": {"final_label": "benign", "action": "approve", "rule": "R7"},
                    }
                ),
                encoding="utf-8",
            )
        return {"done": len(rows), "skipped": 0, "errors": 0}

    first = scan_target(
        project_dir=project,
        variant="A-LLM-X",
        run_id="scan-test-1",
        reports_dir=reports,
        cache_dir=cache_dir,
        run_agent=True,
        osv_fn=_no_osv,
        runner_fn=fake_runner,
    )
    assert dispatched == [["build-tool@1.2.0"]]
    assert first["counts"]["tier0_no_hook"] == 1
    assert first["counts"]["tier2_needs_agent"] == 1
    by_pkg = {item["package"]: item for item in first["results"]}
    assert by_pkg["build-tool@1.2.0"]["tier"] == "tier2_agent"
    assert by_pkg["build-tool@1.2.0"]["npm_command"] == ["npm", "approve-scripts", "build-tool@1.2.0"]
    assert by_pkg["pure-js@1.0.0"]["npm_command"] == ["npm", "approve-scripts", "pure-js@1.0.0"]

    second = scan_target(
        project_dir=project,
        variant="A-LLM-X",
        run_id="scan-test-2",
        reports_dir=reports,
        cache_dir=cache_dir,
        run_agent=True,
        osv_fn=_no_osv,
        runner_fn=fake_runner,
    )
    # Second run hits Tier 1 cache — container runner is not invoked again.
    assert len(dispatched) == 1
    assert second["counts"]["tier1_cached"] == 1
    assert second["counts"]["tier2_needs_agent"] == 0
