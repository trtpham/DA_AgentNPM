import pytest
from pydantic import ValidationError

from agent.schema import Verdict


def test_verdict_requires_evidence_and_remediation():
    verdict = dict(package="example@1.0.0", label="malicious", confidence=0.9,
                   description="Install script sends private data to remote host",
                   behaviors=[], action="deny", remediation=[])
    with pytest.raises(ValidationError):
        Verdict.model_validate(verdict)
    verdict["behaviors"] = [dict(behavior="exfiltration", technique="network", severity="high",
                                 evidence=dict(file="setup.js", lines="12-18"), analysis="unrelated host", impact="token theft")]
    verdict["remediation"] = ["Block install script"]
    assert Verdict.model_validate(verdict).label == "malicious"


@pytest.mark.parametrize("label,action", [
    ("benign", "deny"), ("malicious", "approve"), ("suspicious", "approve"),
])
def test_verdict_rejects_conflicting_action(label, action):
    verdict = dict(package="example@1.0.0", label=label, confidence=0.9,
                   description="Install script sends private data to remote host",
                   behaviors=[dict(behavior="network request", technique="network", severity="high",
                                   evidence=dict(file="setup.js", lines="1"), analysis="external host",
                                   impact="possible data transfer")], action=action,
                   remediation=["Review install script"])
    with pytest.raises(ValidationError, match="inconsistent action"):
        Verdict.model_validate(verdict)
