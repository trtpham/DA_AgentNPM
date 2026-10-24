import sqlite3

from agent.decide import decide, record_decision
from agent.schema import Verdict


def verdict(label="malicious", confidence=0.9):
    return Verdict.model_validate({
        "package": "safe-fixture@1.0.0", "label": label, "confidence": confidence,
        "description": "Synthetic fixture contains one inspected install behavior",
        "behaviors": [{"behavior": "Reads fixture", "technique": "read", "severity": "low",
                       "evidence": {"file": "setup.js", "lines": "1"},
                       "analysis": "Synthetic source is inspected.", "impact": "Only test data is read."}],
        "action": "deny" if label == "malicious" else "approve" if label == "benign" else "review",
        "remediation": ["Review fixture"] if label != "benign" else [],
    })


def test_decision_rules_prioritize_canary_error_and_verified_evidence():
    evidence = [{"file": "setup.js", "lines": "1", "exists": True}]
    item = verdict("benign")
    assert decide(item, evidence, canary_touched=True)["rule"] == "R1"
    assert decide(item, evidence, run_error=True)["action"] == "review"
    assert decide(verdict(), [{**evidence[0], "exists": False}])["label"] == "suspicious"
    assert decide(item, evidence, osv_malicious=True)["rule"] == "R5"
    assert decide(item, evidence, auto_approve_allowed=True)["action"] == "approve"
    assert decide(item, evidence)["action"] == "review"
    assert decide(item, evidence, auto_approve_allowed=False)["action"] == "review"
    assert decide(verdict(), evidence)["action"] == "deny"
    assert decide(verdict(confidence=0.7), evidence)["action"] == "review"


def test_decision_thresholds_are_validated():
    try:
        decide(verdict(), [], deny_threshold=1.1)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid threshold accepted")


def test_error_decision_is_recorded_in_sqlite(tmp_path):
    decision = decide(None, [], step_limit=True)
    assert (decision["label"], decision["action"], decision["rule"]) == ("suspicious", "review", "R2")
    path = tmp_path / "decisions.sqlite"
    record_decision(path, "run-1", "safe-fixture@1.0.0", decision)
    with sqlite3.connect(path) as connection:
        row = connection.execute("SELECT final_label, final_action, rule FROM decisions LIMIT 1").fetchone()
    assert row == ("suspicious", "review", "R2")
