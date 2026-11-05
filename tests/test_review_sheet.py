import csv

import pytest

from data.scripts.review_sheet import COPIED, REVIEW, build_sheet, check_sheet
from experiments.dataset import FIELDS


def write_labels(path):
    rows = [
        ("1", "lib-a", "1.0.0", "benign", "fam-a"),
        ("2", "lib-b", "1.0.0", "malicious", "npm-token-worm-2026-03"),
        ("3", "lib-c", "1.0.0", "suspicious", "fam-c"),
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        for row_id, name, version, label, cluster in rows:
            writer.writerow({"id": row_id, "name": name, "version": version, "label": label,
                             "behavior_main": "b", "technique": "t", "file": "x.js", "lines": "1",
                             "source": "https://example.invalid", "split": "dev", "cluster": cluster})


def fill(path, **values):
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        row.update(values)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, COPIED + REVIEW)
        writer.writeheader()
        writer.writerows(rows)


def test_rounds_select_rows_and_never_overwrite(tmp_path):
    labels = tmp_path / "labels.csv"
    write_labels(labels)
    assert build_sheet(labels, 1, tmp_path / "r1.csv") == 1
    assert build_sheet(labels, 2, tmp_path / "r2.csv") == 1
    assert build_sheet(labels, 4, tmp_path / "r4.csv") == 1
    with pytest.raises(FileExistsError):
        build_sheet(labels, 1, tmp_path / "r1.csv")
    assert check_sheet(tmp_path / "r1.csv") == {"rows": 1, "decisions": {"pending": 1},
                                                "problems": [], "complete": False}


def test_check_rejects_self_review_and_unexplained_exclusion(tmp_path):
    labels = tmp_path / "labels.csv"
    write_labels(labels)
    sheet = tmp_path / "r1.csv"
    build_sheet(labels, 1, sheet)
    fill(sheet, decision="exclude", reviewer="Codex", reviewed_at="")
    problems = check_sheet(sheet)["problems"]
    assert len(problems) == 3
    fill(sheet, decision="verified", reviewer="Reviewer A", reviewed_at="2026-11-04")
    assert check_sheet(sheet)["complete"] is True
