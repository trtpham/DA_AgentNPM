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
    clusters = {}
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
        group = clusters.setdefault(row["cluster"], [])
        if group and group[0]["label"] != row["label"]:
            raise ValueError(f"mixed labels in cluster: {row['cluster']}")
        group.append(row)

    for label in LABELS:
        groups = sorted(((cluster, group) for cluster, group in clusters.items() if group[0]["label"] == label),
                        key=lambda item: (hashlib.sha256(item[0].encode()).digest(), item[0]))
        if not groups:
            continue
        total = sum(len(group) for _, group in groups)
        possible = {0: 0}
        for index, (_, group) in enumerate(groups):
            for count, mask in list(possible.items()):
                possible.setdefault(count + len(group), mask | (1 << index))
        # Exact 80/20 can be impossible when a cluster contains multiple samples.
        counts = [count for count in possible if 0 < count < total] if len(groups) > 1 else [0]
        chosen = min(counts, key=lambda count: (abs(count - total * 0.2), count))
        mask = possible[chosen]
        for index, (_, group) in enumerate(groups):
            for row in group:
                row["split"] = "test" if mask & (1 << index) else "dev"

    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
