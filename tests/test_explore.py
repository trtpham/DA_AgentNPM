import json
import os
from pathlib import Path

import pytest

from tools.explore import (MAX_HITS, MAX_LIST_FILES, decode_literal, file_stats, inspect_binary, inspect_scripts,
                           list_endpoints, list_files, resolve_value, search_code, trace_flow,
                           trace_requires)

CORPUS = Path(__file__).parent / "fixtures" / "corpus"
PACKAGES = Path(__file__).parent / "fixtures" / "packages"


def _package(tmp_path: Path, scripts: dict, files: dict[str, str]) -> str:
    (tmp_path / "package.json").write_text(json.dumps(
        {"name": "explore-fixture", "version": "1.0.0", "scripts": scripts}, indent=2), encoding="utf-8")
    for name, content in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(content, encoding="utf-8")
    return str(tmp_path)


# A1 list_files

def test_list_files_marks_install_path_of_multi_file_package():
    result = list_files(str(CORPUS / "multi-file-exfil"))
    assert result["ok"] and result["data"]["untrusted"] and not result["data"]["truncated"]
    files = {entry["path"]: entry for entry in result["data"]["files"]}
    assert set(files) == {"package.json", "lib/index.js", "lib/util/collect.js", "lib/util/send.js"}
    assert all(files[name]["in_install_path"] for name in files if name.startswith("lib/"))
    assert files["lib/index.js"] == {"path": "lib/index.js", "bytes": files["lib/index.js"]["bytes"],
                                     "lines": 3, "kind": "js", "in_install_path": True}
    assert files["package.json"]["kind"] == "json"


def test_list_files_kind_uses_magic_bytes_not_names(tmp_path):
    package = _package(tmp_path, {}, {"README.md": "hello\n"})
    (tmp_path / "prebuilt.bin").write_bytes(b"\x7fELF" + b"\0" * 60)
    (tmp_path / "data.dat").write_bytes(b"\x01\x00\x02")
    (tmp_path / "node_modules" / "dep").mkdir(parents=True)
    (tmp_path / "node_modules" / "dep" / "x.js").write_text("x", encoding="utf-8")
    files = {entry["path"]: entry for entry in list_files(package)["data"]["files"]}
    assert files["prebuilt.bin"]["kind"] == "native" and files["prebuilt.bin"]["lines"] is None
    assert files["data.dat"]["kind"] == "binary"
    assert files["README.md"]["kind"] == "text" and files["README.md"]["lines"] == 1
    assert not any(name.startswith("node_modules") for name in files)


def test_list_files_skips_symlinks_with_reason(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    package_dir = tmp_path / "pkg"
    package_dir.mkdir()
    package = _package(package_dir, {}, {})
    try:
        os.symlink(outside, package_dir / "link.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need extra rights on this system")
    result = list_files(package)["data"]
    assert [entry["path"] for entry in result["files"]] == ["package.json"]
    assert result["skipped"] == [{"path": "link.txt", "reason": "symlink not followed"}]


def test_list_files_caps_file_count(tmp_path):
    package = _package(tmp_path, {}, {f"f{i:03}.txt": "x" for i in range(MAX_LIST_FILES + 5)})
    result = list_files(package)["data"]
    assert len(result["files"]) == MAX_LIST_FILES and result["truncated"]
    assert result["incomplete"] == [f"file limit ({MAX_LIST_FILES}) reached"]


def test_list_files_missing_package_is_an_error_not_exception(tmp_path):
    result = list_files(str(tmp_path / "missing"))
    assert result["ok"] is False and result["data"] is None and result["error"]


# A2 search_code

def test_search_code_finds_literal_lines():
    result = search_code(str(CORPUS / "twin-evil"), "token")
    assert result["ok"] and result["data"]["untrusted"]
    assert [(hit["file"], hit["line"]) for hit in result["data"]["hits"]] == [("setup.js", 8), ("setup.js", 9)]
    assert all(hit["counts_as_seen"] for hit in result["data"]["hits"])


def test_search_code_never_matches_identity_lines():
    package = str(CORPUS / "twin-evil")
    assert search_code(package, "probe-twin-b")["data"]["hits"] == []
    assert search_code(package, "Build helper")["data"]["hits"] == []
    assert [hit["line"] for hit in search_code(package, "postinstall")["data"]["hits"]] == [6]


def test_search_code_is_literal_and_case_option(tmp_path):
    package = _package(tmp_path, {}, {"a.js": "const re = /a.*b/;\nconst Token = 1;\n"})
    assert [hit["line"] for hit in search_code(package, "a.*b")["data"]["hits"]] == [1]
    assert search_code(package, "(((")["data"]["hits"] == []
    assert len(search_code(package, "token")["data"]["hits"]) == 1
    assert search_code(package, "token", case_sensitive=True)["data"]["hits"] == []


@pytest.mark.parametrize("text", ["x", "y" * 101, None])
def test_search_code_rejects_bad_text(tmp_path, text):
    result = search_code(_package(tmp_path, {}, {}), text)
    assert result["ok"] is False and "2-100" in result["error"]


def test_search_code_cut_line_does_not_count_as_seen(tmp_path):
    package = _package(tmp_path, {}, {"min.js": "a" * 500 + "needle" + "b" * 500 + "\nneedle short\n"})
    hits = search_code(package, "needle")["data"]["hits"]
    assert hits[0]["truncated"] and not hits[0]["counts_as_seen"]
    assert "needle" in hits[0]["snippet"] and len(hits[0]["snippet"]) == 200
    assert hits[1]["counts_as_seen"] and hits[1]["snippet"] == "needle short"


def test_search_code_caps_hits(tmp_path):
    (tmp_path / "over").mkdir()
    (tmp_path / "exact").mkdir()
    package = _package(tmp_path / "over", {}, {"a.js": "hit\n" * (MAX_HITS + 10)})
    result = search_code(package, "hit")["data"]
    assert len(result["hits"]) == MAX_HITS and result["truncated"]
    exact = search_code(_package(tmp_path / "exact", {}, {"a.js": "hit\n" * MAX_HITS}), "hit")["data"]
    assert len(exact["hits"]) == MAX_HITS and not exact["truncated"]


# A3 trace_requires

def test_trace_requires_follows_relative_chain_and_lists_builtins():
    result = trace_requires(str(CORPUS / "multi-file-exfil"))
    assert result["ok"] and not result["data"]["truncated"] and result["data"]["counts_as_seen"] is False
    data = result["data"]
    assert data["entries"] == ["lib/index.js"]
    relative = [(edge["from"], edge["line"], edge["to"]) for edge in data["edges"] if edge["kind"] == "relative"]
    assert relative == [("lib/index.js", 1, "lib/util/collect.js"), ("lib/index.js", 2, "lib/util/send.js")]
    assert data["builtins"] == {"lib/util/collect.js": ["fs", "os", "path"], "lib/util/send.js": ["dns"]}
    assert data["external"] == [] and data["unresolved"] == [] and data["dynamic"] == []


def test_trace_requires_reports_dynamic_require():
    data = trace_requires(str(CORPUS / "hex-obfuscated"))["data"]
    assert data["dynamic"] == [{"file": "i.js", "line": 2}]


def test_trace_requires_external_unresolved_esm_and_single_file(tmp_path):
    package = _package(tmp_path, {"install": "node a.js"}, {
        "a.js": "import x from 'left-pad';\nimport '@scope/tool/sub';\nrequire('./missing');\n"
                "const p = require('fs/promises');\nrequire('../../escape');\nimport('./b.mjs');\n",
        "b.mjs": "export * from './c';\n",
        "c.js": "module.exports = 1;\n"})
    data = trace_requires(package)["data"]
    assert data["external"] == ["@scope/tool", "left-pad"]
    assert data["builtins"] == {"a.js": ["fs"]}
    assert [item["spec"] for item in data["unresolved"]] == ["./missing", "../../escape"]
    assert data["files"] == ["a.js", "b.mjs", "c.js"]
    single = trace_requires(package, "b.mjs")["data"]
    assert single["entries"] == ["b.mjs"] and single["files"] == ["b.mjs", "c.js"]
    assert trace_requires(package, "../outside.js")["ok"] is False


def test_trace_requires_depth_limit(tmp_path):
    files = {f"d{i}.js": f"require('./d{i + 1}');\n" for i in range(6)}
    files["d6.js"] = "1;\n"
    data = trace_requires(_package(tmp_path, {"postinstall": "node d0.js"}, files))["data"]
    assert data["files"] == [f"d{i}.js" for i in range(5)]
    assert data["truncated"] and data["incomplete"] == ["depth limit (4) at d4.js:1"]


# A5 inspect_scripts

def test_inspect_scripts_inline_code():
    data = inspect_scripts(str(CORPUS / "inline-fetch-eval"))["data"]
    assert data["untrusted"] and data["order"] == ["preinstall"]
    hook = data["hooks"][0]
    assert hook["hook"] == "preinstall" and hook["line"] == 7
    assert "eval(d)" in hook["commands"][0]["inline_code"]
    assert hook["commands"][0]["runs_file"] == []


def test_inspect_scripts_external_native_build():
    data = inspect_scripts(str(CORPUS / "native-gyp"))["data"]
    assert data["hooks"][0]["commands"][0]["external"] == ["node-gyp"]
    assert data["implicit_node_gyp"] is False


def test_inspect_scripts_chains_order_and_pipes(tmp_path):
    package = _package(tmp_path, {
        "postinstall": "npm run build && printf done | node",
        "preinstall": "CI=1 node setup.js",
        "build": "node scripts/build",
    }, {"setup.js": "1;\n", "scripts/build.js": "1;\n"})
    data = inspect_scripts(package)["data"]
    assert data["order"] == ["preinstall", "postinstall"]
    assert data["chains"] == [{"from_hook": "postinstall", "via": "npm run build", "to_script": "build"}]
    hooks = {hook["hook"]: hook for hook in data["hooks"]}
    assert hooks["preinstall"]["commands"][0]["argv"] == ["node", "setup.js"]
    assert hooks["preinstall"]["commands"][0]["runs_file"] == ["setup.js"]
    assert hooks["build"]["chained_from"] == "postinstall"
    assert hooks["build"]["commands"][0]["runs_file"] == ["scripts/build.js"]
    pipes = [command["pipes_to_shell"] for command in hooks["postinstall"]["commands"]]
    assert pipes == [False, False, True]


def test_inspect_scripts_without_scripts_and_implicit_gyp(tmp_path):
    package = _package(tmp_path, {}, {"binding.gyp": "{}"})
    data = inspect_scripts(package)["data"]
    assert data["order"] == [] and data["hooks"] == [] and data["implicit_node_gyp"] is True
    assert inspect_scripts(str(tmp_path / "missing"))["ok"] is False


# A10 file_stats

def test_file_stats_hints():
    minified = file_stats(str(PACKAGES / "obfuscated-package"), "install.min.js")["data"]
    assert minified["minified_hint"] and minified["max_line"] > 500
    obfuscated = file_stats(str(CORPUS / "hex-obfuscated"), "i.js")["data"]
    assert obfuscated["obfuscated_hint"] and obfuscated["hex_ident_ratio"] >= 0.1
    assert "hex_ident_ratio >= 0.1" in obfuscated["reasons"]
    plain = file_stats(str(CORPUS / "twin-safe"), "setup.js")["data"]
    assert not plain["minified_hint"] and not plain["obfuscated_hint"] and plain["reasons"] == []
    assert plain["lines"] == 5 and plain["comment_ratio"] == 0.2


def test_file_stats_rejects_escape_and_empty_file(tmp_path):
    package = _package(tmp_path, {}, {"empty.js": ""})
    assert file_stats(package, "../x")["ok"] is False
    empty = file_stats(package, "empty.js")["data"]
    assert empty["lines"] == 0 and empty["entropy"] == 0.0 and not empty["obfuscated_hint"]


# A4 trace_flow

def _flows(folder: str, file: str) -> list[tuple]:
    data = trace_flow(str(CORPUS / folder), file)["data"]
    return [(flow["source_line"], flow["source_kind"], flow["sink_line"], flow["sink_kind"], flow["via"])
            for flow in data["flows"]]


def test_trace_flow_secret_to_network_via_variable():
    assert _flows("twin-evil", "setup.js") == [(8, "secret_file", 9, "network", ["token"])]
    assert _flows("env-exfil", "configure.js") == [(4, "env", 9, "network", ["loot"])]


def test_trace_flow_benign_shapes_have_no_secret_to_network_flow():
    assert _flows("env-config", "configure.js") == [(6, "env", 10, "write_package", ["options"])]
    prebuilt = trace_flow(str(CORPUS / "binary-prebuilt"), "install.js")["data"]
    assert {source["kind"] for source in prebuilt["sources"]} == {"network_input"}
    assert {(flow["source_kind"], flow["sink_kind"]) for flow in prebuilt["flows"]} == {("network_input", "write_package")}
    assert _flows("twin-safe", "setup.js") == []


def test_trace_flow_home_path_write_is_outside_package():
    assert _flows("persist-bashrc", "warm.js") == [(6, "home_path", 7, "write_outside", ["rc"])]


def test_trace_flow_rejects_non_javascript():
    result = trace_flow(str(CORPUS / "twin-evil"), "package.json")
    assert result["ok"] is False


# A6 decode_literal

def test_decode_literal_base64_and_escapes():
    stage = decode_literal(str(CORPUS / "base64-eval"), "unpack.js", 2)["data"]
    assert stage["untrusted"] and stage["counts_as_seen"] is False
    assert stage["literals"][0]["encoding"] == "base64" and stage["literals"][0]["decoded_kind"] == "js"
    assert "require('https')" in stage["literals"][0]["decoded_preview"]
    escaped = decode_literal(str(CORPUS / "hex-obfuscated"), "i.js", 1)["data"]["literals"]
    assert [item["decoded_preview"] for item in escaped] == ["child_process", "execSync"]


def test_decode_literal_skips_bad_input_and_hides_identity(tmp_path):
    package = _package(tmp_path, {}, {"a.js": "const a = 'not base64!!';\n"
                                              "const b = String.fromCharCode(104, 105);\n"
                                              "const c = 'abc%2Fdef';\n"})
    assert decode_literal(package, "a.js", 1)["data"]["literals"] == []
    assert decode_literal(package, "a.js", 2)["data"]["literals"][0]["decoded_preview"] == "hi"
    assert decode_literal(package, "a.js", 3)["data"]["literals"][0]["decoded_preview"] == "abc/def"
    assert decode_literal(package, "a.js", 9)["ok"] is False
    assert decode_literal(package, "a.js", 0)["ok"] is False
    assert "hidden" in decode_literal(package, "package.json", 2)["error"]


# A7 resolve_value

def test_resolve_value_array_of_escaped_strings():
    data = resolve_value(str(CORPUS / "hex-obfuscated"), "i.js", "_0x3f1a")["data"]
    assert data["values"][0]["method"] == "literal"
    assert data["values"][0]["value"][:2] == ["child_process", "execSync"]


def test_resolve_value_concat_index_template_and_limits(tmp_path):
    package = _package(tmp_path, {}, {
        "a.js": "const parts = ['ht', 'tp'];\nlet host = parts[0] + parts[1] + '://';\n"
                "host += 'sim.invalid';\nconst url = `${host}/x`;\nconst bad = compute();\n",
        "loop.js": "let a = 'x';\n" + "a = a + 'x';\n" * 12})
    host = resolve_value(package, "a.js", "host")["data"]
    assert [item["value"] for item in host["values"]] == ["http://", "http://sim.invalid"]
    assert resolve_value(package, "a.js", "url")["data"]["values"][0] == {
        "line": 4, "value": "http://sim.invalid/x", "method": "template"}
    assert resolve_value(package, "a.js", "bad")["data"]["values"] == []
    loop = resolve_value(package, "loop.js", "a")["data"]
    assert len(loop["assignments"]) == 10 and loop["truncated"]
    assert resolve_value(package, "a.js", "1bad")["ok"] is False
    assert resolve_value(package, "a.js", "a-b")["ok"] is False


# A8 list_endpoints

def _endpoints(folder: str) -> list[tuple]:
    return [(item["file"], item["line"], item["host"], item["port"], item["built"], item["ip_class"])
            for item in list_endpoints(str(CORPUS / folder))["data"]["endpoints"]]


def test_list_endpoints_ip_port_template_and_decoded():
    assert _endpoints("reverse-shell") == [("scripts/build.js", 5, "203.0.113.40", 4444, "literal", "documentation")]
    assert _endpoints("multi-file-exfil") == [("lib/util/send.js", 7, "*.sim-collector.invalid", None, "template", None)]
    assert _endpoints("base64-eval") == [("unpack.js", 2, "update.sim-cdn.invalid", None, "decoded", None)]
    assert _endpoints("inline-fetch-eval")[0][:3] == ("package.json", 7, "203.0.113.50")
    assert _endpoints("twin-safe") == []


def test_list_endpoints_counts_as_seen_only_for_literals():
    data = list_endpoints(str(CORPUS / "base64-eval"))["data"]
    assert data["untrusted"] and data["endpoints"][0]["counts_as_seen"] is False
    literal = list_endpoints(str(CORPUS / "reverse-shell"))["data"]["endpoints"][0]
    assert literal["counts_as_seen"] is True and literal["is_ip"] is True


def test_list_endpoints_ip_classes(tmp_path):
    package = _package(tmp_path, {"postinstall": "node a.js"}, {
        "a.js": "const a = '127.0.0.1';\nconst b = '10.1.2.3';\nconst c = '8.8.8.8';\nconst d = '999.1.1.1';\n"})
    classes = [(item["host"], item["ip_class"]) for item in list_endpoints(package)["data"]["endpoints"]]
    assert classes == [("127.0.0.1", "loopback"), ("10.1.2.3", "private"), ("8.8.8.8", "public")]


# A9 inspect_binary

def _fake_elf(path: Path, padding: int = 100) -> None:
    # 64-byte ELF-like header, padding and one URL: inert bytes, not a loadable program.
    path.write_bytes(b"\x7fELF\x02\x01\x01" + b"\0" * 57 + b"\0" * padding + b"https://sim-cdn.invalid/addon\0"
                     + b"plain words here\0")


def test_inspect_binary_format_strings_and_hash(tmp_path):
    package = _package(tmp_path, {}, {})
    _fake_elf(tmp_path / "addon.node")
    data = inspect_binary(package, "addon.node")["data"]
    assert data["untrusted"] and data["format"] == "ELF" and not data["truncated"]
    assert [item["text"] for item in data["strings"]] == ["https://sim-cdn.invalid/addon"]
    assert len(data["sha256"]) == 64 and data["bytes"] == (tmp_path / "addon.node").stat().st_size
    assert inspect_binary(package, "package.json")["data"]["format"] == "unknown"
    assert inspect_binary(package, "../x")["ok"] is False


def test_inspect_binary_large_file_is_truncated(tmp_path):
    package = _package(tmp_path, {}, {})
    with (tmp_path / "big.bin").open("wb") as stream:
        stream.write(b"MZ")
        stream.seek(9 * 1024 * 1024)
        stream.write(b"\0")
    data = inspect_binary(package, "big.bin")["data"]
    assert data["format"] == "PE" and data["truncated"]


def test_trace_flow_stays_fast_on_long_chained_files(tmp_path):
    import time
    body = "\n".join(f"const v{j} = process.env.X + v{max(0, j - 1)}; fs.writeFileSync(p, v{j});" for j in range(4000))
    package = _package(tmp_path, {}, {"big.js": body})
    started = time.monotonic()
    data = trace_flow(package, "big.js")["data"]
    assert time.monotonic() - started < 5  # was minutes before 2026-11-08 (quadratic taint search)
    assert data["truncated"] and len(data["flows"]) == 30
    assert all(len(flow["via"]) <= 5 for flow in data["flows"])
