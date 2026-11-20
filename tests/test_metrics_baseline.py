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


def test_missing_lists_labelled_rows_without_a_result():
    labels = [{"name": "a", "version": "1", "label": "malicious"}, {"name": "b", "version": "1", "label": "benign"}]
    result = score([{"package": "a@1", "ok": True, "data": {"issues": 2}}], labels, "guarddog")
    assert result["missing"] == ["b@1"] and result["scored"] == 1 and result["binary"]["tp"] == 1


def test_metrics_cli_scores_only_the_chosen_split(tmp_path):
    import sys
    labels = tmp_path / "labels.csv"
    labels.write_text("id,name,version,label,behavior_main,technique,file,lines,source,split,cluster\n"
                      "d,a,1,malicious,x,x,x,1,s,dev,c1\nt,b,1,benign,x,x,x,1,s,test,c2\n", encoding="utf-8")
    (tmp_path / "a@1.json").write_text(json.dumps({"package": "a@1", "ok": True, "data": {"issues": 0}}))
    (tmp_path / "b@1.json").write_text(json.dumps({"package": "b@1", "ok": True, "data": {"issues": 1}}))
    out = subprocess.run([sys.executable, "-m", "experiments.metrics", str(tmp_path), "--labels", str(labels),
                          "--source", "guarddog", "--split", "dev"], capture_output=True, text=True, check=True)
    result = json.loads(out.stdout)
    assert result["split"] == "dev" and result["scored"] == 1 and result["unmatched"] == ["b@1"]
    assert result["binary"] == {"tp": 0, "fp": 0, "tn": 0, "fn": 1}
