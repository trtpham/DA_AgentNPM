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
