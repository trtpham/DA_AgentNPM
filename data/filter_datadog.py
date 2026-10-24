"""Read Datadog archives in an isolated VM; never extract or execute package code."""

import argparse
import csv
import hashlib
import io
import json
import re
import tarfile
import zipfile
from pathlib import Path

HOOKS = ("preinstall", "install", "postinstall", "prepare")
MAX_MEMBER = 10 * 1024 * 1024
MAX_MANIFEST = 256 * 1024
FIELDS = ("name", "version", "hooks", "sha256", "cluster", "archive")


def _manifest(data: bytes) -> dict | None:
    if len(data) > MAX_MANIFEST:
        return None
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _members(archive: Path) -> tuple[dict | None, str | None]:
    manifest, binding = None, None
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            if member.is_dir() or member.file_size > MAX_MEMBER:
                continue
            name = member.filename.replace("\\", "/")
            if name.endswith("/binding.gyp") or name == "binding.gyp":
                binding = hashlib.sha256(zipped.read(member, pwd=b"infected")).hexdigest()
            if not (name.endswith("/package.json") or name == "package.json" or
                    name.endswith((".tgz", ".tar.gz", ".tar"))):
                continue
            content = zipped.read(member, pwd=b"infected")
            if name.endswith("package.json") and manifest is None:
                manifest = _manifest(content)
            elif name.endswith((".tgz", ".tar.gz", ".tar")):
                with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as tar:
                    for item in tar:
                        if not item.isfile() or item.size > MAX_MEMBER:
                            continue
                        inner = item.name.replace("\\", "/")
                        if inner.endswith("/binding.gyp") or inner == "binding.gyp":
                            stream = tar.extractfile(item)
                            if stream is not None:
                                binding = hashlib.sha256(stream.read()).hexdigest()
                        if (inner.endswith("/package.json") or inner == "package.json") and manifest is None:
                            stream = tar.extractfile(item)
                            if stream is not None:
                                manifest = _manifest(stream.read(MAX_MANIFEST + 1))
    return manifest, binding


def _cluster(scripts: dict, binding: str | None) -> str:
    source = "\n".join(str(scripts.get(hook, "")) for hook in HOOKS)
    if binding:
        source += "\nnode-gyp rebuild:" + binding
    source = re.sub(r"https?://[^\s\"']+", "<URL>", source)
    source = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "<IP>", source)
    source = re.sub(r"\s+", "", source)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def filter_archives(source: Path, destination: Path) -> dict[str, int]:
    if not source.is_dir():
        raise ValueError("source directory missing")
    candidates, seen = [], set()
    scanned = matching = failed = 0
    for archive in sorted(source.rglob("*.zip")):
        scanned += 1
        try:
            manifest, binding = _members(archive)
        except (OSError, ValueError, RuntimeError, NotImplementedError, tarfile.TarError, zipfile.BadZipFile):
            failed += 1
            continue
        if not manifest or not isinstance(manifest.get("scripts", {}), dict):
            continue
        scripts = manifest.get("scripts", {})
        if any(not isinstance(scripts.get(hook, ""), str) for hook in HOOKS):
            continue
        hooks = [hook for hook in HOOKS if hook in scripts]
        if binding:
            hooks.append("binding.gyp")
        if not hooks or not all(isinstance(manifest.get(key), str) for key in ("name", "version")):
            continue
        matching += 1
        cluster = _cluster(scripts, binding)
        if cluster in seen:
            continue
        seen.add(cluster)
        with archive.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        candidates.append({"name": manifest["name"], "version": manifest["version"],
                           "hooks": ";".join(hooks), "sha256": digest,
                           "cluster": cluster, "archive": archive.relative_to(source).as_posix()})
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(candidates)
    return {"scanned": scanned, "matching_before_dedup": matching,
            "candidates": len(candidates), "failed": failed}


def main() -> None:
    parser = argparse.ArgumentParser(description="VM-only, read-only Datadog archive filtering")
    parser.add_argument("source", type=Path, help="Datadog dataset directory inside the isolated VM")
    parser.add_argument("destination", type=Path, help="candidates.csv output inside the VM")
    args = parser.parse_args()
    print(json.dumps(filter_archives(args.source, args.destination)))


if __name__ == "__main__":
    main()
