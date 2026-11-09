import json

from experiments import report_tables as rt

FIELDS = "id,name,version,label,behavior_main,technique,file,lines,source,split,cluster"


def _labels(tmp_path):
    rows = [("m1", "evil", "malicious", "test"), ("m2", "evil2", "malicious", "test"), ("b1", "good", "benign", "test"),
            ("b2", "good2", "benign", "test"), ("d1", "devonly", "benign", "dev")]
    path = tmp_path / "labels.csv"
    path.write_text(FIELDS + "\n" + "".join(f"{i},{n},1.0.0,{l},x,t,f.js,1,s,{s},c{i}\n" for i, n, l, s in rows))
    from experiments.dataset import load_labels
    return [row for row in load_labels(path) if row["split"] == "test"]


def _result(run, package, label, action, rule="R6", seconds=10.0):
    (run / f"{package}.json").write_text(json.dumps({
        "package": package, "status": "ok", "steps": 4, "elapsed_s": seconds, "trace": f"{package}.trace.jsonl",
        "decision": {"label": label, "action": action, "rule": rule, "reasons": ["why"]}}))


def test_agent_row_counts_approved_malicious_errors_and_resources(tmp_path):
    labels = _labels(tmp_path)
    run = tmp_path / "test-a"
    run.mkdir()
    (run / "run_meta.json").write_text(json.dumps({"config": {"name": "A-LLM-X"}, "contexts": None, "resources": {
        "container_peak_mb": 120.5, "ollama": {"qwen3.5:9b": {"size_mb": 6000.0, "vram_mb": 5900.0}}}}))
    _result(run, "evil@1.0.0", "malicious", "deny", seconds=10)
    _result(run, "evil2@1.0.0", "benign", "approve", "R7", seconds=30)
    _result(run, "good@1.0.0", "suspicious", "review", "R3", seconds=20)
    _result(run, "good2@1.0.0", "benign", "approve", "R7", seconds=40)
    row = rt.agent_row(run, labels)
    assert row["name"] == "A-LLM-X" and row["malicious_approved"] == 1 and row["median_seconds"] == 25.0
    assert (row["container_peak_mb"], row["model_mb"], row["model_vram_mb"]) == (120.5, 6000.0, 5900.0)
    assert [case["kind"] for case in row["errors"]] == ["malicious approved", "false positive"]
    text = rt.markdown([row], None)
    assert "| A-LLM-X | không | 0,500 | 0,500 | 0,500 | 0,500 | 1 |" in text
    assert "`test-a/evil2@1.0.0.trace.jsonl`" in text


def test_guarddog_row_and_split_filter(tmp_path):
    labels = _labels(tmp_path)
    assert all(row["split"] == "test" for row in labels) and len(labels) == 4
    gd = tmp_path / "gd"
    gd.mkdir()
    for package, issues in (("evil@1.0.0", 2), ("good@1.0.0", 0)):
        (gd / f"{package}.json").write_text(json.dumps({"package": package, "ok": True, "data": {"issues": issues}}))
    text = rt.markdown([], rt.guarddog_row(gd, labels))
    assert "| GuardDog | — | 1,000 | 1,000 | 1,000 | 0,000 |" in text
