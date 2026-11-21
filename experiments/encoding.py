"""Gate B0 2026-11-21: free text leaves the analysis container only as base64.

Tool previews quote package code, and the model's own words (thoughts, verdict analysis) can quote it too:
Windows Defender quarantined a result file on 20/11 because of a verdict text. So every field that is not a
known structural field (event type, tool, label, action, rule, counts, times) is replaced by
`<field>_b64` + `<field>_encoding`: "base64" is the UTF-8 of a string, "base64-json" the JSON of any other
value. Readers call `decode_fields`, which restores the original keys in memory only.
"""

import base64
import json

# Trace event fields that are written by our code, never by the model or the package.
TRACE_SAFE = frozenset({
    "type", "seq", "ts", "run_id", "package", "tool", "ok", "valid", "untrusted", "duration_ms", "model",
    "config_name", "max_steps", "threshold", "final_label", "final_action", "dry_run", "rule", "kind", "reason",
    "elapsed_s", "steps", "tokens_per_s", "prompt_tokens", "output_tokens",
})
RESULT_SAFE = frozenset({
    "package", "variant", "model", "trace", "status", "steps", "errors", "elapsed_s", "container_peak_mb",
    "planned_command", "decision", "verdict_summary",
})
DECISION_SAFE = frozenset({"label", "action", "rule"})
SUFFIXES = ("_b64", "_encoding")


def _encode_into(target: dict, key: str, value) -> None:
    if isinstance(value, str):
        target[f"{key}_b64"] = base64.b64encode(value.encode("utf-8")).decode("ascii")
        target[f"{key}_encoding"] = "base64"
    else:  # None, numbers, lists and objects keep their type through JSON
        text = json.dumps(value, ensure_ascii=False)
        target[f"{key}_b64"] = None if value is None else base64.b64encode(text.encode("utf-8")).decode("ascii")
        target[f"{key}_encoding"] = "base64" if value is None else "base64-json"


def _encode_except(record: dict, safe: frozenset) -> dict:
    out = {}
    for key, value in record.items():
        if key in safe or key.endswith(SUFFIXES):
            out[key] = value
        else:
            _encode_into(out, key, value)
    return out


def encode_event(event: dict) -> dict:
    return _encode_except(event, TRACE_SAFE)


def encode_trace(text: str) -> str:
    """Every JSONL event of a trace, encoded. Raises ValueError on a line that is not a JSON object."""
    lines = []
    for line in text.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError("trace line is not an object")
        lines.append(json.dumps(encode_event(event), ensure_ascii=False))
    return "".join(line + "\n" for line in lines)


def encode_result(result: dict) -> dict:
    """Result JSON: verdict, error and any unknown field encoded; a plain verdict_summary stays for scoring."""
    out = dict(result)
    verdict = out.get("verdict")
    if isinstance(verdict, dict) and "verdict_summary" not in out:
        out["verdict_summary"] = {key: verdict.get(key) for key in ("label", "confidence", "action")}
    if isinstance(out.get("decision"), dict):
        out["decision"] = _encode_except(out["decision"], DECISION_SAFE)
    if isinstance(out.get("verdict_summary"), dict):
        summary = out["verdict_summary"]
        out["verdict_summary"] = {"label": summary.get("label") if isinstance(summary.get("label"), str) else None,
                                  "confidence": summary.get("confidence")
                                  if isinstance(summary.get("confidence"), (int, float)) else None,
                                  "action": summary.get("action") if isinstance(summary.get("action"), str) else None}
    return _encode_except(out, RESULT_SAFE)


def _plain_keys(record: dict, safe: frozenset) -> list[str]:
    return [key for key in record if key not in safe and not key.endswith(SUFFIXES)]


def trace_has_plain_text(text: str) -> bool:
    """Host guard: True when a trace line keeps a free-text field in plain form (or cannot be checked)."""
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            return True
        if not isinstance(event, dict) or _plain_keys(event, TRACE_SAFE):
            return True
    return False


def result_has_plain_text(result: dict) -> bool:
    if _plain_keys(result, RESULT_SAFE):
        return True
    decision = result.get("decision")
    if decision is not None and (not isinstance(decision, dict) or _plain_keys(decision, DECISION_SAFE)):
        return True
    return any(not isinstance(item, str) or len(item) > 40 for item in result.get("errors") or [])


def decode_fields(record):
    """Restore `<field>` from `<field>_b64` + `<field>_encoding`, recursively; plain old records pass through."""
    if isinstance(record, list):
        return [decode_fields(item) for item in record]
    if not isinstance(record, dict):
        return record
    out = {}
    for key, value in record.items():
        if key.endswith("_encoding") and f"{key[:-9]}_b64" in record:
            continue
        if key.endswith("_b64") and f"{key[:-4]}_encoding" in record:
            name, encoding = key[:-4], record[f"{key[:-4]}_encoding"]
            if value is None:
                out[name] = None
            elif encoding == "base64":
                out[name] = base64.b64decode(value).decode("utf-8")
            elif encoding == "base64-json":
                out[name] = json.loads(base64.b64decode(value).decode("utf-8"))
            else:
                raise ValueError(f"unknown encoding for {name}")
            continue
        out[key] = decode_fields(value)
    return out


def read_events(path) -> list[dict]:
    """Decoded events of one trace file (old plain traces work too)."""
    from pathlib import Path
    text = Path(path).read_text(encoding="utf-8")
    return [decode_fields(json.loads(line)) for line in text.splitlines() if line.strip()]
