"""Download npm tarballs without executing package scripts."""

import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

NAME = re.compile(r"^(?:@[a-z0-9._-]+/)?[a-z0-9._-]+$")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
MAX_FILES = 2000
MAX_BYTES = 50 * 1024 * 1024


def _extract(tarball: Path, destination: Path) -> list[str]:
    files = []
    seen = set()
    total = 0
    with tarfile.open(tarball, "r:gz") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or ".." in path.parts or "\\" in member.name
                    or any(":" in part for part in path.parts)
                    or not path.parts or path.parts[0] != "package"):
                raise ValueError("unsafe tar path")
            if not (member.isfile() or member.isdir()):
                raise ValueError("tar links and special files are forbidden")
            if member.isdir():
                continue
            total += member.size
            if len(files) >= MAX_FILES or total > MAX_BYTES:
                raise ValueError("package exceeds extraction limits")
            relative = Path(*path.parts[1:])
            if not relative.parts:
                raise ValueError("invalid tar file path")
            if relative in seen:
                raise ValueError("duplicate tar file path")
            seen.add(relative)
            target = destination / relative
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError("unsafe tar path")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            files.append(relative.as_posix())
    return files


def fetch_package(name: str, version: str) -> dict:
    if not NAME.fullmatch(name) or not VERSION.fullmatch(version):
        return {"ok": False, "data": None, "error": "invalid package name or version"}
    directory = Path(tempfile.mkdtemp(prefix="npm-agent-"))
    try:
        result = subprocess.run(
            [shutil.which("npm") or "npm", "pack", f"{name}@{version}", "--ignore-scripts", "--json", "--pack-destination", str(directory)],
            capture_output=True, text=True, timeout=120, check=True,
        )
        filename = json.loads(result.stdout)[0]["filename"]
        if Path(filename).name != filename:
            raise ValueError("invalid npm tarball filename")
        files = _extract(directory / filename, directory / "package")
        (directory / filename).unlink()
        return {"ok": True, "data": {"dir": str(directory / "package"), "files": files}, "error": None}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError, json.JSONDecodeError, tarfile.TarError) as error:
        shutil.rmtree(directory)
        return {"ok": False, "data": None, "error": str(error)[:300]}
