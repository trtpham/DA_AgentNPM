"""D-2: turn triage group A candidates into draft proposals and a cross-review round.

    py -3.14 -m data.scripts.propose_labels 5 --limit 40
    py -3.14 -m data.scripts.review_evidence 5 --labels data/proposals.csv   (container)

A proposal is a draft written by Claude from static triage only: label `benign`, the file a hook
runs and its first lines. It is never used for measurement until a person other than the drafter
marks it `verified` in the round sheet. Only group A is proposed automatically; group B needs
someone to read the code first. Clusters are capped so no family dominates (plan, section 2).
"""

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

from data.scripts.review_sheet import build_sheet
from experiments.dataset import FIELDS, load_labels

TRIAGE = Path("data/review_450/triage_450.csv")
LABELS = Path("data/labels.csv")
PROPOSALS = Path("data/proposals.csv")
ROUNDS_DIR = Path("data/review_rounds")
CLUSTER_CAP = 12
MAX_CITED_LINES = 150


def cluster_of(name: str) -> str:
    """A scope groups its packages; an unscoped package is its own cluster (D-3 merges look-alikes)."""
    return name.split("/")[0] if name.startswith("@") else name


def draft(row: dict) -> dict | None:
    """Draft proposal for one group A triage row, or None when there is nothing to cite."""
    entries = json.loads(row.get("entries") or "[]")
    if not entries or not row.get("tarball"):
        return None
    entry = entries[0]
    if entry["file"] == "package.json" and entry.get("line"):
        file, lines = "package.json", str(entry["line"])
        action = f"{entry['hook']} runs an inline command"
    elif entry.get("lines"):
        file, lines = entry["file"], f"1-{min(entry['lines'], MAX_CITED_LINES)}"
        action = f"{entry['hook']} runs {file}"
    else:
        return None
    slug = re.sub(r"[^a-z0-9.]+", "-", row["package"].lower()).strip("-")
    return {"id": f"cand-{slug}-{row['version']}", "name": row["package"], "version": row["version"],
            "label": "benign",
            "behavior_main": f"{action}; static triage found no risky sign (draft, read before verifying)",
            "technique": "draft-no-risky-sign", "file": file, "lines": lines, "source": row["tarball"],
            "split": "pending", "cluster": cluster_of(row["package"])}


def propose(triage: Path, labels: Path, proposals: Path, limit: int, cap: int = CLUSTER_CAP) -> list[dict]:
    """Append up to `limit` new group A drafts to `proposals`; returns the rows added."""
    existing = load_labels(labels) + (load_labels(proposals) if proposals.is_file() else [])
    taken = {(row["name"], row["version"]) for row in existing}
    per_cluster = Counter(row["cluster"] for row in existing)
    with triage.open(encoding="utf-8", newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row["group"] == "A"]
    added = []
    for row in rows:
        if len(added) == limit:
            break
        proposal = draft(row)
        if proposal is None or (proposal["name"], proposal["version"]) in taken or per_cluster[proposal["cluster"]] >= cap:
            continue
        taken.add((proposal["name"], proposal["version"]))
        per_cluster[proposal["cluster"]] += 1
        added.append(proposal)
    if added:
        new_file = not proposals.is_file()
        with proposals.open("a", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerows(added)
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft proposals from triage group A and build a review round")
    parser.add_argument("round", type=int, help="new round number (5 or later)")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()
    if args.round < 5:
        parser.error("rounds 1-4 are the fixed week 2 rounds")
    sheet = ROUNDS_DIR / f"round-{args.round}.csv"
    if sheet.exists():
        parser.error(f"{sheet} exists; a sheet is never overwritten")
    added = propose(TRIAGE, LABELS, PROPOSALS, args.limit)
    if not added:
        raise SystemExit("no new group A candidate to propose")
    count = build_sheet(PROPOSALS, args.round, sheet, [row["id"] for row in added])
    print(json.dumps({"proposed": len(added), "sheet": str(sheet), "rows": count,
                      "next": f"py -3.14 -m data.scripts.review_evidence {args.round} --labels {PROPOSALS}"}))


if __name__ == "__main__":
    main()
