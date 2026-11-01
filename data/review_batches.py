"""Review npm manifests in resumable groups of 18, without running packages."""

import argparse
import csv
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from data.review_public_candidates import EXTRA, FIELDS, SOURCE, review_row

BATCH_SIZE = 18
OUTPUT_DIR = Path(__file__).with_name("review_450") / "batches"


def run_batches(source: Path = SOURCE, output_dir: Path = OUTPUT_DIR, batch: int | None = None,
                review=review_row) -> None:
    with source.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("invalid candidate columns")
        rows = list(reader)
    if len(rows) != 450 or len({(row["package"], row["version"]) for row in rows}) != 450:
        raise ValueError("expected 450 unique package versions")
    if any(None in row or None in row.values() for row in rows):
        raise ValueError("invalid candidate row")

    count = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
    if batch is not None and not 1 <= batch <= count:
        raise ValueError(f"batch must be 1..{count}")
    output_dir.mkdir(parents=True, exist_ok=True)
    for index in ([batch] if batch is not None else range(1, count + 1)):
        selected = rows[(index - 1) * BATCH_SIZE:index * BATCH_SIZE]
        output = output_dir / f"batch-{index:02d}.csv"
        if output.exists():
            with output.open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                existing = list(reader)
                if tuple(reader.fieldnames or ()) != FIELDS + EXTRA or [
                    (row["package"], row["version"]) for row in existing
                ] != [(row["package"], row["version"]) for row in selected] or any(
                    None in row or not row["metadata_status"] or not row["reviewed_at"]
                    or any(row[field] != candidate[field] for field in FIELDS)
                    for row, candidate in zip(existing, selected)
                ):
                    raise ValueError(f"invalid existing batch: {output}")
            print(f"Batch {index:02d}/{count}: already complete")
            continue

        with ThreadPoolExecutor(max_workers=6) as pool:
            reviewed = list(pool.map(review, selected))
        if any(row["metadata_status"] == "fetch_error" for row in reviewed):
            raise RuntimeError(f"batch {index:02d} has fetch_error; retry this batch")
        today = datetime.now(timezone(timedelta(hours=7))).date().isoformat()
        reviewed = [dict(row, reviewed_at=today) for row in reviewed]
        temporary = output.with_suffix(".tmp")
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, FIELDS + EXTRA)
            writer.writeheader()
            writer.writerows(reviewed)
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(temporary, output)
        statuses = Counter(row["metadata_status"] for row in reviewed)
        print(f"Batch {index:02d}/{count}: {len(reviewed)} packages, {dict(statuses)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, help="1-based batch number; omit to run all 25")
    args = parser.parse_args()
    run_batches(batch=args.batch)


if __name__ == "__main__":
    main()
