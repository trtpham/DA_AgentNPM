import json
import subprocess
from pathlib import Path

from experiments.baseline_guarddog import scan, scan_command
from experiments.metrics import score

LABELS = [{"name": n, "version": "1.0.0", "label": l} for n, l in
          (("a", "benign"), ("b", "benign"), ("c", "malicious"), ("d", "suspicious"), ("e", "malicious"))]


def agent(name, label, action, status="ok", steps=3):
    return {"package": f"{name}@1.0.0", "status": status, "steps": steps, "elapsed_s": 10.0,
            "decision": {"label": label, "action": action, "rule": "R"} if label else None}


def test_agent_metrics_count_failures_as_misses():
    results = [agent("a", "benign", "approve"), agent("b", "suspicious", "review"),
               agent("c", "malicious", "deny"), agent("d", "benign", "review"),
               agent("e", None, None, status="error", steps=15), agent("zzz", "benign", "approve")]
    report = score(results, LABELS)
    assert report["binary"] == {"tp": 1, "fp": 1, "tn": 1, "fn": 2}
    assert (report["precision"], report["recall"], report["f1"], report["fpr"]) == (0.5, 0.3333, 0.4, 0.5)
    assert report["confusion"]["malicious"]["error"] == 1 and report["unmatched"] == ["zzz@1.0.0"]
    assert (report["review_rate"], report["valid_json_rate"], report["error_rate"]) == (0.4, 0.8, 0.2)
    fallback = agent("a", "suspicious", "review", status="error")  # failed run scored by its R2 fallback
    report = score([fallback], LABELS)
    assert (report["binary"]["fp"], report["error_rate"]) == (1, 1.0)


def test_guarddog_metrics_and_empty_denominators():
    results = [{"package": "a@1.0.0", "ok": True, "data": {"issues": 0}},
               {"package": "c@1.0.0", "ok": True, "data": {"issues": 2}}]
    report = score(results, LABELS, "guarddog")
    assert report["binary"] == {"tp": 1, "fp": 0, "tn": 1, "fn": 0} and report["review_rate"] is None
    assert score([], LABELS)["precision"] is None


def test_guarddog_scan_runs_offline_read_only_and_parses(tmp_path):
    seen = {}

    def runner(command, **_kwargs):
        seen["command"] = command
        return subprocess.CompletedProcess(command, 0, json.dumps(
            {"issues": 1, "errors": {}, "results": {"npm-exec-base64": [{"location": "index.js:2"}], "shady-links": {}}}), "")

    result = scan(tmp_path, runner=runner)
    assert result["ok"] and result["data"]["rules"] == ["npm-exec-base64"]
    command = seen["command"]
    assert command[command.index("--network") + 1] == "none" and "--read-only" in command
    assert any(part.endswith("target=/scan,readonly") for part in command)
    broken = scan(tmp_path, runner=lambda command, **_k: subprocess.CompletedProcess(command, 1, "not json", ""))
    assert broken["ok"] is False
    assert scan_command(Path(tmp_path))[0] == "docker"
