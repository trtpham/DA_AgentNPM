import csv

import pytest

from data.scripts.freeze_labels import freeze, freeze_rows
from data.scripts.review_sheet import COPIED, REVIEW


def row(row_id, label, cluster, technique="t", behavior="b"):
    return {"id": row_id, "name": row_id, "version": "1.0.0", "label": label, "behavior_main": behavior,
            "technique": technique, "file": "a.js", "lines": "1", "source": "https://example.invalid/x.tgz",
            "split": "pending", "cluster": cluster}


def sheet(path, decisions):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, COPIED + REVIEW)
        writer.writeheader()
        for row_id, decision, observed in decisions:
            writer.writerow({**{field: "x" for field in COPIED}, "id": row_id, "decision": decision,
                             "reviewer": "Reviewer", "reviewed_at": "2026-11-12", "observed_behavior": observed,
                             "note": ""})


def test_only_verified_rows_and_reviewer_words_replace_drafts():
    rows = [row("a", "benign", "c1", technique="draft-no-risky-sign"), row("b", "benign", "c2"),
            row("c", "malicious", "c3"), row("d", "benign", "c4", technique="draft-b-light")]
    sheets = {"a": {"decision": "verified", "observed_behavior": "prints a thank-you message"},
              "b": {"decision": "revise"}, "c": {"decision": "verified"},
              "d": {"decision": "verified", "observed_behavior": ""}}
    kept = freeze_rows(rows, sheets)
    assert [item["id"] for item in kept] == ["a", "c"]
    assert (kept[0]["behavior_main"], kept[0]["technique"]) == ("prints a thank-you message", "reviewed")


def test_mixed_cluster_is_split_per_label():
    rows = [row("a", "benign", "same"), row("b", "malicious", "same")]
    kept = freeze_rows(rows, {"a": {"decision": "verified"}, "b": {"decision": "verified"}})
    assert {item["cluster"] for item in kept} == {"same/benign", "same/malicious"}


def test_freeze_writes_split_and_never_overwrites(tmp_path):
    rows = [row(f"b{i}", "benign", f"cb{i}") for i in range(10)] + [row(f"m{i}", "malicious", f"cm{i}") for i in range(10)]
    sheet(tmp_path / "round-5.csv", [(item["id"], "verified", "seen") for item in rows])
    output = tmp_path / "labels-v1.csv"
    result = freeze(output, 0.6, tmp_path, tables=[rows], hashes={})
    assert result["rows"] == 20 and result["splits"] == {"dev": 8, "test": 12}
    with pytest.raises(FileExistsError):
        freeze(output, 0.6, tmp_path, tables=[rows], hashes={})
