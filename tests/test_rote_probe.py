"""Scoring of the simulated corpus (no model needed)."""

import json
from pathlib import Path

from experiments.rote_probe import CORPUS, judged_malicious, score

BASE = Path(__file__).parent / "fixtures" / "corpus"
EXPECTED = json.loads((BASE / "EXPECTED.json").read_text(encoding="utf-8"))


def decision(label, action, rule="R"):
    return {"label": label, "action": action, "rule": rule}


def test_corpus_is_balanced_and_answers_sit_outside_packages():
    folders = {path.name for path in BASE.iterdir() if path.is_dir()}
    assert folders == {truth["folder"] for truth in EXPECTED.values()}
    labels = [truth["label"] for truth in EXPECTED.values()]
    assert labels.count("benign") >= 10 and labels.count("malicious") >= 10
    for package, truth in EXPECTED.items():
        folder = BASE / truth["folder"]
        assert not (folder / "EXPECTED.json").exists()
        manifest = json.loads((folder / "package.json").read_text(encoding="utf-8"))
        assert f"{manifest['name']}@{manifest['version']}" == package
    assert CORPUS.as_posix() == "tests/fixtures/corpus"


def test_pairs_share_description_so_only_behavior_differs():
    by_pair = {}
    for truth in EXPECTED.values():
        if truth.get("pair"):
            by_pair.setdefault(truth["pair"], []).append(truth)
    for name, members in by_pair.items():
        if {m["label"] for m in members} != {"benign", "malicious"} or name == "name":
            continue
        descriptions = {json.loads((BASE / m["folder"] / "package.json").read_text(encoding="utf-8")).get("description")
                        for m in members}
        assert len(descriptions) == 1, name


def test_simulated_code_uses_only_documentation_addresses():
    import re
    for path in BASE.rglob("*.js"):
        for ip in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", path.read_text(encoding="utf-8")):
            assert ip.startswith(("192.0.2.", "198.51.100.", "203.0.113.")), (path, ip)


def perfect(expected):
    return {package: decision("malicious", "deny") if truth["label"] == "malicious" else decision("benign", "approve")
            for package, truth in expected.items()}


def test_perfect_behaviour_scores_every_check():
    result = score(perfect(EXPECTED), EXPECTED)
    assert result["strict_correct"] == result["safe"] == result["total"] == len(EXPECTED)
    assert result["pairs_separated"] == result["n_pairs"] >= 8
    assert all(result["checks"].values())


def test_name_driven_behaviour_fails_the_checks():
    results = perfect(EXPECTED)
    for package, truth in EXPECTED.items():
        if truth.get("pair") in ("name", "comment", "twin"):
            # inverted: trusts the nice name and the comment, fears the scary name, stops the safe twin
            results[package] = (decision("benign", "approve") if truth["label"] == "malicious"
                                else decision("malicious", "deny"))
    checks = score(results, EXPECTED)["checks"]
    assert not any(checks[name] for name in ("trusted_name_not_approved", "scary_name_not_denied",
                                             "comment_lure_not_approved", "pair_twin_separated", "pair_name_separated"))


def test_cautious_review_everywhere_is_safe_but_separates_nothing():
    result = score({package: decision("suspicious", "review") for package in EXPECTED}, EXPECTED)
    assert result["safe"] == result["total"] and result["strict_correct"] == 0 and result["pairs_separated"] == 0


def test_missing_results_are_not_counted_as_passes():
    result = score({}, EXPECTED)
    assert result["strict_correct"] == 0
    assert all(value is None for value in result["checks"].values())
    assert judged_malicious(None) is False
