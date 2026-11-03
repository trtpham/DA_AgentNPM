import json

import pytest

from agent.decide import decide
from agent.schema import Verdict
from tools.actions import apply_decision


@pytest.fixture
def project(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"name": "app", "version": "1.0.0"}), encoding="utf-8")
    return tmp_path


def verdict(label, confidence=0.9):
    return Verdict.model_validate({
        "package": "dep@1.0.0", "label": label, "confidence": confidence,
        "description": "Synthetic fixture contains one inspected install behavior",
        "behaviors": [{"behavior": "Reads fixture", "technique": "read", "severity": "low",
                       "evidence": {"file": "setup.js", "lines": "1"},
                       "analysis": "Synthetic source is inspected.", "impact": "Only test data is read."}],
        "action": "deny" if label == "malicious" else "approve" if label == "benign" else "review",
        "remediation": ["Review fixture"] if label != "benign" else [],
    })


@pytest.mark.parametrize("label, exists, command", [
    ("malicious", True, ["npm", "deny-scripts", "dep@1.0.0"]),
    ("benign", True, ["npm", "approve-scripts", "dep@1.0.0"]),
    ("malicious", False, None),  # fake evidence is downgraded to review: no command
])
def test_dry_run_plans_command_from_rule_decision(project, label, exists, command):
    decision = decide(verdict(label), [{"file": "setup.js", "lines": "1", "exists": exists}],
                      auto_approve_allowed=True)
    result = apply_decision(str(project), "dep@1.0.0", decision)
    assert result["ok"] and result["data"]["dry_run"] is True
    assert result["data"]["command"] == command
    assert json.loads((project / "package.json").read_text(encoding="utf-8")) == {"name": "app", "version": "1.0.0"}


def test_real_run_and_bad_input_are_refused_without_exceptions(project, tmp_path):
    decision = {"label": "benign", "action": "approve", "rule": "R7", "reasons": []}
    assert apply_decision(str(project), "dep@1.0.0", decision, dry_run=False)["ok"] is False
    assert apply_decision(str(project), "dep; rm -rf /", decision)["error"] == "invalid package id"
    assert apply_decision(str(tmp_path / "missing"), "dep@1.0.0", decision)["ok"] is False
    assert apply_decision(str(project), "dep@1.0.0", {"action": "run"})["ok"] is False
