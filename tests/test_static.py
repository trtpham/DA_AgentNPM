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
