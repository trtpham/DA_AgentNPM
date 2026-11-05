import csv

import pytest

from data.scripts.review_batches import BATCH_SIZE, run_batches
from data.scripts.review_public_candidates import EXTRA, FIELDS


def test_batches_cover_450_once_and_resume_without_refetch(tmp_path):
    source = tmp_path / "candidates.csv"
    output = tmp_path / "batches"
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        for index in range(450):
            row = dict.fromkeys(FIELDS, "")
            row.update(package=f"pkg-{index:03d}", version="1.0.0")
            writer.writerow(row)

    def review(row):
        return dict(row, metadata_status="verified", metadata_detail="hook_confirmed",
                    integrity_present="yes", label_decision="needs_code_review", hook_commands="{}")

    run_batches(source, output, batch=2, review=review)
    assert sorted(path.name for path in output.glob("*.csv")) == ["batch-02.csv"]
    run_batches(source, output, review=review)
    files = sorted(output.glob("batch-*.csv"))
    assert len(files) == 25
    with_rows = []
    for path in files:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            assert tuple(reader.fieldnames or ()) == FIELDS + EXTRA
            rows = list(reader)
            assert len(rows) == BATCH_SIZE
            with_rows.extend(rows)
    assert [row["package"] for row in with_rows] == [f"pkg-{index:03d}" for index in range(450)]

    def should_not_run(row):
        raise AssertionError(f"refetched {row['package']}")

    run_batches(source, output, review=should_not_run)
    with pytest.raises(ValueError, match="batch must be 1..25"):
        run_batches(source, output, batch=26, review=review)

    first = files[0]
    with first.open(newline="", encoding="utf-8") as stream:
        damaged = list(csv.DictReader(stream))
    damaged[0]["metadata_status"] = ""
    with first.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, FIELDS + EXTRA)
        writer.writeheader()
        writer.writerows(damaged)
    with pytest.raises(ValueError, match="invalid existing batch"):
        run_batches(source, output, batch=1, review=should_not_run)

    def network_failure(row):
        return dict(review(row), metadata_status="fetch_error")

    retry_dir = tmp_path / "retry"
    with pytest.raises(RuntimeError, match="fetch_error"):
        run_batches(source, retry_dir, batch=1, review=network_failure)
    assert not list(retry_dir.glob("*.csv"))
