import csv

from data.scripts.data_report import TARGETS, decisions, markdown, report
from data.scripts.review_sheet import COPIED, REVIEW


def row(row_id, label, cluster, split="dev"):
    return {"id": row_id, "label": label, "cluster": cluster, "split": split}


def test_only_verified_rows_count_toward_targets():
    rows = [row("1", "benign", "a"), row("2", "malicious", "b"), row("3", "benign", "c"), row("4", "benign", "d")]
    result = report(rows, {"1": "verified", "2": "verified", "3": "", "4": "exclude"}, cap=12)
    assert result["verified"] == {"total": 2, "benign": 1, "malicious": 1, "clusters": 2}
    assert result["review_status"] == {"verified": 2, "pending": 1, "exclude": 1}
    assert result["ready"] is False and result["checks"]["cluster cap"] is True


def test_ready_when_every_target_and_the_cap_hold():
    rows = [row(f"b{i}", "benign", f"c{i % 45}") for i in range(200)]
    rows += [row(f"m{i}", "malicious", f"k{i % 45}") for i in range(200)]
    result = report(rows, {item["id"]: "verified" for item in rows}, cap=12)
    assert result["ready"] is True
    assert report(rows, {item["id"]: "verified" for item in rows}, cap=4)["checks"]["cluster cap"] is False
    assert "Sẵn sàng đóng băng v1: **có**" in markdown(result) and len(TARGETS) == 4


def test_decisions_take_the_latest_round(tmp_path):
    for number, decision in ((1, "revise"), (10, "verified")):
        with (tmp_path / f"round-{number}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, COPIED + REVIEW)
            writer.writeheader()
            writer.writerow({**{field: "" for field in COPIED + REVIEW}, "id": "x", "decision": decision})
    assert decisions(tmp_path) == {"x": "verified"}


def test_ai_review_counts_separately_and_only_when_asked(tmp_path):
    import csv
    from data.scripts.data_report import reviews
    (tmp_path / "ai-review").mkdir()
    with (tmp_path / "round-1.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, ["id", "decision", "observed_behavior", "reviewer", "reviewed_at"])
        writer.writeheader()
        writer.writerows([{"id": "a", "decision": "exclude"}, {"id": "b", "decision": ""}])
    with (tmp_path / "ai-review" / "round-1.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, ["id", "ai_decision", "ai_observed_behavior", "ai_note", "reviewer", "reviewed_at"])
        writer.writeheader()
        writer.writerows([{"id": "a", "ai_decision": "verified", "reviewer": "Claude (AI)"},
                          {"id": "b", "ai_decision": "verified", "reviewer": "Claude (AI)"}])
    assert reviews(tmp_path)["b"]["decision"] == ""
    found = reviews(tmp_path, include_ai=True)
    assert found["a"]["decision"] == "exclude" and found["a"]["review_kind"] == "human"
    assert found["b"]["decision"] == "verified" and found["b"]["review_kind"] == "ai"


def test_later_ai_round_replaces_earlier_ai_decision(tmp_path):
    from data.scripts.data_report import reviews
    (tmp_path / "ai-review").mkdir()
    for number, decision in ((5, "revise"), (27, "verified")):
        with (tmp_path / "ai-review" / f"round-{number}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, ["id", "ai_decision", "ai_observed_behavior", "ai_note", "reviewer", "reviewed_at"])
            writer.writeheader()
            writer.writerow({"id": "x", "ai_decision": decision, "reviewer": "Claude (AI)"})
    assert reviews(tmp_path, include_ai=True)["x"]["decision"] == "verified"


def test_trimmed_rows_stop_counting_as_verified(tmp_path):
    from data.scripts.data_report import TRIM_FILE, reviews
    with (tmp_path / "round-1.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, ["id", "decision", "observed_behavior", "reviewer", "reviewed_at"])
        writer.writeheader()
        writer.writerows([{"id": "a", "decision": "verified"}, {"id": "b", "decision": "verified"},
                          {"id": "c", "decision": "exclude"}])
    (tmp_path / TRIM_FILE).write_text("id,label,cluster,reason\na,benign,k,x\nc,benign,k,x\n", encoding="utf-8")
    found = reviews(tmp_path)
    assert found["a"]["decision"] == "trimmed" and found["a"]["review_kind"] == "human"
    assert found["b"]["decision"] == "verified" and found["c"]["decision"] == "exclude"
    result = report([row("a", "benign", "k"), row("b", "benign", "k")], {k: v["decision"] for k, v in found.items()})
    assert result["verified"]["total"] == 1 and result["review_status"]["trimmed"] == 1
