from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: str = Field(min_length=1)
    lines: str = Field(pattern=r"^[1-9]\d*(?:-[1-9]\d*)?$")


class Behavior(BaseModel):
    model_config = ConfigDict(extra="forbid")

    behavior: str = Field(min_length=1)
    technique: str = Field(min_length=1)
    severity: Literal["low", "medium", "high"]
    evidence: Evidence
    analysis: str = Field(min_length=1)
    impact: str = Field(min_length=1)


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: str = Field(pattern=r"^(?:@[a-z0-9._-]+/)?[a-z0-9._-]+@[^@/\s]+$")
    label: Literal["malicious", "suspicious", "benign"]
    confidence: float = Field(ge=0, le=1)
    description: str
    behaviors: list[Behavior]
    action: Literal["deny", "approve", "review"]
    remediation: list[str]

    @field_validator("description")
    @classmethod
    def description_length(cls, value: str) -> str:
        if not 5 <= len(value.split()) <= 15:
            raise ValueError("description must contain 5 to 15 words")
        return value

    @model_validator(mode="after")
    def require_evidence_and_remediation(self):
        if self.label != "benign" and (not self.behaviors or not self.remediation):
            raise ValueError("non-benign verdict requires behaviors and remediation")
        if (self.label == "benign" and self.action == "deny"
                or self.label in ("malicious", "suspicious") and self.action == "approve"):
            raise ValueError("inconsistent action for verdict label")
        return self
