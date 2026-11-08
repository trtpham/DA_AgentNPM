"""Freeze labels v1 (plan KE_HOACH_DU_LIEU_400, 19/11/2026): verified rows only, split by cluster.

    py -3.14 -m data.scripts.freeze_labels --output data/labels-v1.csv

1. D-3 dedupe of data/labels.csv + data/proposals.csv (exact duplicates, look-alike clusters, cap 12).
2. Keep only rows whose latest round-sheet decision is `verified` (a person other than the drafter).
3. A drafted row takes the reviewer's `observed_behavior` as `behavior_main`; its draft technique
   becomes `reviewed`. Labels are never changed here: a `revise` must be fixed and re-verified.
4. A cluster that ends up with two labels is split per label, then prepare_labels assigns dev/test
   by cluster (test share 0.6 by default, as in the plan). Refuses to overwrite an existing file.
"""

import argparse
import csv
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

from data.scripts.data_report import ROUNDS_DIR
from data.scripts.dedupe_labels import CAP, DEFAULT_HASHES, DEFAULT_TABLES, dedupe, load_hashes
from data.scripts.prepare_labels import prepare_labels
from experiments.dataset import FIELDS, load_labels


def reviewed(rounds_dir: Path = ROUNDS_DIR) -> dict[str, dict]:
    """Latest sheet row per id across all rounds."""
    found = {}
    for path in sorted(rounds_dir.glob("round-*.csv"), key=lambda item: int(item.stem.split("-")[1])):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                found[row["id"]] = row
    return found


def freeze_rows(rows: list[dict], sheets: dict[str, dict]) -> list[dict]:
    kept = []
    for row in rows:
        sheet = sheets.get(row["id"], {})
        if sheet.get("decision", "").strip() != "verified":
            continue
        row = dict(row)
        if row["technique"].startswith("draft-"):
            observed = sheet.get("observed_behavior", "").strip()
            if not observed:
                continue  # a verified draft must say, in the reviewer's words, what was seen
            row["behavior_main"], row["technique"] = observed, "reviewed"
        kept.append(row)
    labels_per_cluster: dict[str, set] = {}
    for row in kept:
        labels_per_cluster.setdefault(row["cluster"], set()).add(row["label"])
    for row in kept:
        if len(labels_per_cluster[row["cluster"]]) > 1:
            row["cluster"] = f"{row['cluster']}/{row['label']}"
        row["split"] = ""
    return kept


def freeze(output: Path, test_share: float = 0.6, rounds_dir: Path = ROUNDS_DIR, tables=None, hashes=None) -> dict:
    if output.exists():
        raise FileExistsError(f"{output} exists; a frozen label set is never overwritten")
    tables = tables if tables is not None else [load_labels(path) for path in DEFAULT_TABLES if path.is_file()]
    rows = dedupe(tables, hashes if hashes is not None else load_hashes(list(DEFAULT_HASHES)), CAP)["rows"]
    kept = freeze_rows(rows, reviewed(rounds_dir))
    if not kept:
        raise ValueError("no verified rows to freeze")
    with tempfile.TemporaryDirectory() as directory:
        staging = Path(directory) / "verified.csv"
        with staging.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, FIELDS)
            writer.writeheader()
            writer.writerows(kept)
        prepare_labels(staging, output, test_share)
    frozen = load_labels(output)
    return {"rows": len(frozen), "labels": dict(sorted(Counter(row["label"] for row in frozen).items())),
            "splits": dict(sorted(Counter(row["split"] for row in frozen).items())),
            "clusters": len({row["cluster"] for row in frozen})}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Freeze labels v1 from verified rows")
    parser.add_argument("--output", type=Path, default=Path("data/labels-v1.csv"))
    parser.add_argument("--test-share", type=float, default=0.6)
    args = parser.parse_args()
    print(json.dumps(freeze(args.output, args.test_share), ensure_ascii=False))


if __name__ == "__main__":
    main()
