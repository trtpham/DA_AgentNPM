"""Build and check cross-review sheets for the four week 2 label rounds.

A sheet only lists what the original labeler recorded; the reviewer reads the
code in an isolated VM/container and fills the empty columns by hand.
"""

import argparse
import csv
from collections import Counter
from pathlib import Path

from experiments.dataset import load_labels

ROUNDS = {
    1: lambda row: row["label"] == "benign",
    2: lambda row: row["cluster"] == "npm-token-worm-2026-03",
    3: lambda row: row["cluster"] == "shai-hulud-2-2025-11",
    4: lambda row: row["label"] != "benign" and row["cluster"] not in ("npm-token-worm-2026-03", "shai-hulud-2-2025-11"),
}
COPIED = ("id", "name", "version", "label", "cluster", "split", "source", "file", "lines", "behavior_main", "technique")
REVIEW = ("decision", "reviewer", "reviewed_at", "observed_behavior", "note")
DECISIONS = {"verified", "revise", "exclude"}
# Labels were drafted by these agents; a cross-review must come from someone else.
ORIGINAL_LABELERS = {"codex", "claude"}


def build_sheet(labels: Path, round_number: int, destination: Path) -> int:
    if destination.exists():
        raise FileExistsError(f"{destination} exists; a filled sheet must not be overwritten")
    rows = [row for row in load_labels(labels) if ROUNDS[round_number](row)]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, COPIED + REVIEW)
        writer.writeheader()
        writer.writerows({field: row[field] for field in COPIED} for row in rows)
    return len(rows)


def check_sheet(path: Path) -> dict:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != COPIED + REVIEW:
            raise ValueError("invalid review sheet columns")
        rows = list(reader)
    problems = []
    for row in rows:
        decision = row["decision"].strip()
        if not decision:
            continue
        if decision not in DECISIONS:
            problems.append(f"{row['id']}: decision must be one of {sorted(DECISIONS)}")
        reviewer = row["reviewer"].strip()
        if not reviewer or reviewer.lower() in ORIGINAL_LABELERS:
            problems.append(f"{row['id']}: reviewer must be a person other than the original labeler")
        if not row["reviewed_at"].strip():
            problems.append(f"{row['id']}: reviewed_at is required")
        if decision in ("revise", "exclude") and not row["note"].strip():
            problems.append(f"{row['id']}: note must explain {decision}")
    decisions = Counter(row["decision"].strip() or "pending" for row in rows)
    return {"rows": len(rows), "decisions": dict(decisions), "problems": problems,
            "complete": not problems and decisions.get("pending", 0) == 0}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or check week 2 cross-review sheets")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("round", type=int, choices=sorted(ROUNDS))
    build.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    build.add_argument("--output", type=Path)
    check = commands.add_parser("check")
    check.add_argument("sheet", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        output = args.output or Path("data/review_rounds") / f"round-{args.round}.csv"
        print(f"{build_sheet(args.labels, args.round, output)} rows -> {output}")
    else:
        result = check_sheet(args.sheet)
        print(result)
        if result["problems"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
