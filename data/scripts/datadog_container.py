"""S2: sample the Datadog npm malware dataset inside a disposable container (Gate B0 2026-11-08).

    py -3.14 -m data.scripts.datadog_container --zips 2400

Host:      lists samples/npm/malicious_intent/**.zip at a pinned commit (GitHub tree API, metadata
           only), shuffles with a fixed seed and sends paths to a container in batches of 100.
Container: downloads each ZIP from raw.githubusercontent.com into tmpfs, opens it with the
           dataset password, extracts the inner npm tarball safely, runs the project's static
           triage (read only) and prints one JSON line of metadata. No package code runs and no
           archive reaches the Windows disk. Output: data/datadog/candidates-batch-XXX.jsonl.
"""

import argparse
import hashlib
import io
import json
import random
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

_PARENTS = Path(__file__).resolve().parents
ROOT = _PARENTS[2] if len(_PARENTS) > 2 else _PARENTS[0]
OUT_DIR = ROOT / "data" / "datadog"
REPO = "DataDog/malicious-software-packages-dataset"
COMMIT = "72c723be547033c558244520524b117c8d71663b"  # main on 2026-11-05, pinned for reproducibility
RAW = f"https://raw.githubusercontent.com/{REPO}/{COMMIT}/samples/npm/malicious_intent/"
SEED = 20261108
BATCH = 100
MAX_ZIP = 20 * 1024 * 1024
IMAGE = "python:3.12-slim"


def _get(url: str, limit: int = MAX_ZIP) -> bytes:
    host = urllib.parse.urlsplit(url).hostname
    if host not in ("raw.githubusercontent.com", "api.github.com") or not url.startswith("https://"):
        raise ValueError("only GitHub hosts are allowed")
    request = urllib.request.Request(url, headers={"User-Agent": "DA_AgentNPM-research"})
    with urllib.request.urlopen(request, timeout=120) as response:  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("download too large")
    return data


def zip_paths() -> list[str]:
    """Every ZIP under malicious_intent at COMMIT (paths only, never contents)."""
    api = f"https://api.github.com/repos/{REPO}/git/trees/"
    node = COMMIT
    for name in ("samples", "npm", "malicious_intent"):
        node = next(item["sha"] for item in json.loads(_get(api + node, 50_000_000))["tree"] if item["path"] == name)
    tree = json.loads(_get(api + node + "?recursive=1", 200_000_000))
    if tree.get("truncated"):
        raise RuntimeError("tree listing truncated")
    return sorted(item["path"] for item in tree["tree"] if item["path"].endswith(".zip"))


def sample(paths: list[str], count: int, seed: int = SEED) -> list[str]:
    chosen = list(paths)
    random.Random(seed).shuffle(chosen)
    return chosen[:count]


MAX_FILES, MAX_BYTES = 2000, 50 * 1024 * 1024


def dataset_name(folder: str) -> str:
    """The dataset stores `@scope/name` in a folder called `@scope@name`."""
    if folder.startswith("@") and "/" not in folder and folder.count("@") == 2:
        scope, name = folder[1:].split("@", 1)
        return f"@{scope}/{name}"
    return folder


def _extract_members(zipped: zipfile.ZipFile, destination: Path) -> None:
    """Most dataset ZIPs hold the package files directly: the shallowest package.json is the root.

    Same rules as tools.fetch._extract: no absolute paths, no `..`, no drive letters, size limits.
    """
    names = [member.filename for member in zipped.infolist() if not member.is_dir()]
    manifests = [name for name in names if name.rsplit("/", 1)[-1] == "package.json"]
    if not manifests:
        raise ValueError("no package.json in the ZIP")
    prefix = min(manifests, key=lambda name: (name.count("/"), name))[: -len("package.json")]
    total, count = 0, 0
    for member in zipped.infolist():
        if member.is_dir() or not member.filename.startswith(prefix):
            continue
        relative = PurePosixPath(member.filename[len(prefix):])
        if (relative.is_absolute() or ".." in relative.parts or "\\" in member.filename
                or any(":" in part for part in relative.parts) or not relative.parts):
            raise ValueError("unsafe zip path")
        total += member.file_size
        count += 1
        if count > MAX_FILES or total > MAX_BYTES:
            raise ValueError("package exceeds extraction limits")
        target = destination / Path(*relative.parts)
        if not target.resolve().is_relative_to(destination.resolve()):
            raise ValueError("unsafe zip path")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(zipped.read(member, pwd=b"infected"))


def inspect(path: str, work: Path) -> dict:
    """Container side: one dataset ZIP -> metadata and static triage (nothing is executed)."""
    from data.scripts.triage_candidates import triage
    from tools.fetch import _extract

    parts = path.split("/")
    result = {"path": path, "name": dataset_name("/".join(parts[:-2])), "version": parts[-2], "archive": RAW + path}
    try:
        data = _get(RAW + path)
        result["zip_sha256"] = hashlib.sha256(data).hexdigest()
        shutil.rmtree(work, ignore_errors=True)
        (work / "package").mkdir(parents=True)
        with zipfile.ZipFile(io.BytesIO(data)) as zipped:
            tarballs = [member for member in zipped.infolist() if member.filename.endswith((".tgz", ".tar.gz"))]
            if len(tarballs) == 1 and tarballs[0].file_size <= MAX_ZIP:
                (work / "pkg.tgz").write_bytes(zipped.read(tarballs[0], pwd=b"infected"))
                _extract(work / "pkg.tgz", work / "package")
            else:
                _extract_members(zipped, work / "package")
        found = triage(str(work / "package"))
        result.update({key: found.get(key) for key in ("manifest", "hooks", "entries", "install_hash", "reasons",
                                                       "external", "risky", "hosts", "flows")})
        result["has_hook"] = bool(found.get("hooks"))
    except Exception as error:  # report and continue
        result["error"] = f"{type(error).__name__}: {str(error)[:150]}"
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return result


def container_command() -> list[str]:
    mounts = []
    for source, target in ((ROOT / "tools", "/app/tools"), (ROOT / "agent", "/app/agent"),
                           (ROOT / "data" / "scripts", "/app/data/scripts")):
        mounts += ["--mount", f"type=bind,source={source},target={target},readonly"]
    return ["docker", "run", "--rm", "-i", "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=512m",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "1g", "--pids-limit", "64",
            "--user", "10001:10001", *mounts, "--env", "PYTHONDONTWRITEBYTECODE=1",
            IMAGE, "python", "-I", "/app/data/scripts/datadog_container.py", "--inside"]


def run_batch(number: int, paths: list[str], out_dir: Path = OUT_DIR, runner=subprocess.run) -> Path | None:
    output = out_dir / f"candidates-batch-{number:03}.jsonl"
    if output.is_file() and len(output.read_text(encoding="utf-8").splitlines()) == len(paths):
        return None
    completed = runner(container_command(), input="\n".join(paths), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=3600, check=False)
    results = [json.loads(line) for line in (completed.stdout or "").splitlines() if line.strip()]
    if completed.returncode or len(results) != len(paths):
        raise RuntimeError(f"batch {number}: {len(results)}/{len(paths)}: {(completed.stderr or '')[-300:]}")
    out_dir.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in results), encoding="utf-8")
    return output


def main() -> None:
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Sample Datadog npm malware metadata in a disposable container")
    parser.add_argument("--zips", type=int, default=2400, help="how many ZIPs to inspect (seeded sample)")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside:
        sys.path.insert(0, "/app")
        for line in sys.stdin:
            if line.strip():
                print(json.dumps(inspect(line.strip(), Path("/tmp/work")), ensure_ascii=False), flush=True)
        return
    chosen = sample(zip_paths(), args.zips)
    for number, start in enumerate(range(0, len(chosen), BATCH), 1):
        written = run_batch(number, chosen[start:start + BATCH])
        print(json.dumps({"batch": number, "status": "done" if written else "skipped"}), flush=True)


if __name__ == "__main__":
    main()
