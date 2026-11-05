import csv
import json
from pathlib import Path

import pytest

from agent.decide import decide
from agent.schema import Verdict
from experiments import run_batch as batch
from experiments.dataset import FIELDS

FIXTURES = Path(__file__).parent / "fixtures"


def fake_analyze(package, model, max_steps, trace, **kwargs):
    trace.emit("run_start", model=model, config_name=None, max_steps=max_steps)
    if "canary" in package:
        trace.emit("error", kind="model_error", message="boom")
        trace.emit("decision", threshold={}, evidence_checks=[], final_label="suspicious",
                   final_action="review", dry_run=True, rule="R2", reasons=["Analysis failed"])
        raise RuntimeError("boom")
    verdict = Verdict.model_validate({
        "package": "benign-install-fixture@1.0.0", "label": "benign", "confidence": 0.9,
        "description": "Installation writes only a fixed local test marker",
        "behaviors": [{"behavior": "Writes marker", "technique": "fs.writeFileSync", "severity": "low",
                       "evidence": {"file": "postinstall.js", "lines": "2"}, "analysis": "Fixed text.",
                       "impact": "Local marker."}],
        "action": "approve", "remediation": []})
    decision = decide(verdict, [{"exists": True}], auto_approve_allowed=True)
    trace.emit("decision", threshold={}, evidence_checks=[], final_label=decision["label"],
               final_action=decision["action"], dry_run=True, rule=decision["rule"], reasons=decision["reasons"])
    trace.emit("run_end", elapsed_s=0.1, steps=2, tokens_per_s=None)
    return verdict, 2


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(batch, "_ollama", lambda _path: None)


def test_batch_isolates_failures_records_meta_and_resumes(tmp_path):
    inputs = batch.select_inputs(None, None, [], [FIXTURES / "benign-package", FIXTURES / "canary-package"], False)
    counts = batch.run_batch("run-1", "A-TLM", inputs, tmp_path, analyze=fake_analyze)
    assert counts == {"done": 2, "skipped": 0, "errors": 1}
    run_dir = tmp_path / "run-1"
    ok = json.loads((run_dir / "benign-install-fixture@1.0.0.json").read_text(encoding="utf-8"))
    failed = json.loads((run_dir / "canary-fixture@1.0.0.json").read_text(encoding="utf-8"))
    assert ok["decision"]["action"] == "approve" and ok["planned_command"] == ["npm", "approve-scripts", "benign-install-fixture@1.0.0"]
    assert failed["status"] == "error" and failed["decision"]["rule"] == "R2" and failed["planned_command"] is None
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["model"] == "qwen3.5:0.8b" and meta["chat_options"]["num_ctx"] == 16384
    assert meta["inputs"] == ["benign-install-fixture@1.0.0", "canary-fixture@1.0.0"]

    (run_dir / "canary-fixture@1.0.0.json").unlink()  # simulate a crash before the result was written
    assert batch.run_batch("run-1", "A-TLM", inputs, tmp_path, analyze=fake_analyze) == {"done": 1, "skipped": 1, "errors": 1}
    assert len(json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))["resumed_at"]) == 1
    with pytest.raises(ValueError, match="different config"):
        batch.run_batch("run-1", "A-LLM", inputs, tmp_path, analyze=fake_analyze)


def test_non_benign_rows_need_isolation_and_labels_stay_out_of_inputs(tmp_path):
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        for name, label, split in (("good", "benign", "dev"), ("bad", "malicious", "dev"), ("later", "benign", "test")):
            writer.writerow({"id": name, "name": name, "version": "1.0.0", "label": label, "behavior_main": "b",
                             "technique": "t", "file": "x.js", "lines": "1", "source": "s", "split": split, "cluster": name})
    with pytest.raises(ValueError, match="not benign"):
        batch.select_inputs(labels, "dev", [], [], False)
    inputs = batch.select_inputs(labels, "dev", ["good"], [], False)
    assert inputs == [{"package": "good@1.0.0", "name": "good", "version": "1.0.0"}]
    assert batch.select_inputs(labels, "dev", [], [], True)[1]["package"] == "bad@1.0.0"


# --- W5-9: chat options come from experiments/configs/*.yaml (AGENTS §6.7) ------------------------
def test_shipped_configs_hold_num_ctx_and_temperature():
    for variant in ("A-LLM", "A-SLM", "A-TLM"):
        options = batch.load_config(variant)["options"]
        assert set(options) >= {"num_ctx", "temperature"} and set(options) <= set(batch.OPTION_TYPES)
        assert isinstance(options["num_ctx"], int) and options["temperature"] == 0


def test_options_change_only_through_yaml(tmp_path):
    (tmp_path / "X.yaml").write_text('name: X\nmodel: "m:1b"\nmax_steps: 15\ndeny_threshold: 0.8\n'
                                     "approve_threshold: 0.8\noptions:\n  num_ctx: 4096\n  temperature: 0.2\n",
                                     encoding="utf-8")
    config = batch.load_config("X", tmp_path)
    assert config["model"] == "m:1b" and config["options"] == {"num_ctx": 4096, "temperature": 0.2}


def test_unknown_option_is_rejected(tmp_path):
    (tmp_path / "X.yaml").write_text("name: X\nmodel: m\nmax_steps: 15\ndeny_threshold: 0.8\n"
                                     "approve_threshold: 0.8\noptions:\n  num_cxt: 4096\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown option"):
        batch.load_config("X", tmp_path)


def test_run_meta_matches_yaml_options(tmp_path, monkeypatch):
    seen = {}

    def recording_analyze(package, model, max_steps, trace, **kwargs):
        seen.update(kwargs["options"])
        return fake_analyze(package, model, max_steps, trace, **kwargs)

    inputs = batch.select_inputs(None, None, [], [FIXTURES / "benign-package"], False)
    batch.run_batch("run-opts", "A-SLM", inputs, tmp_path, analyze=recording_analyze)
    meta = json.loads((tmp_path / "run-opts" / "run_meta.json").read_text(encoding="utf-8"))
    yaml_options = batch.load_config("A-SLM")["options"]
    assert seen == yaml_options
    assert {key: meta["chat_options"][key] for key in yaml_options} == yaml_options


def test_chat_sends_yaml_overrides_to_ollama(monkeypatch):
    from agent import run as agent_run

    sent = {}

    class FakeResponse:
        status = 200

        def read(self, *args):
            return json.dumps({"message": {"role": "assistant", "content": "{}"}}).encode()

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, url, body, headers):
            sent.update(json.loads(body))

        def getresponse(self):
            return FakeResponse()

        def close(self):
            pass

    monkeypatch.setattr(agent_run, "HTTPConnection", FakeConnection)
    agent_run._chat("m", [], overrides={"num_ctx": 8192, "temperature": 0.1, "num_gpu": 99})
    assert sent["options"]["num_ctx"] == 8192 and sent["options"]["temperature"] == 0.1
    assert sent["options"]["num_gpu"] == 99
    agent_run._chat("m", [])
    assert sent["options"]["num_ctx"] == agent_run.CHAT_OPTIONS["num_ctx"] and "num_gpu" not in sent["options"]
