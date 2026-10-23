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
