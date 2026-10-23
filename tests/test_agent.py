import json
from pathlib import Path

import pytest

from agent.run import analyze, _tool


FIXTURE = str(Path(__file__).parent / "fixtures" / "benign-package")


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

    def chat(_model, _messages, final=False):
        final_flags.append(final)
        return next(replies)

    result, steps = analyze(FIXTURE, "fake-model", chat=chat)

    assert steps == 3
    assert final_flags == [False, False, True]
    assert result.label == "benign"
    assert result.behaviors[0].evidence.lines == "2"


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
