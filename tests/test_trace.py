import json
import sqlite3
from pathlib import Path

import pytest

from agent.run import analyze
from agent.schema import Verdict
from agent.trace import NullTraceWriter, TraceWriter, trace_filename


def test_jsonl_sequence_flush_and_scoped_filename(tmp_path):
    package = "@scope/native-addon@1.0.0"
    writer = TraceWriter(tmp_path / "run-1", package)
    writer.emit("run_start", model="qwen3.5:4b", max_steps=15)
    assert writer.path.exists()
    writer.emit("tool_result", tool="read_file", ok=True, data_preview="x" * 2500, untrusted=True)
    writer.emit("run_end", elapsed_s=1.2, steps=1)

    events = [json.loads(line) for line in writer.path.read_text(encoding="utf-8").splitlines()]
    assert [event["seq"] for event in events] == [0, 1, 2]
    assert all(event["run_id"] == "run-1" and event["package"] == package for event in events)
    assert events[0]["config_name"] is None
    assert len(events[1]["data_preview"]) == 2000
    assert events[2]["tokens_per_s"] is None
    assert writer.path.name == trace_filename(package)
    assert all(character not in writer.path.name for character in "@/\\:")
    assert len(trace_filename("@scope/" + "a" * 200 + "@1.0.0")) < 255


def test_null_writer_creates_no_file(tmp_path):
    NullTraceWriter().emit("run_start", model="fake", max_steps=1)
    assert list(tmp_path.iterdir()) == []


def test_agent_writes_read_only_trace_for_fixture(tmp_path):
    package_dir = str(Path(__file__).parent / "fixtures" / "benign-package")
    verdict = {
        "package": "benign-install-fixture@1.0.0", "label": "benign", "confidence": 0.9,
        "description": "Installation writes only a fixed local test marker",
        "behaviors": [{"behavior": "Writes a local marker", "technique": "file write",
                       "severity": "low", "evidence": {"file": "postinstall.js", "lines": "2"},
                       "analysis": "The script writes fixed text to a local file.",
                       "impact": "Creates a test marker."}],
        "action": "approve", "remediation": [],
    }
    replies = iter([
        {"role": "assistant", "content": "I will inspect the script.",
         "tool_calls": [{"function": {"name": "read_file", "arguments": {"file": "postinstall.js"}}}]},
        {"role": "assistant", "content": json.dumps(verdict)},
    ])
    writer = TraceWriter(tmp_path / "run-2", verdict["package"])
    result, steps = analyze(package_dir, "fake-model", chat=lambda *_args, **_kwargs: next(replies), trace=writer)
    events = [json.loads(line) for line in writer.path.read_text(encoding="utf-8").splitlines()]

    assert (result.label, steps) == ("benign", 2)
    assert [event["seq"] for event in events] == list(range(len(events)))
    assert {event["type"] for event in events} >= {
        "run_start", "thought", "tool_call", "tool_result", "verdict", "decision", "run_end"}
    decision = next(event for event in events if event["type"] == "decision")
    assert (decision["final_action"], decision["rule"], decision["dry_run"]) == ("approve", "R7", True)
    with sqlite3.connect(tmp_path / "decisions.sqlite") as connection:
        assert connection.execute("SELECT final_action, rule FROM decisions LIMIT 1").fetchone() == ("approve", "R7")
    assert any(event["type"] == "tool_result" and event["untrusted"] for event in events)


def test_synthetic_samples_are_valid_and_bounded():
    samples = sorted((Path(__file__).parents[1] / "viewer" / "sample_traces").glob("*.jsonl"))
    assert len(samples) == 3
    for sample in samples:
        events = [json.loads(line) for line in sample.read_text(encoding="utf-8").splitlines()]
        assert sample.name == trace_filename(events[0]["package"])
        assert [event["seq"] for event in events] == list(range(len(events)))
        assert all(event["package"] == events[0]["package"] for event in events)
        assert all(len(event.get("data_preview") or "") <= 2000 for event in events)
        Verdict.model_validate(next(event for event in events if event["type"] == "verdict")["verdict"])
    assert any("<img src=x onerror=alert(1)>" in sample.read_text(encoding="utf-8") for sample in samples)


def test_step_limit_closes_trace(tmp_path):
    package_dir = str(Path(__file__).parent / "fixtures" / "benign-package")
    writer = TraceWriter(tmp_path / "run-limit", "benign-install-fixture@1.0.0")
    with pytest.raises(RuntimeError, match="no valid evidence-backed verdict"):
        analyze(package_dir, "fake-model", max_steps=1,
                chat=lambda *_args, **_kwargs: {"role": "assistant", "content": "No tool call"}, trace=writer)
    events = [json.loads(line) for line in writer.path.read_text(encoding="utf-8").splitlines()]
    assert events[-3]["type"] == "limit" and events[-3]["reason"] == "max_steps"
    assert (events[-2]["type"], events[-2]["rule"], events[-2]["final_action"]) == ("decision", "R2", "review")
    assert events[-1]["type"] == "run_end" and events[-1]["steps"] == 1
