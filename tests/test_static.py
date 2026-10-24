import json

from tools.static import read_file, read_manifest


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
