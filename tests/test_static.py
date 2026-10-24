import json
import base64
import time

from tools.static import deobfuscate, extract_indicators, read_file, read_manifest


def test_minified_pretty_view_and_indicators(tmp_path):
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
    assert indicators["ok"] and any(item["kind"] == "eval" for item in indicators["data"]["indicators"])
    (tmp_path / "oversized.js").write_text("x" * (256 * 1024 + 1), encoding="utf-8")
    assert extract_indicators(str(tmp_path))["data"]["truncated"] is True


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
