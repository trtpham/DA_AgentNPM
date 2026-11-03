import json

import pytest

from tools.intel import _https_json, build_context, diff_versions, osv_lookup, registry_metadata


def fake_registry(calls):
    documents = {
        "https://registry.npmjs.org/@demo/pkg": {"versions": {"1.0.0": {}, "1.1.0-beta.1": {}, "1.1.0": {}, "2.0.0": {}}},
        "https://registry.npmjs.org/@demo/pkg/1.0.0": {"scripts": {"test": "jest"}},
        "https://registry.npmjs.org/@demo/pkg/1.1.0": {"scripts": {"postinstall": "node x.js"},
                                                        "maintainers": [{"name": "a"}], "dist": {"integrity": "sha512-x"}},
        "https://api.osv.dev/v1/query": {"vulns": [{"id": "MAL-2026-1", "summary": "Malicious code"}]},
    }

    def fetch(url, body=None, accept="application/json"):
        calls.append((url, body))
        return documents[url]
    return fetch


def test_context_reports_new_hooks_and_osv_malicious_signal():
    calls = []
    context = build_context("@demo/pkg", "1.1.0", fake_registry(calls))
    registry = context["registry"]["data"]
    assert context["osv"]["data"]["malicious"] is True
    assert (registry["previous_version"], registry["new_hooks"], registry["hooks_changed_since_previous"]) == (
        "1.0.0", ["postinstall"], True)
    assert registry["maintainers"] == 1 and registry["integrity"] == "sha512-x"
    assert calls[0][1] == {"package": {"name": "@demo/pkg", "ecosystem": "npm"}, "version": "1.1.0"}
    assert all("@demo/pkg" in url or "osv" in url for url, _ in calls)


def test_lookups_validate_input_and_never_raise():
    def broken(*_args, **_kwargs):
        raise OSError("offline")
    assert osv_lookup("bad name", "1.0.0")["error"] == "invalid package name or version"
    assert registry_metadata("pkg", "1.0.0", broken) == {"ok": False, "data": None, "error": "offline"}
    with pytest.raises(ValueError, match="host not allowed"):
        _https_json("https://example.invalid/x")


def test_diff_versions_flags_new_hook_and_indicator(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    for directory in (old, new):
        directory.mkdir()
    (old / "package.json").write_text(json.dumps({"name": "p", "version": "1.0.0"}), encoding="utf-8")
    (new / "package.json").write_text(json.dumps({"name": "p", "version": "1.0.1",
                                                  "scripts": {"postinstall": "node x.js"}}), encoding="utf-8")
    (new / "x.js").write_text("require('child_process').exec('id');\n", encoding="utf-8")
    data = diff_versions(str(old), str(new))["data"]
    assert data["hooks_added"] == ["postinstall"] and data["targets_added"] == ["x.js"]
    assert "child_process" in data["indicator_types_added"]
