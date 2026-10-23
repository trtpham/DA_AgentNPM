"""Bounded, read-only inspection of an extracted package."""

import json
from pathlib import Path

MAX_FILE_BYTES = 256 * 1024
MAX_LINES = 150


def _safe_file(package: str, file: str) -> Path:
    root = Path(package).resolve(strict=True)
    target = root / file
    if target.is_symlink() or not target.resolve(strict=True).is_relative_to(root):
        raise ValueError("file escapes package directory")
    if not target.is_file() or target.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("file missing or too large")
    return target


def read_file(package: str, file: str, start: int = 1, end: int = 150) -> dict:
    try:
        if start < 1 or end < start or end - start + 1 > MAX_LINES:
            raise ValueError("invalid line range")
        target = _safe_file(package, file)
        with target.open(encoding="utf-8", errors="replace") as stream:
            lines = [line.rstrip("\n") for number, line in enumerate(stream, 1) if start <= number <= end]
        return {"ok": True, "data": {"untrusted": True, "content": "\n".join(lines)}, "error": None}
    except (OSError, ValueError) as error:
        return {"ok": False, "data": None, "error": str(error)[:300]}


def read_manifest(package: str) -> dict:
    try:
        manifest = json.loads(_safe_file(package, "package.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("invalid package.json")
        deps = {key: manifest.get(key, {}) for key in ("dependencies", "devDependencies", "optionalDependencies")}
        if any(not isinstance(value, dict) for value in deps.values()):
            raise ValueError("invalid dependencies")
        suspicious = {name: spec for group in deps.values() for name, spec in group.items()
                      if isinstance(spec, str) and (spec.startswith(("git+", "git:", "http:", "https:")) or "github.com/" in spec)}
        return {"ok": True, "data": {
            "scripts": {"untrusted": True, "content": manifest.get("scripts", {})},
            "dependencies": {"untrusted": True, "content": deps},
            "git_or_url_deps": {"untrusted": True, "content": suspicious},
            "bin": {"untrusted": True, "content": manifest.get("bin", {})},
            "has_binding_gyp": (Path(package) / "binding.gyp").is_file(),
        }, "error": None}
    except (OSError, ValueError, TypeError) as error:
        return {"ok": False, "data": None, "error": str(error)[:300]}
