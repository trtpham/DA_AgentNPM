"""Bounded, read-only inspection of an extracted package."""

import json
import re
from pathlib import Path

MAX_FILE_BYTES = 256 * 1024
MAX_LINES = 150
MAX_LINE_CHARS = 1000


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
        lines = []
        truncated = False
        with target.open(encoding="utf-8", errors="replace") as stream:
            for number, line in enumerate(stream, 1):
                if number > end:
                    break
                if number < start:
                    continue
                line = line.rstrip("\n")
                if len(line) > MAX_LINE_CHARS:
                    truncated = True
                    line = f"{line[:MAX_LINE_CHARS]}…[cắt {len(line) - MAX_LINE_CHARS} ký tự]"
                lines.append(line)
        data = {"untrusted": True, "content": "\n".join(lines)}
        if truncated:
            data["truncated"] = True
        return {"ok": True, "data": data, "error": None}
    except (OSError, ValueError) as error:
        return {"ok": False, "data": None, "error": str(error)[:300]}


def read_manifest(package: str) -> dict:
    try:
        raw = _safe_file(package, "package.json").read_text(encoding="utf-8")
        manifest = json.loads(raw)
        if not isinstance(manifest, dict):
            raise ValueError("invalid package.json")
        scripts = manifest.get("scripts", {})
        if not isinstance(scripts, dict) or any(not isinstance(key, str) or not isinstance(value, str)
                                                for key, value in scripts.items()):
            raise ValueError("invalid scripts")
        script_lines = {}
        source_lines = raw.splitlines()
        scripts_start = re.search(r'(?<!\\)"scripts"\s*:\s*\{', raw)
        if scripts and scripts_start is None:
            raise ValueError("cannot locate scripts in package.json")
        for hook in scripts:
            match = re.search(r'(?<!\\)"' + re.escape(hook) + r'"\s*:', raw[scripts_start.end():])
            if match is None:
                raise ValueError(f"cannot locate script {hook} in package.json")
            script_lines[hook] = raw.count("\n", 0, scripts_start.end() + match.start()) + 1
        deps = {key: manifest.get(key, {}) for key in ("dependencies", "devDependencies", "optionalDependencies")}
        if any(not isinstance(value, dict) for value in deps.values()):
            raise ValueError("invalid dependencies")
        suspicious = {name: spec for group in deps.values() for name, spec in group.items()
                      if isinstance(spec, str) and (spec.startswith(("git+", "git:", "http:", "https:")) or "github.com/" in spec)}
        return {"ok": True, "data": {
            "name": manifest.get("name"),
            "version": manifest.get("version"),
            "scripts": {"untrusted": True, "content": scripts},
            "script_lines": script_lines,
            "script_excerpts": {hook: source_lines[line - 1][:MAX_LINE_CHARS] for hook, line in script_lines.items()},
            "dependencies": {"untrusted": True, "content": deps},
            "git_or_url_deps": {"untrusted": True, "content": suspicious},
            "bin": {"untrusted": True, "content": manifest.get("bin", {})},
            "has_binding_gyp": (Path(package) / "binding.gyp").is_file(),
        }, "error": None}
    except (OSError, ValueError, TypeError) as error:
        return {"ok": False, "data": None, "error": str(error)[:300]}
