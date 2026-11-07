"""Read-only exploration tools for an extracted package (plan Phần A: A1, A2, A3, A5, A10).

Rules shared by every tool (docs/tien-do/KE_HOACH_TOOLS_AGENT_SANDBOX.md, Phần A):
- never import, eval or run package code, no subprocess; files are only read as bytes or text;
- every file goes through `tools.static._safe_file` (blocks `..`, absolute paths, symlinks, > 256 KB);
- `node_modules/` is skipped and directory symlinks are not followed;
- results use {"ok", "data", "error"}; package content sits under `"untrusted": true`;
- each tool has a result cap and reports `truncated` plus the reasons in `incomplete`;
- `counts_as_seen` says whether a result may count as a line the model has seen (verbatim, uncut).
"""

import math
import os
import posixpath
import re
import shlex
from collections import Counter
from pathlib import Path

from agent.semantics import identity_lines
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
