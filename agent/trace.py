"""Append-only JSONL events for the local, read-only viewer."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


EVENT_FIELDS = {
    "run_start": ("model", "config_name", "max_steps"),
    "thought": ("text",),
    "tool_call": ("tool", "args"),
    "tool_result": ("tool", "ok", "summary", "data_preview", "untrusted", "duration_ms"),
    "verdict": ("verdict", "valid", "validation_errors"),
    "decision": ("threshold", "evidence_checks", "final_label", "final_action", "dry_run"),
    "error": ("kind", "message"),
    "limit": ("reason",),
    "run_end": ("elapsed_s", "steps", "tokens_per_s"),
}


def trace_filename(package: str) -> str:
    return f"{hashlib.sha256(package.encode('utf-8')).hexdigest()}.trace.jsonl"


class NullTraceWriter:
    def emit(self, type: str, **fields) -> None:
        pass


class TraceWriter:
    def __init__(self, run_dir: str | Path, package: str):
        self.run_dir = Path(run_dir)
        self.run_id = self.run_dir.name
        self.package = package
        self.path = self.run_dir / trace_filename(package)
        self.seq = 0
        if self.path.exists():
            raise FileExistsError(self.path)

    def emit(self, type: str, **fields) -> None:
        if type not in EVENT_FIELDS:
            raise ValueError(f"unknown trace event: {type}")
        unexpected = fields.keys() - EVENT_FIELDS[type]
        if unexpected:
            raise ValueError(f"unknown {type} fields: {sorted(unexpected)}")
        event = {key: fields.get(key) for key in EVENT_FIELDS[type]}
        if type == "tool_result" and isinstance(event["data_preview"], str):
            event["data_preview"] = event["data_preview"][:2000]
        event.update(run_id=self.run_id, package=self.package, seq=self.seq,
                     ts=datetime.now(timezone.utc).isoformat(), type=type)
        line = json.dumps(event, ensure_ascii=False) + "\n"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as output:
            output.write(line)
            output.flush()
        self.seq += 1
