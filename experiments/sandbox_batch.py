"""Phase A of the sandbox ablation (Gate B0 2026-11-09): run each labelled package's install script in the
offline sandbox and record what it did, for `run_isolated --sandbox-results` (A-*-XS configs).

Per package:
1. `docker volume create agentnpm-…` (lives inside Docker's Linux VM, never on the Windows disk);
2. the disposable runner container downloads and safely extracts the source into the volume (pkg/), as
   run_isolated does in tmpfs; no package code runs here;
3. sandbox/run.py installs it from the volume: --network none, read-only root, cap-drop ALL (+SYS_PTRACE),
   256 MB without swap, 64 PIDs, 60 s, fake canaries;
4. the volume is removed. Only a behaviour summary is written (no raw strace, stdout or stderr text).

Run malicious samples in the clean Ubuntu VM (docs: sandbox/VM_UBUNTU.md); Docker Desktop is for tests and
benign packages. Same code on both.

    py -3.14 -m experiments.sandbox_batch <run_id> --labels data/labels-v1.csv --split dev
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

SUMMARY_KEYS = ("returncode", "outcome", "trace_complete", "canary_touched", "behavior")


def volume_name(run_id: str, package: str) -> str:
    return "agentnpm-" + hashlib.sha256(f"{run_id}\0{package}".encode()).hexdigest()[:24]


def compact(result: dict) -> dict:
    """What the agent's sandbox step reads (agent.run.run_sandbox_once), without raw untrusted text."""
    data = result.get("data")
    if not data:
        return {"ok": False, "data": None, "error": result.get("error")}
    package_files = ((data.get("by_actor") or {}).get("package") or {}).get("files_outside_package", [])
    summary = {key: data.get(key) for key in SUMMARY_KEYS}
    summary["by_actor"] = {"package": {"files_outside_package": package_files[:50]}}
    return {"ok": bool(result.get("ok")), "data": summary, "error": result.get("error")}


def prepare(volume: str, row: dict, docker=subprocess.run) -> dict:
    from experiments.run_isolated import container_command
    completed = docker(container_command(prepare_volume=volume), input=json.dumps({"row": row}),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900, check=False)
    lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    if completed.returncode or not lines:
        return {"ok": False, "error": f"prepare container failed: {(completed.stderr or '')[-200:]}"}
    return json.loads(lines[-1])


def run(run_id: str, rows: list[dict], reports: Path = Path("reports"), docker=subprocess.run, sandbox=None) -> dict:
    from experiments import run_batch as batch
    from sandbox.run import run_sandbox_volume

    if not batch.RUN_ID.fullmatch(run_id):
        raise ValueError("invalid run id")
    sandbox = sandbox or run_sandbox_volume
    out = reports / run_id / "sandbox"
    out.mkdir(parents=True, exist_ok=True)
    counts = {"done": 0, "skipped": 0, "prepare_failed": 0, "sandbox_not_ok": 0, "canary": 0}
    for row in rows:
        package = f"{row['name']}@{row['version']}"
        path = out / batch.result_name(package)
        if path.is_file():
            counts["skipped"] += 1
            continue
        volume = volume_name(run_id, package)
        docker(["docker", "volume", "create", volume], capture_output=True, text=True, timeout=60, check=True)
        try:
            prepared = prepare(volume, row, docker)
            if prepared.get("ok"):
                result = compact(sandbox(volume))
            else:
                counts["prepare_failed"] += 1
                result = {"ok": False, "data": None, "error": prepared.get("error")}
        finally:
            docker(["docker", "volume", "rm", "-f", volume], capture_output=True, text=True, timeout=60, check=False)
        counts["done"] += 1
        counts["sandbox_not_ok"] += not result["ok"]
        counts["canary"] += bool((result.get("data") or {}).get("canary_touched"))
        path.write_text(json.dumps({"package": package, **result}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"package": package, "ok": result["ok"],
                          "outcome": (result.get("data") or {}).get("outcome"),
                          "canary": (result.get("data") or {}).get("canary_touched")}, ensure_ascii=False), flush=True)
    (out / "sandbox_meta.json").write_text(json.dumps({"run_id": run_id, "counts": counts,
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
    args = parser.parse_args()
    from experiments.dataset import load_labels
    rows = [row for row in load_labels(args.labels) if not args.split or row["split"] == args.split]
    rows = rows[:args.limit] if args.limit else rows
    print(json.dumps(run(args.run_id, rows, args.reports)))


if __name__ == "__main__":
    main()
