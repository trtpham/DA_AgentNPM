"""Read-only exploration tools for an extracted package (plan Phần A: A1–A10).

Rules shared by every tool (docs/ke-hoach/KE_HOACH_TOOLS_AGENT_SANDBOX.md, Phần A):
- never import, eval or run package code, no subprocess; files are only read as bytes or text;
- every file goes through `tools.static._safe_file` (blocks `..`, absolute paths, symlinks, > 256 KB);
- `node_modules/` is skipped and directory symlinks are not followed;
- results use {"ok", "data", "error"}; package content sits under `"untrusted": true`;
- each tool has a result cap and reports `truncated` plus the reasons in `incomplete`;
- `counts_as_seen` says whether a result may count as a line the model has seen (verbatim, uncut).
"""

import base64
import binascii
import hashlib
import ipaddress
import math
import os
import posixpath
import re
import shlex
import time
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

from agent.semantics import NETWORK, TECHNIQUES, WRITE, identity_lines
from tools.static import (LIFECYCLE, MAX_FILE_BYTES, _safe_file, external_commands, install_targets,
                          read_manifest)

MAX_LIST_FILES = 300
MAX_HITS = 50
SNIPPET_CHARS = 200
MAX_TRACE_DEPTH = 4
MAX_TRACE_FILES = 100
MAX_INLINE_CHARS = 300
JS_SUFFIXES = (".js", ".cjs", ".mjs")
SHELLS = ("sh", "bash", "zsh", "node")

NODE_BUILTINS = frozenset({
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console", "constants", "crypto",
    "dgram", "diagnostics_channel", "dns", "domain", "events", "fs", "http", "http2", "https",
    "inspector", "module", "net", "os", "path", "perf_hooks", "process", "punycode", "querystring",
    "readline", "repl", "stream", "string_decoder", "sys", "timers", "tls", "trace_events", "tty",
    "url", "util", "v8", "vm", "wasi", "worker_threads", "zlib"})

# Module specifiers written as string literals: require('x'), import ... from 'x', import 'x', import('x').
SPECIFIERS = (
    re.compile(r"\brequire\s*\(\s*(['\"])([^'\"\n]+)\1\s*\)"),
    re.compile(r"\b(?:import|export)\b[^'\"\n;]*?\bfrom\s*(['\"])([^'\"\n]+)\1"),
    re.compile(r"\bimport\s*(['\"])([^'\"\n]+)\1"),
    re.compile(r"\bimport\s*\(\s*(['\"])([^'\"\n]+)\1\s*\)"),
)
# require(variable) / import(variable): the loaded module cannot be known statically.
DYNAMIC = re.compile(r"\b(?:require|import)\s*\(\s*(?!['\"\s)])")

NATIVE_MAGIC = (b"\x7fELF", b"MZ", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe",
                b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe")
KIND_BY_SUFFIX = {".js": "js", ".cjs": "js", ".mjs": "js", ".json": "json", ".sh": "shell", ".node": "native"}

# file_stats thresholds; the reasons list names every threshold a file passes.
MINIFIED_MAX_LINE = 500
MINIFIED_AVG_LINE = 200
OBFUSCATED_ESCAPE = 0.1
OBFUSCATED_HEX_IDENT = 0.1
ESCAPE = re.compile(r"\\x[0-9a-fA-F]{2}|\\u[0-9a-fA-F]{4}")
IDENTIFIER = re.compile(r"(?<![\\\w$])[A-Za-z_$][\w$]*")
HEX_IDENTIFIER = re.compile(r"_0x[0-9a-fA-F]+$")


def _ok(data: dict) -> dict:
    return {"ok": True, "data": data, "error": None}


def _fail(error: Exception) -> dict:
    return {"ok": False, "data": None, "error": str(error)[:300]}


def _walk(package: str) -> tuple[list[str], list[dict], bool]:
    """Relative POSIX paths of regular files, without following symlinks; stops after MAX_LIST_FILES."""
    root = Path(package).resolve(strict=True)
    files, skipped = [], []
    stack = [root]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as entries:
            ordered = sorted(entries, key=lambda entry: entry.name)
        for entry in reversed(ordered):  # reversed + stack pop keeps alphabetical order per level
            relative = Path(entry.path).relative_to(root).as_posix()
            if entry.is_symlink():
                skipped.append({"path": relative, "reason": "symlink not followed"})
            elif entry.is_dir(follow_symlinks=False):
                if entry.name != "node_modules":
                    stack.append(Path(entry.path))
            elif entry.is_file(follow_symlinks=False):
                if len(files) == MAX_LIST_FILES:
                    return sorted(files), skipped, True
                files.append(relative)
    return sorted(files), skipped, False


def _kind(relative: str, head: bytes) -> str:
    suffix = posixpath.splitext(relative)[1].lower()
    if head.startswith(NATIVE_MAGIC):
        return "native"
    if suffix in KIND_BY_SUFFIX:
        return KIND_BY_SUFFIX[suffix]
    if head.startswith(b"\0asm") or b"\0" in head:
        return "binary"
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as error:
        # A multi-byte character cut at the end of the sample is still text.
        if error.start < len(head) - 3:
            return "other"
    return "text"


def _module_name(spec: str) -> str:
    parts = spec.split("/")
    return "/".join(parts[:2]) if spec.startswith("@") else parts[0]


def _resolve(package: str, base_file: str, spec: str) -> str | None:
    """Relative specifier to a package file, resolved like Node (x, x.js, x.cjs, x.mjs, x.json, x/index.js)."""
    target = posixpath.normpath(posixpath.join(posixpath.dirname(base_file), spec))
    if target.startswith("..") or "node_modules" in target.split("/"):
        return None
    for candidate in (target, f"{target}.js", f"{target}.cjs", f"{target}.mjs", f"{target}.json",
                      f"{target}/index.js"):
        try:
            _safe_file(package, candidate)
        except (OSError, ValueError):
            continue
        return candidate
    return None


def _install_entries(package: str) -> list[str]:
    manifest = read_manifest(package)
    if not manifest["ok"]:
        raise ValueError(manifest["error"])
    data = manifest["data"]
    return sorted(install_targets(package, data["scripts"]["content"], data["has_binding_gyp"]))


def _trace(package: str, entries: list[str]) -> dict:
    """Breadth-first walk over the module graph from `entries`; scans JavaScript files only."""
    edges, unresolved, dynamic, incomplete = [], [], [], []
    builtins: dict[str, list[str]] = {}
    external: set[str] = set()
    visited: list[str] = []
    pending = [(entry, 0) for entry in entries]
    queued = set(entries)
    while pending:
        relative, depth = pending.pop(0)
        if len(visited) == MAX_TRACE_FILES:
            incomplete.append(f"file limit ({MAX_TRACE_FILES}) reached")
            break
        try:
            safe = _safe_file(package, relative)
        except (OSError, ValueError):
            incomplete.append(f"install source not readable: {relative}")
            continue
        visited.append(relative)
        if safe.suffix not in JS_SUFFIXES:
            continue
        found_builtins = set()
        for number, line in enumerate(safe.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if DYNAMIC.search(line):
                dynamic.append({"file": relative, "line": number})
            for pattern in SPECIFIERS:
                for match in pattern.finditer(line):
                    spec = match.group(2).strip()
                    if spec.startswith(("./", "../")) or spec in (".", ".."):
                        target = _resolve(package, relative, spec)
                        if target is None:
                            unresolved.append({"from": relative, "line": number, "spec": spec[:SNIPPET_CHARS]})
                            continue
                        edges.append({"from": relative, "line": number, "to": target, "kind": "relative"})
                        if target in queued:
                            continue
                        if depth + 1 > MAX_TRACE_DEPTH:
                            incomplete.append(f"depth limit ({MAX_TRACE_DEPTH}) at {relative}:{number}")
                            continue
                        queued.add(target)
                        pending.append((target, depth + 1))
                    elif spec.startswith("node:") or _module_name(spec) in NODE_BUILTINS:
                        name = spec.removeprefix("node:").split("/")[0]
                        found_builtins.add(name)
                        edges.append({"from": relative, "line": number, "to": name, "kind": "builtin"})
                    else:
                        name = _module_name(spec)[:SNIPPET_CHARS]
                        external.add(name)
                        edges.append({"from": relative, "line": number, "to": name, "kind": "external"})
        if found_builtins:
            builtins[relative] = sorted(found_builtins)
    return {"entries": entries, "files": visited, "edges": edges, "builtins": builtins,
            "external": sorted(external), "unresolved": unresolved, "dynamic": dynamic,
            "incomplete": incomplete}


def trace_requires(package: str, file: str | None = None) -> dict:
    """A3: module graph from `file`, or from every install entry point when `file` is None."""
    try:
        if file is not None:
            _safe_file(package, file)
        result = _trace(package, [file] if file is not None else _install_entries(package))
        incomplete = result.pop("incomplete")
        return _ok({"untrusted": True, **result, "truncated": bool(incomplete), "incomplete": incomplete[:10],
                    "counts_as_seen": False})
    except (OSError, ValueError, TypeError) as error:
        return _fail(error)


def list_files(package: str) -> dict:
    """A1: every regular file with size, line count, kind and whether an install hook reaches it."""
    try:
        paths, skipped, capped = _walk(package)
        incomplete = [f"file limit ({MAX_LIST_FILES}) reached"] if capped else []
        try:
            install_path = set(_trace(package, _install_entries(package))["files"])
        except (OSError, ValueError) as error:
            install_path = set()
            incomplete.append(f"install path unknown: {str(error)[:100]}")
        files = []
        for relative in paths:
            full = Path(package, relative)
            size = full.stat().st_size
            with full.open("rb") as stream:
                head = stream.read(4096)
            kind = _kind(relative, head)
            lines = None
            if size <= MAX_FILE_BYTES and kind not in ("native", "binary"):
                content = full.read_bytes()
                lines = content.count(b"\n") + (1 if content and not content.endswith(b"\n") else 0)
            files.append({"path": relative, "bytes": size, "lines": lines, "kind": kind,
                          "in_install_path": relative in install_path})
        return _ok({"untrusted": True, "files": files, "skipped": skipped[:20], "truncated": bool(incomplete),
                    "incomplete": incomplete, "counts_as_seen": False})
    except (OSError, ValueError, TypeError) as error:
        return _fail(error)


def search_code(package: str, text: str, case_sensitive: bool = False) -> dict:
    """A2: literal (not regex) search in text files; identity lines of package.json never match."""
    try:
        if not isinstance(text, str) or not 2 <= len(text) <= 100:
            raise ValueError("text must be a literal of 2-100 characters")
        needle = text if case_sensitive else text.lower()
        paths, _, capped = _walk(package)
        incomplete = [f"file limit ({MAX_LIST_FILES}) reached"] if capped else []
        hits = []
        for relative in paths:
            if len(hits) > MAX_HITS:
                hits.pop()  # the extra hit only proved the limit was passed
                incomplete.append(f"hit limit ({MAX_HITS}) reached")
                break
            try:
                safe = _safe_file(package, relative)
            except (OSError, ValueError):
                continue  # too large or not a plain file; list_files reports it
            raw = safe.read_bytes()
            if _kind(relative, raw[:4096]) in ("native", "binary"):
                continue
            content = raw.decode("utf-8", errors="replace")
            hidden = identity_lines(content) if relative == "package.json" else set()
            for number, line in enumerate(content.splitlines(), 1):
                if number in hidden:
                    continue
                position = (line if case_sensitive else line.lower()).find(needle)
                if position < 0:
                    continue
                cut = len(line) > SNIPPET_CHARS
                start = max(0, min(position - 80, len(line) - SNIPPET_CHARS)) if cut else 0
                hits.append({"file": relative, "line": number, "snippet": line[start:start + SNIPPET_CHARS],
                             "truncated": cut, "counts_as_seen": not cut})
                if len(hits) > MAX_HITS:
                    break
        if len(hits) > MAX_HITS:
            hits.pop()
            incomplete.append(f"hit limit ({MAX_HITS}) reached")
        return _ok({"untrusted": True, "hits": hits, "truncated": bool(incomplete), "incomplete": incomplete})
    except (OSError, ValueError, TypeError) as error:
        return _fail(error)


def _split_commands(script: str) -> list[tuple[list[str], str]]:
    """Commands of one script with the separator before each ('' first, then ';', '&&', '|', ...)."""
    lexer = shlex.shlex(script.replace("\r\n", "\n").replace("\n", ";"), posix=True, punctuation_chars=";&|")
    lexer.whitespace_split = True
    lexer.commenters = ""
    commands: list[tuple[list[str], str]] = [([], "")]
    for token in lexer:
        if token and set(token) <= set(";&|"):
            commands.append(([], token))
        else:
            commands[-1][0].append(token)
    result = []
    for argv, separator in commands:
        while argv and re.fullmatch(r"[A-Za-z_]\w*=.*", argv[0]):
            argv.pop(0)  # leading VAR=value assignments
        if argv:
            result.append((argv, separator))
    return result


def _inline_code(argv: list[str]) -> str | None:
    flags = ("-e", "--eval", "-p", "--print") if argv[0] == "node" else ("-c", "-lc")
    if argv[0] not in ("node", "sh", "bash", "zsh"):
        return None
    for index, argument in enumerate(argv[1:-1], 1):
        if argument in flags:
            return argv[index + 1][:MAX_INLINE_CHARS]
    return None


def _describe_script(package: str, script: str) -> list[dict]:
    commands = []
    for argv, separator in _split_commands(script):
        single = {"install": shlex.join(argv)}
        commands.append({
            "argv": [argument[:SNIPPET_CHARS] for argument in argv],
            "runs_file": sorted(install_targets(package, single, False)),
            "external": sorted(external_commands(single)),
            "pipes_to_shell": separator == "|" and posixpath.basename(argv[0]) in SHELLS,
            "inline_code": _inline_code(argv),
        })
    return commands


def inspect_scripts(package: str) -> dict:
    """A5: lifecycle hooks in run order, each parsed into commands, plus `npm run X` chains."""
    try:
        manifest = read_manifest(package)
        if not manifest["ok"]:
            raise ValueError(manifest["error"])
        scripts = manifest["data"]["scripts"]["content"]
        lines = manifest["data"]["script_lines"]
        order = [hook for hook in LIFECYCLE if hook in scripts]
        hooks, chains = [], []
        pending = [(hook, None) for hook in order]
        seen = set()
        while pending:
            name, parent = pending.pop(0)
            if name in seen:
                continue
            seen.add(name)
            commands = _describe_script(package, scripts[name])
            hooks.append({"hook": name, "line": lines.get(name), "chained_from": parent, "commands": commands})
            for command in commands:
                argv = command["argv"]
                if (argv[0] in ("npm", "pnpm", "yarn") and len(argv) > 2 and argv[1] in ("run", "run-script")
                        and argv[2] in scripts):
                    chains.append({"from_hook": name, "via": " ".join(argv[:3]), "to_script": argv[2]})
                    pending.append((argv[2], name))
        implicit = manifest["data"]["has_binding_gyp"] and "install" not in scripts
        return _ok({"untrusted": True, "order": order, "hooks": hooks, "chains": chains,
                    "implicit_node_gyp": implicit, "counts_as_seen": False})
    except (OSError, ValueError, TypeError) as error:
        return _fail(error)


def file_stats(package: str, file: str) -> dict:
    """A10: numeric shape of one file; hints name the thresholds they pass, never the package."""
    try:
        raw = _safe_file(package, file).read_bytes()
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        lengths = [len(line) for line in lines] or [0]
        entropy = -sum(count / len(raw) * math.log2(count / len(raw)) for count in Counter(raw).values()) if raw else 0.0
        escape_chars = sum(len(match) for match in ESCAPE.findall(text))
        identifiers = IDENTIFIER.findall(text)
        hex_identifiers = sum(1 for name in identifiers if HEX_IDENTIFIER.match(name))
        comment_lines = sum(1 for line in lines if line.lstrip().startswith(("//", "/*", "*")))
        stats = {
            "lines": len(lines),
            "max_line": max(lengths),
            "avg_line": round(sum(lengths) / len(lengths), 1),
            "entropy": round(entropy, 2),
            "escape_density": round(escape_chars / len(text), 3) if text else 0.0,
            "hex_ident_ratio": round(hex_identifiers / len(identifiers), 3) if identifiers else 0.0,
            "comment_ratio": round(comment_lines / len(lines), 3) if lines else 0.0,
        }
        minified = [reason for passed, reason in (
            (stats["max_line"] > MINIFIED_MAX_LINE, f"max_line > {MINIFIED_MAX_LINE}"),
            (stats["avg_line"] > MINIFIED_AVG_LINE, f"avg_line > {MINIFIED_AVG_LINE}")) if passed]
        obfuscated = [reason for passed, reason in (
            (stats["escape_density"] >= OBFUSCATED_ESCAPE, f"escape_density >= {OBFUSCATED_ESCAPE}"),
            (stats["hex_ident_ratio"] >= OBFUSCATED_HEX_IDENT, f"hex_ident_ratio >= {OBFUSCATED_HEX_IDENT}"))
            if passed]
        return _ok({**stats, "minified_hint": bool(minified), "obfuscated_hint": bool(obfuscated),
                    "reasons": minified + obfuscated, "counts_as_seen": False})
    except (OSError, ValueError, TypeError) as error:
        return _fail(error)


# --- shared JavaScript text helpers (heuristic, line based; no parser, nothing is executed) ----------

QUOTED = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`")
SIMPLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


def _literals(line: str) -> list[tuple[int, str, str]]:
    """(one-based column, quote, raw body) of each string literal on one line; `//` ends the scan."""
    found, index = [], 0
    while index < len(line):
        char = line[index]
        if char == "/" and line[index + 1:index + 2] == "/":
            break
        if char == "/" and line[index + 1:index + 2] == "*":
            end = line.find("*/", index + 2)
            if end < 0:
                break
            index = end + 2
            continue
        if char in "'\"`":
            start, index, escaped = index, index + 1, False
            while index < len(line):
                if escaped:
                    escaped = False
                elif line[index] == "\\":
                    escaped = True
                elif line[index] == char:
                    break
                index += 1
            found.append((start + 1, char, line[start + 1:index]))
        index += 1
    return found


def _unescape(raw: str) -> str:
    """JavaScript string escapes (\\xNN, \\uNNNN, \\u{N}, \\n ...) decoded as plain text."""
    out, index = [], 0
    while index < len(raw):
        char = raw[index]
        if char != "\\" or index + 1 == len(raw):
            out.append(char)
            index += 1
            continue
        escape = raw[index + 1]
        if escape == "x" and re.fullmatch(r"[0-9a-fA-F]{2}", raw[index + 2:index + 4]):
            out.append(chr(int(raw[index + 2:index + 4], 16)))
            index += 4
        elif escape == "u" and raw[index + 2:index + 3] == "{":
            end = raw.find("}", index + 3)
            digits = raw[index + 3:end] if end > 0 else ""
            if re.fullmatch(r"[0-9a-fA-F]{1,6}", digits) and int(digits, 16) <= 0x10FFFF:
                out.append(chr(int(digits, 16)))
                index = end + 1
            else:
                out.append(escape)
                index += 2
        elif escape == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", raw[index + 2:index + 6]):
            out.append(chr(int(raw[index + 2:index + 6], 16)))
            index += 6
        else:
            out.append(SIMPLE_ESCAPES.get(escape, escape))
            index += 2
    return "".join(out)


def _split_top(text: str, separator: str) -> list[str]:
    """Split on `separator` outside strings and brackets."""
    parts, depth, quote, escaped, current = [], 0, None, False, []
    for char in text:
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == separator and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def _clean(text: str) -> str:
    """Text safe to put in JSON/UTF-8 output (lone surrogates from \\uD800 escapes become '?')."""
    return text.encode("utf-8", "replace").decode("utf-8")


def _lines_of(package: str, file: str) -> list[str]:
    return _safe_file(package, file).read_text(encoding="utf-8", errors="replace").splitlines()


# --- A6 decode_literal -------------------------------------------------------------------------------

MAX_LITERALS = 10
MAX_PREVIEW = 500
MAX_DECODED = 64 * 1024
JS_HINT = re.compile(r"require\s*\(|\bfunction\b|=>|\beval\s*\(|child_process|\bexec\w*\s*\(")
FROM_CHAR_CODE = re.compile(r"String\.fromCharCode\(\s*((?:\d+\s*,\s*)*\d+)\s*\)")


def _describe(value: bytes | str) -> dict | None:
    if isinstance(value, bytes):
        size = len(value)
        try:
            text = value.decode("utf-8")
        except UnicodeDecodeError:
            text = None
    else:
        text, size = value, len(value.encode("utf-8", "replace"))
    if size > MAX_DECODED:
        return None
    if text is None or sum(not (char.isprintable() or char in "\n\r\t") for char in text) > len(text) // 10:
        raw = value if isinstance(value, bytes) else value.encode("utf-8", "replace")
        return {"decoded_kind": "binary", "decoded_preview": raw[:MAX_PREVIEW // 2].hex(), "bytes": size}
    return {"decoded_kind": "js" if JS_HINT.search(text) else "text",
            "decoded_preview": _clean(text[:MAX_PREVIEW]), "bytes": size}


def _decode_raw(raw: str) -> tuple[str, bytes | str] | None:
    value = _unescape(raw)
    if ESCAPE.search(raw) or "\\u{" in raw:
        return "escape", value
    compact = value.strip()
    if re.fullmatch(r"(?:[0-9a-fA-F]{2}){8,}", compact):
        return "hex", bytes.fromhex(compact)
    if len(compact) >= 16 and len(compact) % 4 == 0 and re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", compact):
        try:
            return "base64", base64.b64decode(compact, validate=True)
        except (binascii.Error, ValueError):
            pass
    if re.search(r"%[0-9A-Fa-f]{2}", value):
        decoded = unquote(value)
        if decoded != value:
            return "uri", decoded
    return None


def _line_decodes(line: str) -> list[dict]:
    literals = []
    for column, _, raw in _literals(line):
        attempt = _decode_raw(raw)
        described = _describe(attempt[1]) if attempt else None
        if described:
            literals.append({"column": column, "encoding": attempt[0], **described})
    for match in FROM_CHAR_CODE.finditer(line):
        codes = [int(number) for number in re.findall(r"\d+", match.group(1))]
        if all(code <= 0x10FFFF for code in codes):
            described = _describe("".join(map(chr, codes)))
            if described:
                literals.append({"column": match.start() + 1, "encoding": "fromCharCode", **described})
    return literals


def decode_literal(package: str, file: str, line: int) -> dict:
    """A6: decode base64 / hex / \\x / \\u / fromCharCode / %XX literals on one line. Never evaluated."""
    try:
        if type(line) is not int or line < 1:
            raise ValueError("line must be a positive integer")
        lines = _lines_of(package, file)
        if line > len(lines):
            raise ValueError("line out of range")
        if file == "package.json" and line in identity_lines("\n".join(lines)):
            raise ValueError("package.json identity line is hidden for blind review")
        literals = _line_decodes(lines[line - 1])
        return _ok({"untrusted": True, "file": file, "line": line, "literals": literals[:MAX_LITERALS],
                    "truncated": len(literals) > MAX_LITERALS, "counts_as_seen": False})
    except (OSError, ValueError, TypeError) as error:
        return _fail(error)


# --- A7 resolve_value --------------------------------------------------------------------------------

IDENTIFIER_NAME = re.compile(r"[A-Za-z_$][\w$]{0,63}")
MAX_RESOLVE_STEPS = 10
MAX_VALUES = 20
MAX_VALUE_CHARS = 300
ANY_ASSIGNMENT = re.compile(r"(?<![\w$.])(?:(?:var|let|const)\s+)?([A-Za-z_$][\w$]*)\s*(\+?=)(?![=>])\s*(.+)")


def _expression(text: str) -> str:
    """The expression at the start of `text`, up to `;` or `,` outside strings and brackets."""
    for separator in (";", ","):
        text = _split_top(text, separator)[0]
    return text.strip()


def _evaluate(expr: str, env: dict) -> tuple[str | list, str] | None:
    """Static value of string literals, + concatenation, array[index] and constant templates."""
    expr = expr.strip()
    if expr.startswith("[") and expr.endswith("]"):
        items = [item for item in _split_top(expr[1:-1], ",") if item.strip()]
        values = [_evaluate(item, env) for item in items]
        if all(value is not None and isinstance(value[0], str) for value in values):
            return [value[0] for value in values], "literal"
        return None
    terms = _split_top(expr, "+")
    if len(terms) > 1:
        parts = [_evaluate(term, env) for term in terms]
        if all(part is not None and isinstance(part[0], str) for part in parts):
            return "".join(part[0] for part in parts), "concat"
        return None
    if len(expr) >= 2 and expr[0] in "'\"" and expr[-1] == expr[0]:
        return _unescape(expr[1:-1]), "literal"
    if len(expr) >= 2 and expr[0] == expr[-1] == "`":
        pieces = re.split(r"\$\{([^{}]*)\}", expr[1:-1])
        out = []
        for index, piece in enumerate(pieces):
            if index % 2 == 0:
                out.append(_unescape(piece))
                continue
            value = _evaluate(piece, env)
            if value is None or not isinstance(value[0], str):
                return None
            out.append(value[0])
        return "".join(out), "template"
    indexed = re.fullmatch(r"([A-Za-z_$][\w$]*)\s*\[\s*(\d+)\s*\]", expr)
    if indexed and isinstance(env.get(indexed.group(1)), list):
        items = env[indexed.group(1)]
        if int(indexed.group(2)) < len(items):
            return items[int(indexed.group(2))], "index"
        return None
    if IDENTIFIER_NAME.fullmatch(expr) and isinstance(env.get(expr), str):
        return env[expr], "literal"
    return None


def _short(value: str | list) -> str | list:
    if isinstance(value, list):
        return [_clean(item[:MAX_VALUE_CHARS]) for item in value[:MAX_VALUES]]
    return _clean(value[:MAX_VALUE_CHARS])


def resolve_value(package: str, file: str, name: str) -> dict:
    """A7: assignments of one identifier and the values computable from string/array literals."""
    try:
        if not isinstance(name, str) or not IDENTIFIER_NAME.fullmatch(name):
            raise ValueError("name must be a JavaScript identifier")
        lines = _lines_of(package, file)
        env: dict[str, str | list] = {}
        assignments, values, incomplete = [], [], []
        for number, line in enumerate(lines, 1):
            if incomplete:
                break
            # Every `X = …` / `X += …` updates the constants other values may refer to.
            for match in ANY_ASSIGNMENT.finditer(line):
                assigned, operator, expr = match.group(1), match.group(2), _expression(match.group(3))
                if assigned == name and len(assignments) == MAX_RESOLVE_STEPS:
                    incomplete.append(f"step limit ({MAX_RESOLVE_STEPS}) reached")
                    break
                result = _evaluate(expr, env)
                if result is not None and operator == "+=":
                    previous = env.get(assigned)
                    result = ((previous + result[0], "concat")
                              if isinstance(previous, str) and isinstance(result[0], str) else None)
                if result is not None:
                    env[assigned] = result[0]
                else:
                    env.pop(assigned, None)  # a value that cannot be computed hides the previous one
                if assigned != name:
                    continue
                assignments.append({"line": number, "expr": _clean(expr[:SNIPPET_CHARS])})
                if result is not None and len(values) < MAX_VALUES:
                    values.append({"line": number, "value": _short(result[0]), "method": result[1]})
        return _ok({"untrusted": True, "file": file, "name": name, "assignments": assignments, "values": values,
                    "truncated": bool(incomplete), "incomplete": incomplete, "counts_as_seen": False})
    except (OSError, ValueError, TypeError) as error:
        return _fail(error)


# --- A4 trace_flow -----------------------------------------------------------------------------------

MAX_FLOWS = 30
MAX_POINTS = 50
TAINT_PASSES = 5
# Source and sink signs reuse the L3 vocabulary (agent.semantics) where it is call-shaped.
SOURCE_KINDS = (
    ("secret_file", re.compile(TECHNIQUES["read-secret-file"], re.I)),
    ("env", re.compile(r"\bprocess\.env\b")),
    ("home_path", re.compile(r"\bhomedir\s*\(|process\.env\.(?:HOME|USERPROFILE)\b|['\"`]~/")),
    ("file_read", re.compile(r"\breadFileSync\b|\breadFile\s*\(|\bcreateReadStream\b|\breaddirSync\b")),
    ("network_input", re.compile(r"\.on\s*\(\s*['\"](?:data|end)['\"]")),
)
ENV_ACCESS = re.compile(r"\bprocess\.env\b")
NETWORK_SINK = re.compile(NETWORK)
PROCESS_SINK = re.compile(r"\b(?:exec|execSync|execFile|execFileSync|spawn|spawnSync|fork)\s*\(")
EVAL_SINK = re.compile(r"\beval\s*\(|\bnew\s+Function\b|\bFunction\s*\(|\bvm\.\w+\s*\(")
WRITE_SINK = re.compile(WRITE)
OUTSIDE = re.compile(r"homedir|tmpdir|/etc/|\.bashrc|\.profile|\.zshrc|crontab|AppData|Startup|LaunchAgents|systemd")
MODULE_LINE = re.compile(r"\brequire\s*\(\s*['\"]|^\s*(?:import|export)\b")
ASSIGNMENT = re.compile(r"(?<![\w$.])(?:(?:var|let|const)\s+)?([A-Za-z_$][\w$]*)\s*(?:\+|\|\||\?\?)?=(?![=>])\s*(.*)")


TOKEN = re.compile(r"(?<![\w$.])[A-Za-z_$][\w$]*")  # identifiers, not `.property` accesses
MAX_VIA = 5
FLOW_SECONDS = 2.0  # per file; a slower analysis returns what it has with `truncated`


def _blocks(lines: list[str]) -> tuple[list[int], dict[int, int]]:
    """Innermost `{` block id at the start of each line, and each block's parent (0 = top level)."""
    parent, stack, at_start, next_id = {0: 0}, [0], [], 1
    for line in lines:
        at_start.append(stack[-1])
        code = QUOTED.sub("''", line).split("//", 1)[0]
        for char in code:
            if char == "{":
                parent[next_id] = stack[-1]
                stack.append(next_id)
                next_id += 1
            elif char == "}" and len(stack) > 1:
                stack.pop()
    return at_start, parent


def _inside(block: int, ancestor: int, parent: dict[int, int]) -> bool:
    while True:
        if block == ancestor:
            return True
        if block == 0:
            return False
        block = parent[block]


def trace_flow(package: str, file: str) -> dict:
    """A4: sources, sinks and source-to-sink flows in one JavaScript file (line heuristic)."""
    try:
        if not file.endswith(JS_SUFFIXES):
            raise ValueError("trace_flow needs a JavaScript file")
        lines = _lines_of(package, file)
        code = [QUOTED.sub(lambda match: match.group(0) if OUTSIDE.search(match.group(0)) or
                           SOURCE_KINDS[0][1].search(match.group(0)) else "''", line) for line in lines]
        sources = []
        for number, line in enumerate(lines, 1):
            if MODULE_LINE.search(line):
                continue
            for kind, pattern in SOURCE_KINDS:
                # The L3 secret-file signs include `.env` files; `process.env` is the env kind instead.
                subject = ENV_ACCESS.sub("", line) if kind == "secret_file" else line
                if pattern.search(subject):
                    sources.append({"kind": kind, "line": number, "expr": _clean(line.strip()[:SNIPPET_CHARS])})
        # Line -> its first source kind (SOURCE_KINDS order); reversed so the first one is written last.
        source_lines = {item["line"]: item["kind"] for item in reversed(sources)}
        # Statements `X = …`: the right side may continue over lines until its brackets close (max 20).
        statements = []
        for number, line in enumerate(lines, 1):
            match = ASSIGNMENT.search(code[number - 1])
            if not match or MODULE_LINE.search(line):
                continue
            span, depth = [number], 0
            for offset in range(number, min(len(lines), number + 20) + 1):
                text = code[offset - 1] if offset > number else match.group(2)
                depth += sum(text.count(char) for char in "([{") - sum(text.count(char) for char in ")]}")
                if offset > number:
                    span.append(offset)
                if depth <= 0:
                    break
            statements.append((match.group(1), span))
        # Identifier tokens of each line, computed once: lookups below are set operations, so the
        # cost grows with the file size instead of (statements x variables) regex searches.
        tokens = [set(TOKEN.findall(line)) for line in code]
        deadline = time.monotonic() + FLOW_SECONDS
        incomplete: list[str] = []
        # Taint: variable -> (source line, source kind, via names). A variable is also a network
        # handle when its right side opens a connection (`const req = https.request(...)`).
        taint: dict[str, tuple[int, str, list[str]]] = {}
        handles: set[str] = set()
        for _ in range(TAINT_PASSES):
            changed = False
            for name, span in statements:
                if name in taint:
                    continue
                if time.monotonic() > deadline:
                    break
                for offset in span:
                    if offset in source_lines:
                        taint[name] = (offset, source_lines[offset], [name])
                        break
                    used = sorted((taint[other][0], other) for other in tokens[offset - 1] & taint.keys() if other != name)
                    if used:
                        origin = taint[used[0][1]]
                        taint[name] = (origin[0], origin[1], (origin[2] + [name])[-MAX_VIA:])
                        break
                changed |= name in taint
            if not changed:
                break
        for name, span in statements:
            if NETWORK_SINK.search(code[span[0] - 1]) and "(" in code[span[0] - 1]:
                handles.add(name)
        handle_call = (re.compile(r"(?<![\w$.])(?:" + "|".join(map(re.escape, sorted(handles))) +
                                  r")\.(?:end|write|send)\s*\(") if handles else None)
        home_vars = {name for name, origin in taint.items() if origin[1] == "home_path"}
        sinks = []
        for number, line in enumerate(code, 1):
            if MODULE_LINE.search(lines[number - 1]):
                continue
            outside_var = bool(tokens[number - 1] & home_vars)
            if handle_call and handle_call.search(line) or NETWORK_SINK.search(line) and "(" in line:
                kind = "network"
            elif PROCESS_SINK.search(line):
                kind = "process"
            elif EVAL_SINK.search(line):
                kind = "eval"
            elif WRITE_SINK.search(line):
                kind = "write_outside" if OUTSIDE.search(line) or outside_var else "write_package"
            else:
                continue
            sinks.append({"kind": kind, "line": number, "expr": _clean(lines[number - 1].strip()[:SNIPPET_CHARS])})
        block_at, parent = _blocks(lines)
        flows, seen_pairs = [], set()

        def add(source_line: int, source_kind: str, sink: dict, via: list[str], confidence: str) -> None:
            if (source_line, sink["line"]) in seen_pairs or len(flows) > MAX_FLOWS:
                return
            seen_pairs.add((source_line, sink["line"]))
            flows.append({"source_line": source_line, "source_kind": source_kind, "sink_line": sink["line"],
                          "sink_kind": sink["kind"], "via": via, "confidence": confidence})

        scoped = [item for item in sources if block_at[item["line"] - 1]]  # top-level sources never pair by block
        for sink in sinks:
            if len(flows) > MAX_FLOWS:
                break
            if time.monotonic() > deadline:
                incomplete.append(f"time limit ({FLOW_SECONDS:g} s) reached at line {sink['line']}")
                break
            if sink["line"] in source_lines and source_lines[sink["line"]] != "network_input":
                add(sink["line"], source_lines[sink["line"]], sink, [], "direct")
            for name in sorted(tokens[sink["line"] - 1] & taint.keys()):
                origin, kind, via = taint[name]
                if origin != sink["line"]:
                    add(origin, kind, sink, via, "via_variable")
            for item in scoped:
                if item["line"] >= sink["line"]:
                    break  # sources are in line order
                if _inside(block_at[sink["line"] - 1], block_at[item["line"] - 1], parent):
                    add(item["line"], item["kind"], sink, [], "same_function")
        if len(flows) > MAX_FLOWS:
            incomplete.append(f"flow limit ({MAX_FLOWS}) reached")
        return _ok({"untrusted": True, "file": file, "sources": sources[:MAX_POINTS], "sinks": sinks[:MAX_POINTS],
                    "flows": flows[:MAX_FLOWS], "truncated": bool(incomplete), "incomplete": incomplete,
                    "counts_as_seen": False})
    except (OSError, ValueError, TypeError) as error:
        return _fail(error)


# --- A8 list_endpoints -------------------------------------------------------------------------------

MAX_ENDPOINTS = 50
URL = re.compile(r"\b(?:https?|wss?|ftp)://[^\s'\"`<>)\]]+")
IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
HOST_FIELD = re.compile(r"\bhost(?:name)?\s*:\s*(['\"])([^'\"]+)\1")
PORT_NEAR = re.compile(r"\bport\s*[:=]\s*(\d{1,5})\b|\.connect\s*\(\s*(\d{1,5})\s*,")
DNS_CALL = re.compile(r"\bdns\.\w+\s*\(\s*(['\"`])(.*?)\1")
DOCUMENTATION = tuple(ipaddress.ip_network(net) for net in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24",
                                                             "2001:db8::/32"))


def _ip_class(host: str) -> str | None:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return None
    if address.is_loopback:
        return "loopback"
    if any(address in network for network in DOCUMENTATION):
        return "documentation"
    return "private" if address.is_private or address.is_link_local else "public"


def _endpoints_in(text: str, built: str) -> list[dict]:
    """Endpoints in one piece of text; structure only, no host is trusted or distrusted by name."""
    found, covered = [], []
    for match in URL.finditer(text):
        value = match.group(0)
        covered.append(match.span())
        templated = "${" in value
        try:
            parts = urlsplit(value)
            host, port = parts.hostname, parts.port
        except ValueError:
            host, port = None, None
        found.append({"value": value, "scheme": value.split(":", 1)[0], "host": host, "port": port,
                      "built": "template" if templated and built == "literal" else built})
    for match in DNS_CALL.finditer(text):
        name = match.group(2)
        if "${" in name:
            suffix = name.rsplit("}", 1)[-1].lstrip(".")
            host, kind = (f"*.{suffix}" if suffix else None), "template"
        else:
            host, kind = name, built
        if host:
            covered.append(match.span())
            found.append({"value": name, "scheme": "dns", "host": host, "port": None, "built": kind})
    port_match = PORT_NEAR.search(text)
    near_port = int(next(group for group in port_match.groups() if group)) if port_match else None
    hosts = [(match.group(2), match.span()) for match in HOST_FIELD.finditer(text)]
    hosts += [(match.group(1), match.span()) for match in IPV4.finditer(text)]
    seen_hosts = set()
    for host, span in hosts:
        if any(start <= span[0] < end for start, end in covered) or host in seen_hosts:
            continue
        if IPV4.fullmatch(host) and _ip_class(host) is None:
            continue  # e.g. a version number like 1.2.3.400
        seen_hosts.add(host)
        tail = re.match(r":(\d{1,5})\b", text[span[1]:])
        found.append({"value": host, "scheme": None, "host": host,
                      "port": int(tail.group(1)) if tail else near_port, "built": built})
    for item in found:
        item["is_ip"] = item["host"] is not None and _ip_class(item["host"]) is not None
        item["ip_class"] = _ip_class(item["host"]) if item["host"] else None
    return found


def list_endpoints(package: str) -> dict:
    """A8: URLs, IPs, host/port fields and DNS names on the install path, including decoded literals."""
    try:
        manifest = read_manifest(package)
        if not manifest["ok"]:
            raise ValueError(manifest["error"])
        traced = _trace(package, _install_entries(package))
        incomplete = list(traced["incomplete"])
        raw_manifest = _lines_of(package, "package.json")
        targets = [("package.json", [line for line in sorted(set(manifest["data"]["script_lines"].values()))])]
        targets += [(file, None) for file in traced["files"] if file.endswith(JS_SUFFIXES + (".json", ".sh"))
                    and file != "package.json"]
        endpoints, keys = [], set()
        for file, only in targets:
            lines = raw_manifest if file == "package.json" else _lines_of(package, file)
            for number, line in enumerate(lines, 1):
                if only is not None and number not in only:
                    continue
                items = _endpoints_in(line, "literal")
                for literal in _line_decodes(line):
                    if literal["decoded_kind"] != "binary":
                        items += _endpoints_in(literal["decoded_preview"], "decoded")
                for item in items:
                    key = (file, number, item["host"], item["port"], item["built"])
                    if key in keys:
                        continue
                    keys.add(key)
                    item["value"] = _clean(item["value"][:SNIPPET_CHARS])
                    item["counts_as_seen"] = (item["built"] == "literal" and len(line) <= 1000)
                    endpoints.append({"file": file, "line": number, **item})
        if len(endpoints) > MAX_ENDPOINTS:
            incomplete.append(f"endpoint limit ({MAX_ENDPOINTS}) reached")
        return _ok({"untrusted": True, "endpoints": endpoints[:MAX_ENDPOINTS], "truncated": bool(incomplete),
                    "incomplete": incomplete[:10]})
    except (OSError, ValueError, TypeError) as error:
        return _fail(error)


# --- A9 inspect_binary -------------------------------------------------------------------------------

MAX_BINARY_BYTES = 8 * 1024 * 1024
MAX_STRINGS = 30
BINARY_FORMATS = ((b"\x7fELF", "ELF"), (b"MZ", "PE"), (b"\xfe\xed\xfa\xce", "Mach-O"), (b"\xfe\xed\xfa\xcf", "Mach-O"),
                  (b"\xce\xfa\xed\xfe", "Mach-O"), (b"\xcf\xfa\xed\xfe", "Mach-O"), (b"\xca\xfe\xba\xbe", "Mach-O"),
                  (b"\0asm", "wasm"), (b"!<arch>\n", "archive"), (b"PK\x03\x04", "archive"), (b"\x1f\x8b", "archive"))
INTERESTING_STRING = re.compile(r"://|^/[\w.-]|^~/|^[A-Za-z]:\\|\\\\|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}/")


def _safe_any_size(package: str, file: str) -> Path:
    """Same path rules as tools.static._safe_file without its 256 KB text limit."""
    root = Path(package).resolve(strict=True)
    target = root / file
    if target.is_symlink() or not target.resolve(strict=True).is_relative_to(root):
        raise ValueError("file escapes package directory")
    if not target.is_file():
        raise ValueError("file missing")
    return target


def inspect_binary(package: str, file: str) -> dict:
    """A9: format by magic bytes, size, sha256 and URL/path-like strings. The file is never loaded or run."""
    try:
        target = _safe_any_size(package, file)
        size = target.stat().st_size
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            head = stream.read(MAX_BINARY_BYTES)
            digest.update(head)
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        file_format = next((name for magic, name in BINARY_FORMATS if head.startswith(magic)), "unknown")
        strings = []
        for match in re.finditer(rb"[\x20-\x7e]{6,}", head):
            text = match.group().decode("ascii")
            if INTERESTING_STRING.search(text):
                strings.append({"offset": match.start(), "text": text[:SNIPPET_CHARS]})
                if len(strings) == MAX_STRINGS:
                    break
        incomplete = [f"only the first {MAX_BINARY_BYTES} bytes were scanned"] if size > MAX_BINARY_BYTES else []
        return _ok({"untrusted": True, "file": file, "format": file_format, "bytes": size,
                    "sha256": digest.hexdigest(), "strings": strings, "truncated": bool(incomplete),
                    "incomplete": incomplete, "counts_as_seen": False})
    except (OSError, ValueError, TypeError) as error:
        return _fail(error)
