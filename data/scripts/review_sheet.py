"""Build and check cross-review sheets.

Rounds 1-4 are the fixed week 2 rounds over data/labels.csv. Rounds 5 and later (D-2, plan
KE_HOACH_DU_LIEU_400) list chosen ids from a proposal table (data/proposals.csv). A sheet only
lists what the original labeler recorded; the reviewer reads the code in an isolated
VM/container and fills the empty columns by hand.
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


def build_sheet(labels: Path, round_number: int, destination: Path, ids: list[str] | None = None) -> int:
    if destination.exists():
        raise FileExistsError(f"{destination} exists; a filled sheet must not be overwritten")
    table = load_labels(labels)
    if ids is None:
        if round_number not in ROUNDS:
            raise ValueError(f"round {round_number} needs an explicit list of ids")
        rows = [row for row in table if ROUNDS[round_number](row)]
    else:
        by_id = {row["id"]: row for row in table}
        missing = [row_id for row_id in ids if row_id not in by_id]
        if missing or len(set(ids)) != len(ids) or not ids:
            raise ValueError(f"ids must be unique and present in {labels}: missing {missing[:5]}")
        rows = [by_id[row_id] for row_id in ids]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, COPIED + REVIEW)
        writer.writeheader()
        writer.writerows({field: row[field] for field in COPIED} for row in rows)
    return len(rows)


def sheet_ids(path: Path) -> list[str]:
    """Ids listed in an existing sheet, in order (rounds 5+ are defined by their sheet)."""
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return [row["id"] for row in csv.DictReader(stream)]


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
    build.add_argument("round", type=int)
    build.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    build.add_argument("--ids-file", type=Path, help="one id per line; required for rounds 5 and later")
    build.add_argument("--output", type=Path)
    check = commands.add_parser("check")
    check.add_argument("sheet", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        output = args.output or Path("data/review_rounds") / f"round-{args.round}.csv"
        ids = [line.strip() for line in args.ids_file.read_text(encoding="utf-8").splitlines() if line.strip()]             if args.ids_file else None
        print(f"{build_sheet(args.labels, args.round, output, ids)} rows -> {output}")
    else:
        result = check_sheet(args.sheet)
        print(result)
        if result["problems"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
