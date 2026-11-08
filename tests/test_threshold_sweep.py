import json

from experiments.threshold_sweep import markdown, recorded, sweep

INPUTS = {"osv_malicious": False, "auto_approve_allowed": True, "review_reasons": [], "unexplained_risks": [],
          "flow_risks": [], "canary_touched": False, "sandbox_risks": []}


def verdict(label, confidence):
    return {"package": "p@1", "label": label, "confidence": confidence, "description": "Install script behaviour summary text",
            "behaviors": [{"behavior": "b", "technique": "t", "severity": "low", "evidence": {"file": "a.js", "lines": "1"},
                           "analysis": "a", "impact": "i"}],
            "action": "review", "remediation": ["r"]}


def write_case(run, package, label, confidence, inputs=INPUTS):
    trace = f"{package}.trace.jsonl"
    events = [{"type": "verdict", "valid": True, "verdict": verdict(label, confidence)},
              {"type": "decision", "evidence_checks": [{"exists": True}], "inputs": inputs}]
    (run / trace).write_text("\n".join(map(json.dumps, events)), encoding="utf-8")
    (run / f"{package}.json").write_text(json.dumps({"package": package, "trace": trace, "status": "ok"}), encoding="utf-8")


def test_sweep_redecides_and_picks_the_safest_best_f1(tmp_path):
    write_case(tmp_path, "evil@1", "malicious", 0.85)
    write_case(tmp_path, "evil2@1", "benign", 0.70)   # the model is wrong with medium confidence
    write_case(tmp_path, "good@1", "benign", 0.90)
    write_case(tmp_path, "old@1", "benign", 0.90, inputs=None)  # trace from before inputs were recorded
    truth = {"evil@1": "malicious", "evil2@1": "malicious", "good@1": "benign", "old@1": "benign"}
    result = sweep(tmp_path, truth)
    by_threshold = {row["threshold"]: row for row in result["rows"]}
    assert result["cases"] == 3 and result["skipped"] == ["old@1"]
    assert by_threshold[0.65]["malicious_approved"] == 1   # 0.70 benign would be approved
    assert by_threshold[0.75]["malicious_approved"] == 0 and by_threshold[0.75]["recall"] == 0.5
    assert by_threshold[0.90]["recall"] == 0.5 and by_threshold[0.90]["fpr"] == 0.0
    # 0.80-0.95 tie on F1 (labels, not actions, are scored); the tie goes to the higher threshold.
    assert result["chosen"] == 0.95
    assert "**(chọn)**" in markdown(result)


def test_recorded_needs_verdict_and_inputs(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps({"type": "decision", "evidence_checks": [], "inputs": INPUTS}), encoding="utf-8")
    assert recorded(path) is None
