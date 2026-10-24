"""Validate a human-reviewed label table and assign a stable split."""

import hashlib
from pathlib import Path

import csv

from experiments.dataset import FIELDS, load_labels

LABELS = {"malicious", "suspicious", "benign"}


def prepare_labels(source: Path, destination: Path) -> int:
    rows = load_labels(source)

    seen_ids = set()
    seen_packages = set()
    for row in rows:
        if any(not row.get(field) or not row[field].strip() for field in FIELDS if field != "split"):
            raise ValueError("label evidence and provenance are required")
        if row["label"] not in LABELS:
            raise ValueError("invalid label")
        key = (row["name"], row["version"])
        if row["id"] in seen_ids or key in seen_packages:
            raise ValueError(f"duplicate package version: {key}")
        seen_ids.add(row["id"])
        seen_packages.add(key)
        row["split"] = "test" if int(hashlib.sha256(row["name"].encode()).hexdigest(), 16) % 5 == 0 else "dev"

    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
