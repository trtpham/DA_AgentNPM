"""Replay raw Ollama replies recorded on 2026-11-04 so model-specific failures stay regression tests.

The replies only describe harmless fixtures. Each file keeps the outcome seen in the live run.
"""

import json
from pathlib import Path

import pytest

from agent.run import analyze
from agent.trace import TraceWriter

ROOT = Path(__file__).parent / "fixtures"
REPLAYS = sorted((ROOT / "replays").glob("*.json"))


@pytest.mark.parametrize("path", REPLAYS, ids=[path.stem for path in REPLAYS])
def test_recorded_replies_reach_the_same_outcome(path, tmp_path):
    record = json.loads(path.read_text(encoding="utf-8"))
    replies = iter(record["replies"])
    writer = TraceWriter(tmp_path / "run", "replay")

    def chat(*_args, **_kwargs):
        return json.loads(json.dumps(next(replies)))  # analyze mutates replies; keep the record intact

    expected = record["expected"]
    if expected["valid"]:
        result, steps = analyze(str(ROOT / record["fixture"]), "replay", chat=chat, trace=writer)
        assert steps == expected["steps"]
    else:
        with pytest.raises(RuntimeError, match="no valid evidence-backed verdict"):
            analyze(str(ROOT / record["fixture"]), "replay", chat=chat, trace=writer)
    decision = next(json.loads(line) for line in writer.path.read_text(encoding="utf-8").splitlines()
                    if json.loads(line)["type"] == "decision")
    assert (decision["rule"], f"{decision['final_label']}/{decision['final_action']}") == (expected["rule"], expected["final"])


def test_replays_cover_success_and_failure():
    outcomes = {json.loads(path.read_text(encoding="utf-8"))["expected"]["valid"] for path in REPLAYS}
    assert outcomes == {True, False} and len(REPLAYS) >= 5
