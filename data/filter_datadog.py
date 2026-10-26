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
MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_SOURCE_FILES = 1000
FIELDS = ("name", "version", "hooks", "sha256", "cluster", "archive")


def _manifest(data: bytes) -> dict | None:
    if len(data) > MAX_MANIFEST:
        return None
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _members(archive: Path) -> tuple[dict | None, str | None, tuple[str, ...]]:
    manifest, binding, manifest_rank = None, None, None
    source_hashes = []
    source_bytes = 0
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            if member.is_dir():
                continue
            name = member.filename.replace("\\", "/")
            source_file = name.endswith((".js", ".cjs", ".mjs", ".sh")) and "node_modules" not in name.split("/")
            if member.file_size > MAX_MEMBER:
                if source_file:
                    raise ValueError("source member too large")
                continue
            if (name.endswith("/binding.gyp") or name == "binding.gyp") and "node_modules" not in name.split("/"):
                binding = hashlib.sha256(zipped.read(member, pwd=b"infected")).hexdigest()
            if not (name.endswith("/package.json") or name == "package.json" or
                    name.endswith((".tgz", ".tar.gz", ".tar", ".js", ".cjs", ".mjs", ".sh"))):
                continue
            if source_file:
                if source_bytes + member.file_size > MAX_SOURCE_BYTES or len(source_hashes) >= MAX_SOURCE_FILES:
                    raise ValueError("source budget exceeded")
                source_bytes += member.file_size
            content = zipped.read(member, pwd=b"infected")
            if source_file:
                source_hashes.append(f"{name}:{hashlib.sha256(content).hexdigest()}")
            if name.endswith("package.json"):
                candidate = _manifest(content)
                rank = (len(name.split("/")), name != "package/package.json", name)
                if candidate is not None and (manifest_rank is None or rank < manifest_rank):
                    manifest, manifest_rank = candidate, rank
            elif name.endswith((".tgz", ".tar.gz", ".tar")):
                with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as tar:
                    for item in tar:
                        if not item.isfile():
                            continue
                        inner = item.name.replace("\\", "/")
                        source_file = inner.endswith((".js", ".cjs", ".mjs", ".sh")) and "node_modules" not in inner.split("/")
                        if item.size > MAX_MEMBER:
                            if source_file:
                                raise ValueError("source member too large")
                            continue
                        if not (inner.endswith(("/binding.gyp", "/package.json", ".js", ".cjs", ".mjs", ".sh")) or
                                inner in ("binding.gyp", "package.json")):
                            continue
                        if source_file:
                            if source_bytes + item.size > MAX_SOURCE_BYTES or len(source_hashes) >= MAX_SOURCE_FILES:
                                raise ValueError("source budget exceeded")
                            source_bytes += item.size
                        stream = tar.extractfile(item)
                        if stream is None:
                            continue
                        data = stream.read(MAX_MEMBER + 1)
                        if (inner.endswith("/binding.gyp") or inner == "binding.gyp") and "node_modules" not in inner.split("/"):
                            binding = hashlib.sha256(data).hexdigest()
                        if source_file:
                            source_hashes.append(f"{inner}:{hashlib.sha256(data).hexdigest()}")
                        if inner.endswith("/package.json") or inner == "package.json":
                            candidate = _manifest(data)
                            rank = (len(inner.split("/")), inner != "package/package.json", inner)
                            if candidate is not None and (manifest_rank is None or rank < manifest_rank):
                                manifest, manifest_rank = candidate, rank
    # shortcut: hash all source files, narrow to script dependencies if archive noise causes over-splitting.
    return manifest, binding, tuple(sorted(source_hashes))


def _cluster(scripts: dict, binding: str | None, source_hashes: tuple[str, ...]) -> str:
    source = "\n".join(str(scripts.get(hook, "")) for hook in HOOKS)
    if binding:
        source += "\nnode-gyp rebuild:" + binding
    source += "\n" + "\n".join(source_hashes)
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
            manifest, binding, source_hashes = _members(archive)
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
        cluster = _cluster(scripts, binding, source_hashes)
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
