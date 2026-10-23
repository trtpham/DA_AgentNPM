"""Validate a human-reviewed label table and assign a stable split."""

import csv
import hashlib
from pathlib import Path

FIELDS = ("package", "version", "label", "source", "source_url", "reviewer", "split")
LABELS = {"malicious", "suspicious", "benign"}


def prepare_labels(source: Path, destination: Path) -> int:
    with source.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("invalid labels.csv columns")
        rows = list(reader)

    seen = set()
    for row in rows:
        if any(not row[field].strip() for field in FIELDS[:-1]):
            raise ValueError("label provenance and reviewer are required")
        if row["label"] not in LABELS:
            raise ValueError("invalid label")
        key = (row["package"], row["version"])
        if key in seen:
            raise ValueError(f"duplicate package version: {key}")
        seen.add(key)
        row["split"] = "test" if int(hashlib.sha256(row["package"].encode()).hexdigest(), 16) % 5 == 0 else "dev"

    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
