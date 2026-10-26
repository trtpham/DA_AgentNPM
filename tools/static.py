"""Bounded, read-only inspection of an extracted package."""

import json
import base64
import binascii
from collections import Counter
import io
import math
import re
import shlex
from pathlib import Path

MAX_FILE_BYTES = 256 * 1024
MAX_LINES = 150
MAX_LINE_CHARS = 1000
LIFECYCLE = ("preinstall", "install", "postinstall", "prepare")


def script_targets(scripts: dict) -> set[str]:
    targets = set()
    pending = list(LIFECYCLE)
    seen = set()
    while pending:
        hook = pending.pop()
        if hook in seen:
            continue
        seen.add(hook)
        lexer = shlex.shlex(scripts.get(hook, "").replace("\r\n", "\n").replace("\n", ";"),
                            posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        lexer.commenters = ""
        commands = [[]]
        for token in lexer:
            if token and set(token) <= set(";&|"):
                commands.append([])
            else:
                commands[-1].append(token)
        for command in commands:
            while command and re.fullmatch(r"[A-Za-z_]\w*=.*", command[0]):
                command.pop(0)
            if not command:
                continue
            if command[0].startswith("./"):
                targets.add(command[0].removeprefix("./"))
            if command[0] in ("npm", "pnpm", "yarn") and len(command) > 2 and command[1] in ("run", "run-script"):
                if command[2] in scripts:
                    pending.append(command[2])
            if command[0] not in ("node", "sh", "bash"):
                continue
            index = 1
            while index < len(command):
                argument = command[index]
                if argument in (("-e", "--eval") if command[0] == "node" else ("-c", "-lc")):
                    break
                if command[0] == "node" and argument in ("-r", "--require", "--import", "--loader"):
                    if index + 1 < len(command):
                        targets.add(command[index + 1].removeprefix("./"))
                    index += 2
                    continue
                if command[0] == "node" and argument.startswith(("--require=", "--import=", "--loader=")):
                    targets.add(argument.split("=", 1)[1].removeprefix("./"))
                elif not argument.startswith("-"):
                    targets.add(argument.removeprefix("./"))
                    break
                index += 1
    return targets


def _pretty_source(package: str, file: str) -> str:
    if not file.endswith((".js", ".cjs", ".mjs")):
        raise ValueError("pretty view requires JavaScript file")
    source = _safe_file(package, file).read_text(encoding="utf-8", errors="replace")
    # shortcut: regex detection is heuristic; use a JS parser if exact formatting becomes required.
    output, quote, escaped = [], None, False
    line_comment = block_comment = regex = char_class = False
    previous = ""
    index = 0
    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""
        output.append(char)
        if line_comment:
            if char == "\n":
                line_comment = False
        elif block_comment:
            if char == "*" and next_char == "/":
                output.append("/")
                index += 1
                block_comment = False
        elif quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
                previous = char
        elif regex:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "[":
                char_class = True
            elif char == "]":
                char_class = False
            elif char == "/" and not char_class:
                regex = False
                previous = char
        elif char == "/" and next_char in ("/", "*"):
            output.append(next_char)
            index += 1
            line_comment = next_char == "/"
            block_comment = next_char == "*"
        elif char in ("'", '"', "`"):
            quote = char
        elif char == "/" and ((previous and previous in "=(,:!?[>{") or
                              source[max(0, index - 10):index].rstrip().endswith("return")):
            regex = True
        else:
            if char in (";", "{", "}"):
                output.append("\n")
            if not char.isspace():
                previous = char
        index += 1
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
    "home_secret": re.compile(r"(?:os\.homedir\s*\(\s*\)|process\.env\.HOME|\bhome\b).{0,100}\.(?:npmrc|ssh|aws)\b"),
    "environment": re.compile(r"\bprocess\.env\b"),
    "network_api": re.compile(r"\b(?:fetch|https?\.request|dns\.lookup)\s*\(|\brequire\s*\(\s*['\"](?:net|https?|dns)['\"]\s*\)"),
    "decode": re.compile(r"\batob\s*\(|\bBuffer\.from\s*\([^;\n]*?,\s*['\"]base64['\"]\s*\)"),
    "hex": re.compile(r"\b(?:[0-9a-fA-F]{2}){20,}\b"),
    "base64": re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),
}

RELATIVE_REQUIRE = re.compile(r"\brequire\s*\(\s*['\"](\.{1,2}/[^'\"]+)['\"]\s*\)")
RELATIVE_IMPORT = re.compile(r"\b(?:import|export)\b[^;\n]*?['\"](\.{1,2}/[^'\"]+)['\"]")


def extract_indicators(package: str) -> dict:
    try:
        manifest = read_manifest(package)
        if not manifest["ok"]:
            raise ValueError(manifest["error"])
        scripts = manifest["data"]["scripts"]["content"]
        found = []
        seen_environment = set()

        def add(kind: str, file: str, line: int | None, snippet: str) -> None:
            if kind == "environment":
                if file in seen_environment:
                    return
                seen_environment.add(file)
            found.append({"type": kind, "file": file, "line": line, "snippet": snippet[:120]})

        truncated = False
        for hook in LIFECYCLE:
            if hook not in scripts:
                continue
            for kind, pattern in INDICATORS.items():
                if pattern.search(scripts[hook]):
                    add(kind, "package.json", manifest["data"]["script_lines"].get(hook), scripts[hook])
        pending = [(file, 0) for file in sorted(script_targets(scripts))]
        if manifest["data"]["has_binding_gyp"] and "install" not in scripts:
            pending.append(("binding.gyp", 0))
        seen = set()
        while pending and len(seen) < 100 and len(found) < 30:
            relative, depth = pending.pop(0)
            if relative in seen or "node_modules" in Path(relative).parts:
                continue
            seen.add(relative)
            try:
                safe = _safe_file(package, relative)
            except (OSError, ValueError):
                truncated = True
                continue
            if safe.suffix not in (".js", ".cjs", ".mjs", ".json", ".sh", ".gyp"):
                continue
            for number, line in enumerate(safe.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                for kind, pattern in INDICATORS.items():
                    if pattern.search(line):
                        add(kind, relative, number, line)
                if safe.suffix in (".js", ".cjs", ".mjs"):
                    for required in RELATIVE_REQUIRE.findall(line) + RELATIVE_IMPORT.findall(line):
                        if depth == 2:
                            truncated = True
                            continue
                        target = Path(relative).parent / required
                        if not target.suffix:
                            js_file = target.with_suffix(".js")
                            target = js_file if (Path(package) / js_file).is_file() else target / "index.js"
                        pending.append((target.as_posix(), depth + 1))
                if len(found) >= 30:
                    break
        return {"ok": True, "data": {"untrusted": True, "indicators": found,
                                      "truncated": truncated or bool(pending) or len(found) >= 30}, "error": None}
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
