"""Phase A of the sandbox ablation (Gate B0 2026-11-09): run each labelled package's install script in the
offline sandbox and record what it did, for `run_isolated --sandbox-results` (A-*-XS configs).

Per package:
1. `docker volume create agentnpm-…` (lives inside Docker's Linux VM, never on the Windows disk);
2. the disposable runner container downloads and safely extracts the source into the volume (pkg/), as
   run_isolated does in tmpfs; no package code runs here;
3. (2026-11-20) sandbox/cache_deps.sh, network on, `npm install --ignore-scripts` of the package only to fill
   npm-cache/ in the volume with its production dependencies; no lifecycle script runs;
4. sandbox/run.py installs it from the volume as a user would (empty project, `npm install --offline <tarball>`):
   --network none, read-only root, cap-drop ALL (+SYS_PTRACE), 256 MB without swap, 64 PIDs, 60 s, fake canaries;
5. the volume is removed. Only a behaviour summary is written (no raw strace, stdout or stderr text).

Gate B0 2026-11-21 (robust batches): preflight checks recorded in sandbox_meta.json; stale agentnpm-* volumes and
agentnpm-sbx-* containers removed first; every result has `script_ran` and `fail_reason`; failures that say
nothing about the package (infra, prepare, not_started) are retried once, and `--retry-failed` reruns them later.

Run malicious samples in the clean Ubuntu VM (docs: sandbox/VM_UBUNTU.md); Docker Desktop is for tests and
benign packages. Same code on both.

    py -3.14 -m experiments.sandbox_batch <run_id> --labels data/labels-v1.csv --split dev
    py -3.14 -m experiments.sandbox_batch <run_id> --labels data/labels-v1.csv --split dev --retry-failed
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

SUMMARY_KEYS = ("returncode", "outcome", "trace_complete", "canary_touched", "behavior", "script_ran", "fail_reason")
# Failures that say nothing about the package: retried, and rerun by --retry-failed.
RETRYABLE = ("infra", "prepare", "not_started")
ATTEMPTS = 2
MIN_FREE_GB = 5


def volume_name(run_id: str, package: str) -> str:
    return "agentnpm-" + hashlib.sha256(f"{run_id}\0{package}".encode()).hexdigest()[:24]


def compact(result: dict) -> dict:
    """What the agent's sandbox step reads (agent.run.run_sandbox_once), without raw untrusted text."""
    data = result.get("data")
    if not data:
        return {"ok": False, "data": None, "error": result.get("error"), "fail_reason": "infra"}
    package_files = ((data.get("by_actor") or {}).get("package") or {}).get("files_outside_package", [])
    summary = {key: data.get(key) for key in SUMMARY_KEYS}
    summary["by_actor"] = {"package": {"files_outside_package": package_files[:50]}}
    return {"ok": bool(result.get("ok")), "data": summary, "error": result.get("error"),
            "fail_reason": data.get("fail_reason")}


def prepare(volume: str, row: dict, docker=subprocess.run) -> dict:
    from experiments.run_isolated import container_command
    from sandbox.run import run_named
    try:
        completed = run_named(container_command(prepare_volume=volume), 900, docker, input=json.dumps({"row": row}),
                              encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "prepare container timed out"}
    lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    if completed.returncode or not lines:
        return {"ok": False, "error": f"prepare container failed: {(completed.stderr or '')[-200:]}"}
    return json.loads(lines[-1])


def cleanup_stale(docker=subprocess.run) -> dict:
    """Remove agentnpm-sbx-* containers and agentnpm-* volumes left by a batch that was killed hard."""
    from sandbox.run import CONTAINER_PREFIX
    removed = {"containers": 0, "volumes": 0}
    listed = docker(["docker", "ps", "-aq", "--filter", f"name={CONTAINER_PREFIX}"], capture_output=True, text=True,
                    timeout=60, check=False)
    for container in (listed.stdout or "").split():
        docker(["docker", "rm", "-f", container], capture_output=True, text=True, timeout=60, check=False)
        removed["containers"] += 1
    listed = docker(["docker", "volume", "ls", "-q", "--filter", "name=agentnpm-"], capture_output=True, text=True,
                    timeout=60, check=False)
    for volume in (listed.stdout or "").split():
        if volume.startswith("agentnpm-"):
            docker(["docker", "volume", "rm", "-f", volume], capture_output=True, text=True, timeout=60, check=False)
            removed["volumes"] += 1
    return removed


def preflight(labels: Path | None, reports: Path, docker=subprocess.run, disk=shutil.disk_usage) -> dict:
    """Checks before a batch, recorded in sandbox_meta.json. Raises SystemExit when the batch cannot run."""
    from experiments.run_isolated import IMAGE as RUNNER_IMAGE
    from sandbox.run import IMAGE as SANDBOX_IMAGE
    info = {"images": {}, "labels_sha256": None, "git_commit": None, "git_dirty": None}
    for image in (SANDBOX_IMAGE, RUNNER_IMAGE):
        found = docker(["docker", "image", "inspect", image, "--format", "{{.Id}}"], capture_output=True, text=True,
                       timeout=60, check=False)
        if found.returncode:
            raise SystemExit(f"preflight: image {image} missing; build it first (sandbox/VM_UBUNTU.md)")
        info["images"][image] = (found.stdout or "").strip()
    reports.mkdir(parents=True, exist_ok=True)
    free_gb = disk(reports).free / 1e9
    info["free_gb"] = round(free_gb, 1)
    if free_gb < MIN_FREE_GB:
        raise SystemExit(f"preflight: only {free_gb:.1f} GB free, need {MIN_FREE_GB} GB")
    if labels and labels.is_file():
        info["labels_sha256"] = hashlib.sha256(labels.read_bytes()).hexdigest()
    try:  # a VM copy made with git archive has no .git; then both stay None
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30, check=False)
        if commit.returncode == 0:
            info["git_commit"] = commit.stdout.strip()
            status = subprocess.run(["git", "status", "--porcelain", "--", "sandbox", "experiments"],
                                    capture_output=True, text=True, timeout=30, check=False)
            info["git_dirty"] = bool(status.stdout.strip())
    except OSError:
        pass
    return info


def _attempt(run_id: str, row: dict, docker, sandbox, cache) -> dict:
    package = f"{row['name']}@{row['version']}"
    volume = volume_name(run_id, package)
    docker(["docker", "volume", "create", volume], capture_output=True, text=True, timeout=60, check=True)
    try:
        prepared = prepare(volume, row, docker)
        if not prepared.get("ok"):
            return {"ok": False, "data": None, "error": prepared.get("error"), "fail_reason": "prepare"}
        # A failed dependency fetch still runs the sandbox: the offline install then shows what was missing.
        dependencies = cache(volume)
        result = compact(sandbox(volume))
        result["dependencies"] = {"ok": bool(dependencies.get("ok")), "error": dependencies.get("error")}
        return result
    finally:
        docker(["docker", "volume", "rm", "-f", volume], capture_output=True, text=True, timeout=60, check=False)


def run(run_id: str, rows: list[dict], reports: Path = Path("reports"), docker=subprocess.run, sandbox=None,
        cache=None, retry_failed: bool = False, checks: dict | None = None) -> dict:
    from experiments import run_batch as batch
    from sandbox.run import cache_dependencies, run_sandbox_volume

    if not batch.RUN_ID.fullmatch(run_id):
        raise ValueError("invalid run id")
    sandbox = sandbox or run_sandbox_volume
    cache = cache or (lambda volume: cache_dependencies(volume, docker))
    out = reports / run_id / "sandbox"
    out.mkdir(parents=True, exist_ok=True)
    stale = cleanup_stale(docker)
    counts = {"done": 0, "skipped": 0, "prepare_failed": 0, "cache_failed": 0, "sandbox_not_ok": 0, "canary": 0,
              "retried": 0, "fail_reason": {}}
    for row in rows:
        package = f"{row['name']}@{row['version']}"
        path = out / batch.result_name(package)
        if path.is_file():
            old = json.loads(path.read_text(encoding="utf-8"))
            if not (retry_failed and old.get("fail_reason") in RETRYABLE):
                counts["skipped"] += 1
                continue
        for attempt in range(1, ATTEMPTS + 1):
            result = _attempt(run_id, row, docker, sandbox, cache)
            if result.get("fail_reason") not in RETRYABLE:
                break
            counts["retried"] += attempt < ATTEMPTS
        result["attempts"] = attempt
        counts["done"] += 1
        counts["prepare_failed"] += result.get("fail_reason") == "prepare"
        counts["cache_failed"] += not (result.get("dependencies") or {"ok": True})["ok"]
        counts["sandbox_not_ok"] += not result["ok"]
        counts["canary"] += bool((result.get("data") or {}).get("canary_touched"))
        reason = result.get("fail_reason") or "none"
        counts["fail_reason"][reason] = counts["fail_reason"].get(reason, 0) + 1
        path.write_text(json.dumps({"package": package, **result}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"package": package, "ok": result["ok"],
                          "outcome": (result.get("data") or {}).get("outcome"), "fail_reason": result.get("fail_reason"),
                          "canary": (result.get("data") or {}).get("canary_touched")}, ensure_ascii=False), flush=True)
    (out / "sandbox_meta.json").write_text(json.dumps({"run_id": run_id, "counts": counts, "stale_removed": stale,
                                                       "preflight": checks,
                                                       "inputs": [f"{r['name']}@{r['version']}" for r in rows]},
                                                      ensure_ascii=False, indent=2), encoding="utf-8")
    return counts


def main() -> None:
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Record offline sandbox installs of labelled packages")
    parser.add_argument("run_id")
    parser.add_argument("--labels", type=Path, default=Path("data/labels-v1.csv"))
    parser.add_argument("--split", choices=("dev", "test"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    parser.add_argument("--retry-failed", action="store_true",
                        help="rerun saved rows whose fail_reason is infra, prepare or not_started")
    args = parser.parse_args()
    from experiments.dataset import load_labels
    checks = preflight(args.labels, args.reports)
    print(json.dumps({"preflight": checks}))
    rows = [row for row in load_labels(args.labels) if not args.split or row["split"] == args.split]
    rows = rows[:args.limit] if args.limit else rows
    print(json.dumps(run(args.run_id, rows, args.reports, retry_failed=args.retry_failed, checks=checks)))


if __name__ == "__main__":
    main()
