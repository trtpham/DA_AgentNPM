"""Bounded, read-only inspection of an extracted package."""

import json
import base64
import binascii
from collections import Counter
import io
import math
import re
from pathlib import Path

MAX_FILE_BYTES = 256 * 1024
MAX_LINES = 150
MAX_LINE_CHARS = 1000


def _pretty_source(package: str, file: str) -> str:
    if not file.endswith((".js", ".cjs", ".mjs")):
        raise ValueError("pretty view requires JavaScript file")
    source = _safe_file(package, file).read_text(encoding="utf-8", errors="replace")
    # shortcut: punctuation splitting is a preview, upgrade to a JS parser for exact formatting.
    output, quote, escaped = [], None, False
    for char in source:
        output.append(char)
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in ("'", '"', "`"):
            quote = char
        elif char in (";", "{", "}"):
            output.append("\n")
    return "".join(output)


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
        stream = (io.StringIO(_pretty_source(package, file[:-7])) if file.endswith("#pretty")
                  else _safe_file(package, file).open(encoding="utf-8", errors="replace"))
        lines = []
        truncated = False
        with stream:
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


def deobfuscate(package: str, file: str) -> dict:
    try:
        pretty = _pretty_source(package, file)
        if len(pretty) > MAX_FILE_BYTES * 2:
            raise ValueError("formatted file too large")
        decoded = []
        for match in re.finditer(r"(?<![\w])(?:[A-Za-z0-9+/]{40,}={0,2}|[0-9a-fA-F]{40,})(?![\w])", pretty):
            if len(decoded) == 5:
                break
            token = match.group()
            try:
                value = (bytes.fromhex(token) if re.fullmatch(r"[0-9a-fA-F]{40,}", token) and len(token) % 2 == 0
                         else base64.b64decode(token, validate=True))
            except (ValueError, binascii.Error):
                continue
            preview = value[:500].decode("utf-8", errors="replace")
            decoded.append({"line": pretty.count("\n", 0, match.start()) + 1, "preview": preview})
        lines = pretty.splitlines()
        entropy = []
        for number, line in enumerate(lines, 1):
            if len(line) < 40:
                continue
            score = -sum((count / len(line)) * math.log2(count / len(line)) for count in Counter(line).values())
            if score >= 4.5:
                entropy.append({"line": number, "bits_per_char": round(score, 2)})
            if len(entropy) == 20:
                break
        preview = "\n".join(line[:MAX_LINE_CHARS] for line in lines[:10])
        return {"ok": True, "data": {"untrusted": True, "pretty_file": file + "#pretty",
                                      "content": preview[:8000], "decoded": decoded,
                                      "high_entropy": entropy, "lines": len(lines),
                                      "truncated": len(lines) > 10 or len(preview) > 8000 or
                                                   any(len(line) > MAX_LINE_CHARS for line in lines[:10])}, "error": None}
    except (OSError, ValueError) as error:
        return {"ok": False, "data": None, "error": str(error)[:300]}


INDICATORS = {
    "url": re.compile(r"https?://[^\s\"'<>]{3,}"),
    "ip": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "child_process": re.compile(r"\bchild_process\b"),
    "eval": re.compile(r"\beval\s*\("),
    "new_function": re.compile(r"\bnew\s+Function\b"),
    "sensitive_path": re.compile(r"(?:~/|/home/[^/]+/)(?:\.npmrc|\.ssh|\.aws)\b"),
    "environment": re.compile(r"\bprocess\.env\b"),
}


def extract_indicators(package: str) -> dict:
    try:
        root = Path(package).resolve(strict=True)
        found = []
        files = 0
        truncated = False
        for path in root.rglob("*"):
            if path.suffix not in (".js", ".cjs", ".mjs", ".json", ".sh") or path.is_symlink():
                continue
            if "node_modules" in path.relative_to(root).parts:
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                truncated = True
                continue
            relative = path.relative_to(root).as_posix()
            safe = _safe_file(package, relative)
            files += 1
            if files > 100:
                break
            for number, line in enumerate(safe.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                for kind, pattern in INDICATORS.items():
                    if pattern.search(line):
                        found.append({"kind": kind, "file": relative, "lines": str(number),
                                      "preview": line[:120]})
                if len(found) >= 30:
                    break
            if len(found) >= 30:
                break
        return {"ok": True, "data": {"untrusted": True, "indicators": found,
                                      "truncated": truncated or files > 100 or len(found) >= 30}, "error": None}
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
