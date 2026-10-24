"""Read the frozen Week 2 label contract."""

import csv
from pathlib import Path

FIELDS = ("id", "name", "version", "label", "behavior_main", "technique", "file", "lines", "source", "split", "cluster")


def load_labels(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("invalid labels.csv columns")
        rows = list(reader)
        if any(None in row or None in row.values() for row in rows):
            raise ValueError("invalid labels.csv row")
        return rows
