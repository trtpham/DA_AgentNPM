"""Weeks 7-8: run the agent on labelled packages inside a disposable container (Gate B0 2026-11-08).

    docker build -t agent-npm-runner:local experiments/runner
    py -3.14 -m experiments.run_isolated <run_id> A-LLM-X --labels data/labels-v1.csv --split dev

Malicious samples must not be unpacked on the Windows host and npm no longer serves them, so each
batch runs in a container: it downloads the source (npm tarball checked against the registry
sha512, or the Datadog ZIP at its pinned commit), extracts it into tmpfs, and runs the same
`experiments.run_batch.run_one` the host uses (static reading only, decisions dry-run). The model
is the host's Ollama, reached as host.docker.internal (agent.run.ollama_host accepts nothing else).
Results and traces come back as text and are written in the usual reports/<run_id>/ layout, so
experiments.metrics, threshold_sweep and calibration work unchanged. Resumable.
"""

import argparse
import base64
import hashlib
import io
import json
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

_PARENTS = Path(__file__).resolve().parents
ROOT = _PARENTS[1] if len(_PARENTS) > 1 else _PARENTS[0]
IMAGE = "agent-npm-runner:local"
BATCH = 5
MAX_ARCHIVE = 60 * 1024 * 1024
SOURCE_HOSTS = {"registry.npmjs.org", "raw.githubusercontent.com"}


def _get(url: str) -> bytes:
    if urllib.parse.urlsplit(url).hostname not in SOURCE_HOSTS or not url.startswith("https://"):
        raise ValueError("source host not allowed")
    request = urllib.request.Request(url, headers={"User-Agent": "DA_AgentNPM-research"})
    with urllib.request.urlopen(request, timeout=120) as response:  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        data = response.read(MAX_ARCHIVE + 1)
    if len(data) > MAX_ARCHIVE:
        raise ValueError("archive too large")
    return data


def materialize(row: dict, work: Path) -> Path:
    """Download and safely extract one labelled source into `work/package`; returns that directory."""
    from data.scripts.datadog_container import _extract_members
    from tools.fetch import _extract

    shutil.rmtree(work, ignore_errors=True)
    target = work / "package"
    target.mkdir(parents=True)
    data = _get(row["source"])
    if urllib.parse.urlsplit(row["source"]).hostname == "registry.npmjs.org":
        meta = json.loads(_get(f"https://registry.npmjs.org/{row['name']}/{row['version']}"))
        algorithm, digest = meta["dist"]["integrity"].split("-", 1)
        if algorithm != "sha512" or hashlib.sha512(data).digest() != base64.b64decode(digest):
            raise ValueError("tarball does not match registry integrity")
        (work / "pkg.tgz").write_bytes(data)
        _extract(work / "pkg.tgz", target)
        return target
    with zipfile.ZipFile(io.BytesIO(data)) as zipped:
        tarballs = [member for member in zipped.infolist() if member.filename.endswith((".tgz", ".tar.gz"))]
        if len(tarballs) == 1:
            (work / "pkg.tgz").write_bytes(zipped.read(tarballs[0], pwd=b"infected"))
            _extract(work / "pkg.tgz", target)
        else:
            _extract_members(zipped, target)
    return target


def inside(job: dict) -> dict:
    """Container side: one labelled row -> run_one result plus its trace text."""
    from experiments.run_batch import run_one
    from agent.trace import trace_filename

    row, config = job["row"], job["config"]
    package = f"{row['name']}@{row['version']}"
    run_dir = Path("/tmp/run")
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        directory = materialize(row, Path("/tmp/work"))
    except Exception as error:  # the source could not be prepared; recorded like a failed fetch
        return {"result": {"package": package, "variant": config["name"], "model": config["model"],
                           "status": "error", "error": f"source: {type(error).__name__}: {str(error)[:200]}"},
                "trace": None}
    result = run_one({"package": package, "dir": directory}, run_dir, config, None)
    trace = run_dir / trace_filename(package)
    text = trace.read_text(encoding="utf-8") if trace.is_file() else None
    shutil.rmtree("/tmp/work", ignore_errors=True)
    return {"result": result, "trace": text}


GUARDDOG_IMAGE = "agent-npm-guarddog:2.6.0"


def strip_code(result: dict) -> dict:
    """Drop the matched source text from GuardDog findings, keep rule, location and message.

    The `code` field quotes the malware itself; Windows Defender quarantined 16 of 500 result files
    because of it (08/11/2026). Scores only need the issue count and the rules.
    """
    data = result.get("data")
    if not data:
        return result
    findings = {rule: [{key: value for key, value in item.items() if key != "code"} if isinstance(item, dict) else item
                       for item in items] if isinstance(items, list) else items
                for rule, items in (data.get("results") or {}).items()}
    return {**result, "data": {**data, "results": findings}}


def inside_guarddog(job: dict) -> dict:
    """Container side (GuardDog image): materialize the source and scan it with GuardDog, static only."""
    from experiments.baseline_guarddog import parse_report

    row = job["row"]
    package = f"{row['name']}@{row['version']}"
    try:
        directory = materialize(row, Path("/tmp/work"))
        completed = subprocess.run(["guarddog", "npm", "scan", str(directory), "--output-format", "json"],
                                   capture_output=True, text=True, timeout=600, check=False)
        result = strip_code(parse_report(completed.stdout))
    except Exception as error:  # scored as an error, like a failed baseline scan
        result = {"ok": False, "data": None, "error": f"{type(error).__name__}: {str(error)[:200]}"}
    finally:
        shutil.rmtree("/tmp/work", ignore_errors=True)
    return {"result": {**result, "package": package}, "trace": None}


def container_command(guarddog: bool = False) -> list[str]:
    mounts = []
    for folder in ("agent", "tools", "experiments", "data/scripts"):
        mounts += ["--mount", f"type=bind,source={ROOT / folder},target=/app/{folder},readonly"]
    common = ["docker", "run", "--rm", "-i", "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=1g",
              "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "2g", "--user", "10001:10001",
              "--env", "PYTHONDONTWRITEBYTECODE=1", *mounts, "--workdir", "/tmp"]
    if guarddog:
        # semgrep needs more processes; HOME in tmpfs for its cache; no Ollama access needed.
        return [*common, "--pids-limit", "128", "--env", "HOME=/tmp", "--entrypoint", "python",
                GUARDDOG_IMAGE, "-I", "/app/experiments/run_isolated.py", "--inside", "--guarddog"]
    return [*common, "--pids-limit", "64", "--add-host", "host.docker.internal:host-gateway",
            "--env", "AGENT_OLLAMA_HOST=host.docker.internal",
            IMAGE, "python", "-I", "/app/experiments/run_isolated.py", "--inside"]


def run_guarddog(run_id: str, rows: list[dict], reports: Path = Path("reports"), runner=subprocess.run) -> dict:
    """GuardDog baseline on the same labelled rows, written like experiments.baseline_guarddog."""
    from experiments import run_batch as batch

    if not batch.RUN_ID.fullmatch(run_id):
        raise ValueError("invalid run id")
    out = reports / run_id / "guarddog"
    out.mkdir(parents=True, exist_ok=True)
    todo = [row for row in rows if not (out / batch.result_name(f"{row['name']}@{row['version']}")).is_file()]
    counts = {"done": 0, "skipped": len(rows) - len(todo), "errors": 0}
    for start in range(0, len(todo), BATCH):
        chunk = todo[start:start + BATCH]
        completed = runner(container_command(guarddog=True), input="\n".join(json.dumps({"row": row}) for row in chunk),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=7200, check=False)
        outputs = [json.loads(line) for line in (completed.stdout or "").splitlines() if line.strip()]
        if completed.returncode or len(outputs) != len(chunk):
            raise RuntimeError(f"container failed ({len(outputs)}/{len(chunk)}): {(completed.stderr or '')[-300:]}")
        for output in outputs:
            result = output["result"]
            (out / batch.result_name(result["package"])).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                                                     encoding="utf-8")
            counts["done"] += 1
            counts["errors"] += not result.get("ok")
    (out / "guarddog_meta.json").write_text(json.dumps({"tool": "guarddog", "image": GUARDDOG_IMAGE, "isolated": True,
                                                        "inputs": [f"{row['name']}@{row['version']}" for row in rows]},
                                                       ensure_ascii=False, indent=2), encoding="utf-8")
    return counts


def run(run_id: str, variant: str, rows: list[dict], reports: Path = Path("reports"), runner=subprocess.run) -> dict:
    from experiments import run_batch as batch

    if not batch.RUN_ID.fullmatch(run_id):
        raise ValueError("invalid run id")
    config = batch.load_config(variant)
    run_dir = reports / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    meta_path = run_dir / "run_meta.json"
    inputs = [{"package": f"{row['name']}@{row['version']}"} for row in rows]
    meta = (json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file()
            else batch.run_meta(run_id, config, inputs, None))
    if meta["config"] != config:
        raise ValueError("run_id was started with a different config; use a new run id")
    meta["isolated"] = {"image": IMAGE, "container": "disposable, read-only, tmpfs, cap-drop ALL"}
    todo = [row for row in rows if not (run_dir / batch.result_name(f"{row['name']}@{row['version']}")).is_file()]
    counts = {"done": 0, "skipped": len(rows) - len(todo), "errors": 0}
    for start in range(0, len(todo), BATCH):
        chunk = todo[start:start + BATCH]
        completed = runner(container_command(), input="\n".join(json.dumps({"row": row, "config": config}) for row in chunk),
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=7200, check=False)
        outputs = [json.loads(line) for line in (completed.stdout or "").splitlines() if line.strip()]
        if completed.returncode or len(outputs) != len(chunk):
            raise RuntimeError(f"container failed ({len(outputs)}/{len(chunk)}): {(completed.stderr or '')[-300:]}")
        for output in outputs:
            result = output["result"]
            if output["trace"] is not None and result.get("trace"):
                (run_dir / result["trace"]).write_text(output["trace"], encoding="utf-8")
            (run_dir / batch.result_name(result["package"])).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                                                         encoding="utf-8")
            counts["done"] += 1
            counts["errors"] += result.get("status") == "error"
            print(json.dumps({key: result.get(key) for key in ("package", "status", "decision", "elapsed_s")},
                             ensure_ascii=False), flush=True)
    meta.update(last_counts=counts)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return counts


def main() -> None:
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Run the agent on labelled packages inside a disposable container")
    parser.add_argument("run_id", nargs="?")
    parser.add_argument("variant", nargs="?")
    parser.add_argument("--labels", type=Path, default=Path("data/labels-v1.csv"))
    parser.add_argument("--split", choices=("dev", "test"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    parser.add_argument("--guarddog", action="store_true", help="GuardDog baseline instead of the agent (no variant)")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside:
        sys.path.insert(0, "/app")
        handler = inside_guarddog if args.guarddog else inside
        for line in sys.stdin:
            if line.strip():
                print(json.dumps(handler(json.loads(line)), ensure_ascii=False), flush=True)
        return
    if not args.run_id or not (args.variant or args.guarddog):
        parser.error("run_id and variant (or --guarddog) are required")
    from experiments.dataset import load_labels
    rows = [row for row in load_labels(args.labels) if not args.split or row["split"] == args.split]
    rows = rows[:args.limit] if args.limit else rows
    print(json.dumps(run_guarddog(args.run_id, rows, args.reports) if args.guarddog
                     else run(args.run_id, args.variant, rows, args.reports)))


if __name__ == "__main__":
    main()
