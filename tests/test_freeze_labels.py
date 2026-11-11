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


def ai_sheet(path, decisions):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, ["id", "ai_decision", "ai_observed_behavior", "ai_note", "reviewer", "reviewed_at"])
        writer.writeheader()
        for row_id, decision, observed in decisions:
            writer.writerow({"id": row_id, "ai_decision": decision, "ai_observed_behavior": observed, "ai_note": "",
                             "reviewer": "Claude (AI)", "reviewed_at": "2026-11-11"})


def test_ai_review_is_opt_in_human_wins_and_source_is_recorded(tmp_path):
    rows = [row(f"b{i}", "benign", f"cb{i}", technique="draft-no-risky-sign") for i in range(10)]
    rows += [row(f"m{i}", "malicious", f"cm{i}") for i in range(10)]
    # people decided the malicious rows and b0 (exclude); Claude reviewed every benign row
    sheet(tmp_path / "round-5.csv", [(f"m{i}", "verified", "steals token") for i in range(10)] + [("b0", "exclude", "")]
          + [(f"b{i}", "", "") for i in range(1, 10)])
    ai_sheet(tmp_path / "ai-review" / "round-5.csv", [(f"b{i}", "verified", "prints a message") for i in range(10)])
    with pytest.raises(ValueError, match="no verified rows"):  # without the flag Claude's review is ignored
        freeze(tmp_path / "x.csv", 0.6, tmp_path, tables=[rows[:10]], hashes={})
    output = tmp_path / "labels-v1.csv"
    result = freeze(output, 0.6, tmp_path, tables=[rows], hashes={}, include_ai=True)
    assert result["rows"] == 19 and result["reviewed_by"] == {"human": 10, "ai": 9}
    with output.open(encoding="utf-8") as stream:
        frozen = {item["id"]: item for item in csv.DictReader(stream)}
    assert "b0" not in frozen and frozen["b1"]["technique"] == "reviewed-ai" and frozen["m1"]["technique"] == "t"
    with (tmp_path / "labels-v1-review.csv").open(encoding="utf-8") as stream:
        source = {item["id"]: item for item in csv.DictReader(stream)}
    assert source["b1"]["review_kind"] == "ai" and source["b1"]["reviewer"] == "Claude (AI)"
    assert source["m1"]["review_kind"] == "human"
