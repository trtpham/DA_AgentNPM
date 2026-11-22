import itertools
import json

from agent.decide import decide
from experiments.osv_ablation import (ablate, consistency_problems, load_osv, osv_malicious, osv_only,
                                      with_osv)
from tests.test_decide import verdict

GOOD = [{"file": "setup.js", "lines": "1", "exists": True}]
BAD = [{"file": "setup.js", "lines": "1", "exists": False}]


def test_replay_matches_decide_for_every_rule_path():
    """For each combination of inputs, replaying R5 on the stored no-OSV decision gives decide()'s answer."""
    cases = itertools.product(("benign", "malicious", "suspicious"), (0.5, 0.97), (GOOD, BAD),
                              (False, True), (False, True), (False, True), (False, True))
    checked = 0
    for label, confidence, evidence, canary, error, approve_ok, flow in cases:
        item = verdict(label, confidence)
        kwargs = dict(canary_touched=canary, run_error=error, auto_approve_allowed=approve_ok,
                      flow_risks=["secret -> network"] if flow else [], deny_threshold=0.95,
                      approve_threshold=0.95)
        stored = {"package": "p@1.0.0", "verdict": item.model_dump(), "decision": decide(item, evidence, **kwargs)}
        for flag in (False, True):
            expected = decide(item, evidence, osv_malicious=flag, **kwargs)
            replayed, _ = with_osv(stored, flag)
            assert {k: replayed["decision"][k] for k in ("label", "action", "rule")} == \
                {k: expected[k] for k in ("label", "action", "rule")}
            checked += 1
    assert checked == 3 * 2 * 2 * 2 * 2 * 2 * 2 * 2


def test_osv_flag_matches_agent_run_derivation():
    assert osv_malicious({"osv": {"ok": True, "data": {"malicious": True}}}) is True
    assert osv_malicious({"osv": {"ok": False, "data": {"malicious": True}}}) is False
    assert osv_malicious({"osv": {"ok": True, "data": None}}) is False
    assert osv_malicious(None) is False


def test_load_osv_maps_scoped_names_and_failed_lookups(tmp_path):
    (tmp_path / "@scope__pkg@1.0.0.json").write_text(
        json.dumps({"osv": {"ok": True, "data": {"malicious": True}}}), encoding="utf-8")
    (tmp_path / "plain@2.0.0.json").write_text(json.dumps({"osv": {"ok": False, "data": None}}), encoding="utf-8")
    flags = load_osv(tmp_path, ["@scope/pkg@1.0.0", "plain@2.0.0", "absent@1.0.0"])
    assert flags == {"@scope/pkg@1.0.0": True, "plain@2.0.0": None, "absent@1.0.0": None}


def test_ablate_counts_changes_and_approved_non_benign():
    labels = [{"name": "a", "version": "1", "label": "malicious"},
              {"name": "b", "version": "1", "label": "benign"}]
    benign_verdict = verdict("benign").model_dump()
    results = [
        {"package": "a@1", "status": "ok", "verdict": benign_verdict,
         "decision": {"label": "benign", "action": "approve", "rule": "R7"}},
        {"package": "b@1", "status": "ok", "verdict": benign_verdict,
         "decision": {"label": "benign", "action": "approve", "rule": "R7"}},
    ]
    out = ablate(results, labels, {"a@1": True, "b@1": False})
    assert out["changed"] == ["a@1"]
    assert out["approved_not_benign"] == {"without_osv": 1, "with_osv": 0}
    assert out["without_osv"]["binary"]["fn"] == 1 and out["with_osv"]["binary"]["tp"] == 1


def test_consistency_flags_runs_that_already_used_osv():
    benign_verdict = verdict("benign").model_dump()
    rows = [{"package": "x@1", "verdict": benign_verdict, "decision": {"rule": "R5"}},
            {"package": "y@1", "verdict": verdict("malicious").model_dump(), "decision": {"rule": "R7"}},
            {"package": "z@1", "verdict": None, "decision": {"rule": "R2"}}]
    problems = consistency_problems(rows)
    assert any("x@1" in p for p in problems) and any("y@1" in p for p in problems)
    assert not any("z@1" in p for p in problems)


def test_osv_only_baseline_predicts_from_flag():
    rows = osv_only(["a@1", "b@1", "c@1"], {"a@1": True, "b@1": False, "c@1": None})
    assert [r["decision"]["label"] for r in rows] == ["malicious", "benign", "benign"]
