import json

from experiments.calibration import calibrate, markdown, samples


def test_perfect_calibration_has_zero_ece():
    pairs = [(0.9, True)] * 9 + [(0.9, False)] + [(0.1, False)] * 9 + [(0.1, True)]
    result = calibrate(pairs)
    assert result["ece"] == 0.0 and result["n"] == 20
    assert result["brier"] == round((9 * 0.01 + 0.81 + 9 * 0.01 + 0.81) / 20, 4)


def test_inverted_calibration_has_large_ece():
    result = calibrate([(0.95, False)] * 10 + [(0.05, True)] * 10)
    assert result["ece"] >= 0.9 and result["brier"] > 0.8
    assert result["bins"][4]["accuracy"] == 0.0 and result["bins"][0]["accuracy"] == 1.0


def test_confidence_one_falls_in_last_bin_and_empty_input():
    assert calibrate([(1.0, True)])["bins"][4]["n"] == 1
    assert calibrate([]) == {"n": 0, "bins": calibrate([])["bins"], "ece": None, "brier": None}


def test_samples_use_model_verdict_from_trace_not_decision(tmp_path):
    run = tmp_path / "run-1"
    run.mkdir()
    trace = [{"type": "verdict", "valid": False, "verdict": {"label": "malicious", "confidence": 0.2}},
             {"type": "verdict", "valid": True, "verdict": {"label": "benign", "confidence": 0.9}},
             {"type": "decision", "final_label": "suspicious"}]
    (run / "t.trace.jsonl").write_text("\n".join(map(json.dumps, trace)), encoding="utf-8")
    (run / "p@1.json").write_text(json.dumps({"package": "p@1", "trace": "t.trace.jsonl",
                                              "verdict": {"label": "suspicious", "confidence": 0.9}}), encoding="utf-8")
    (run / "q@1.json").write_text(json.dumps({"package": "q@1"}), encoding="utf-8")  # failed run, no trace
    (run / "run_meta.json").write_text("{}", encoding="utf-8")
    assert samples(run, {"p@1": "benign", "q@1": "benign"}) == [(0.9, True)]
    assert "| run-1 | 1 |" in markdown({"run-1": calibrate([(0.9, True)])})
