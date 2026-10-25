"""Deterministic decision policy and audit log for a model verdict."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from agent.schema import Verdict


def decide(verdict: Verdict | None, evidence_checks: list[dict], *, canary_touched: bool = False,
           run_error: bool = False, step_limit: bool = False, osv_malicious: bool = False,
           deny_threshold: float = 0.8, approve_threshold: float = 0.8,
           auto_approve_allowed: bool = False) -> dict:
    if not 0 <= deny_threshold <= 1 or not 0 <= approve_threshold <= 1:
        raise ValueError("decision thresholds must be between 0 and 1")

    def result(label: str, action: str, rule: str, reason: str) -> dict:
        return {"label": label, "action": action, "rule": rule, "reasons": [reason]}

    if canary_touched:
        return result("malicious", "deny", "R1", "Sandbox canary touched")
    if run_error or step_limit:
        return result("suspicious", "review", "R2", "Analysis failed or reached its step limit")
    if verdict is None:
        raise ValueError("verdict required for successful analysis")

    valid = sum(check.get("exists") is True for check in evidence_checks)
    if verdict.behaviors and valid == 0:
        return result("suspicious", "review", "R3", "No behavior has verified file and lines")
    if verdict.label == "malicious" and valid == 0:
        return result("suspicious", "review", "R4", "Malicious claim has no verified behavior")
    if osv_malicious and verdict.label == "benign":
        return result("suspicious", "review", "R5", "OSV MAL signal blocks automatic approval")
    if verdict.label == "malicious" and verdict.confidence >= deny_threshold:
        return result("malicious", "deny", "R6", "Verified malicious behavior meets deny threshold")
    if verdict.label == "benign" and verdict.confidence >= approve_threshold and valid:
        if not auto_approve_allowed:
            return result("benign", "review", "R7_review", "Install path not fully reviewed; human review required")
        return result("benign", "approve", "R7", "Verified benign evidence meets approve threshold")
    return result(verdict.label, "review", "R8", "Decision requires human review")


def record_decision(path: Path, run_id: str, package: str, decision: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS decisions (
            run_id TEXT NOT NULL, package TEXT NOT NULL, final_label TEXT NOT NULL,
            final_action TEXT NOT NULL, rule TEXT NOT NULL, reasons_json TEXT NOT NULL,
            created_at TEXT NOT NULL, PRIMARY KEY (run_id, package))""")
        connection.execute("""INSERT OR REPLACE INTO decisions
            (run_id, package, final_label, final_action, rule, reasons_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, package, decision["label"], decision["action"], decision["rule"],
             json.dumps(decision["reasons"]), datetime.now(timezone.utc).isoformat()))
