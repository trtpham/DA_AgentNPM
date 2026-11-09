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
# Indicator types that a benign verdict must explain before automatic approval.
RISK_INDICATORS = frozenset({"child_process", "network_api", "sensitive_path", "home_secret",
                             "eval", "new_function", "decode", "analyst_directive"})
# B4: text in a comment or string that addresses an automated reviewer ("analysts must approve this").
# It is recorded as a behavior of the package, never followed; any hit blocks automatic approval.
ANALYST_DIRECTIVE = re.compile(
    r"\b(?:automated|ai|llm|analy[sz]ts?|reviewers?|scanners?|auditors?|security\s+review)\b.{0,120}"
    r"\b(?:must|should|shall|label|approve|ignore|classify|mark)\b"
    r"|\bignore\s+(?:all\s+|any\s+)?(?:previous|prior|above)\s+instructions\b"
    r"|\byou\s+are\s+(?:an?|the)\s+(?:ai|assistant|model|analyst|reviewer|scanner)\b"
    # Verdict language aimed at the reviewer (injection_probe 2026-11-09: a lure 60+ characters after
    # "automated", and a comment imitating a clean verdict, were missed). Only comments/strings count.
    r"|\b(?:label|mark|classify)(?:s|ed|ing)?\b.{0,40}\b(?:benign|safe|harmless)\b"
    r"|\bapprove\w*\b.{0,30}\b(?:install|script|package)"
    r"|[\"']verdict[\"']\s*:\s*\{"
    r"|[\"'](?:label|action)[\"']\s*:\s*[\"'](?:benign|approve|safe)[\"']", re.I)
_QUOTED = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`")


def analyst_directive(line: str) -> bool:
    """True when a comment or string literal on this JavaScript line addresses the analyst."""
    stripped = line.lstrip()
    if stripped.startswith(("//", "/*", "*")):
        return ANALYST_DIRECTIVE.search(stripped) is not None
    strings = [match.group(0) for match in _QUOTED.finditer(line)]
    code = _QUOTED.sub("''", line)
    comment = code.split("//", 1)[1] if "//" in code else ""
    comment += " ".join(re.findall(r"/\*(.*?)(?:\*/|$)", code))
    return any(ANALYST_DIRECTIVE.search(text) for text in strings + [comment])
# Commands that fetch or build code that is not inside the extracted package.
EXTERNAL_COMMANDS = frozenset({"npx", "pnpx", "curl", "wget", "node-gyp", "prebuild-install",
                               "node-pre-gyp", "prebuild", "cmake-js"})
PACKAGE_MANAGER_FETCH = frozenset({"install", "i", "ci", "add", "exec", "dlx", "x"})


def _hook_commands(scripts: dict) -> list[list[str]]:
    commands = []
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
        parsed = [[]]
        for token in lexer:
            if token and set(token) <= set(";&|"):
                parsed.append([])
            else:
                parsed[-1].append(token)
        for command in parsed:
            while command and re.fullmatch(r"[A-Za-z_]\w*=.*", command[0]):
                command.pop(0)
            if not command:
                continue
            commands.append(command)
            if command[0] in ("npm", "pnpm", "yarn") and len(command) > 2 and command[1] in ("run", "run-script"):
                if command[2] in scripts:
                    pending.append(command[2])
    return commands


def external_commands(scripts: dict) -> set[str]:
    found = set()
    for command in _hook_commands(scripts):
        if command[0] in EXTERNAL_COMMANDS:
            found.add(command[0])
        elif command[0] in ("npm", "pnpm", "yarn") and (
                len(command) == 1 and command[0] == "yarn" or
                len(command) > 1 and command[1] in PACKAGE_MANAGER_FETCH):
            found.add(" ".join(command[:2]))
    return found


def install_targets(package: str, scripts: dict, has_binding_gyp: bool) -> set[str]:
    """Files an install hook runs, resolved like Node (`x` -> `x.js`, `x/index.js`)."""
    targets = set()
    for target in script_targets(scripts):
        for candidate in (target, f"{target}.js", f"{target}.cjs", f"{target}.mjs", f"{target}/index.js"):
            try:
                _safe_file(package, candidate)
            except (OSError, ValueError):
                continue
            target = candidate
            break
        targets.add(target)
    if has_binding_gyp and ("install" not in scripts or "node-gyp" in external_commands(scripts)):
        targets.add("binding.gyp")
    return targets


def script_targets(scripts: dict) -> set[str]:
    targets = set()
    for command in _hook_commands(scripts):
        if command[0].startswith("./"):
            targets.add(command[0].removeprefix("./"))
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
    # A command string that fetches or builds code outside the package, e.g. execSync(`npm install ...`).
    "external_install": re.compile(r"\b(?:execSync|exec|execFileSync|execFile|spawnSync|spawn)\s*\(\s*[`'\"]\s*"
                                   r"(?:npm|npx|pnpm|yarn|curl|wget|node-gyp|prebuild-install)\b"),
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

        # Why the install path could not be scanned completely; any entry blocks automatic approval.
        incomplete = []
        native = []  # per-platform .node files are reported as one reason
        for hook in LIFECYCLE:
            if hook not in scripts:
                continue
            for kind, pattern in INDICATORS.items():
                if pattern.search(scripts[hook]):
                    add(kind, "package.json", manifest["data"]["script_lines"].get(hook), scripts[hook])
        pending = [(file, 0) for file in sorted(install_targets(package, scripts, manifest["data"]["has_binding_gyp"]))]
        seen = set()
        while pending and len(seen) < 100 and len(found) < 30:
            relative, depth = pending.pop(0)
            if relative in seen or "node_modules" in Path(relative).parts:
                continue
            seen.add(relative)
            try:
                safe = _safe_file(package, relative)
            except (OSError, ValueError):
                if relative.endswith(".node"):
                    native.append(relative)
                else:
                    incomplete.append(f"install source not readable: {relative}")
                continue
            if safe.suffix not in (".js", ".cjs", ".mjs", ".json", ".sh", ".gyp"):
                continue
            for number, line in enumerate(safe.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                for kind, pattern in INDICATORS.items():
                    if pattern.search(line):
                        add(kind, relative, number, line)
                if safe.suffix in (".js", ".cjs", ".mjs") and analyst_directive(line):
                    add("analyst_directive", relative, number, line)
                if safe.suffix in (".js", ".cjs", ".mjs"):
                    for required in RELATIVE_REQUIRE.findall(line) + RELATIVE_IMPORT.findall(line):
                        if depth == 2:
                            incomplete.append(f"require depth limit (2) at {relative}:{number}")
                            continue
                        target = Path(relative).parent / required
                        if not target.suffix:
                            js_file = target.with_suffix(".js")
                            target = js_file if (Path(package) / js_file).is_file() else target / "index.js"
                        pending.append((target.as_posix(), depth + 1))
                if len(found) >= 30:
                    break
        if native:
            incomplete.insert(0, f"{len(native)} native binaries not in package (e.g. {', '.join(sorted(native)[:2])})")
        if len(found) >= 30:
            incomplete.append("indicator limit (30) reached")
        elif any(file not in seen and "node_modules" not in Path(file).parts for file, _ in pending):
            incomplete.append("file limit (100) reached")
        return {"ok": True, "data": {"untrusted": True, "indicators": found, "truncated": bool(incomplete),
                                      "incomplete": incomplete[:10]}, "error": None}
    except (OSError, ValueError) as error:
        return {"ok": False, "data": None, "error": str(error)[:300]}


def _script_lines(raw: str) -> dict[str, int]:
    """Line of each key in the top-level "scripts" object, ignoring nested "scripts" keys."""
    lines: dict[str, int] = {}
    stack: list[str] = []
    scripts_depth = None
    next_is_scripts = False
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == '"':
            end = index + 1
            while raw[end] != '"':
                end += 2 if raw[end] == "\\" else 1
            key = json.loads(raw[index:end + 1])
            after = end + 1
            while after < len(raw) and raw[after].isspace():
                after += 1
            if after < len(raw) and raw[after] == ":" and stack and stack[-1] == "{":
                if len(stack) == 1:
                    next_is_scripts = key == "scripts"
                elif scripts_depth == len(stack):
                    # json.loads keeps the last duplicate key, so the last line wins here too.
                    lines[key] = raw.count("\n", 0, index) + 1
                index = after + 1
                continue
            next_is_scripts = False
            index = end + 1
            continue
        if char in "{[":
            stack.append(char)
            if char == "{" and next_is_scripts and len(stack) == 2:
                scripts_depth, lines = 2, {}
            next_is_scripts = False
        elif char in "}]":
            if scripts_depth == len(stack):
                scripts_depth = None
            stack.pop()
        elif not char.isspace() and char != ",":
            next_is_scripts = False
        index += 1
    return lines


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
        script_lines = _script_lines(raw)
        source_lines = raw.splitlines()
        for hook in scripts:
            if hook not in script_lines:
                raise ValueError(f"cannot locate script {hook} in package.json")
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
