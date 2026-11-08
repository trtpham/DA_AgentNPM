"""D-2: turn triage group A candidates into draft proposals and a cross-review round.

    py -3.14 -m data.scripts.propose_labels 5 --limit 40
    py -3.14 -m data.scripts.review_evidence 5 --labels data/proposals.csv   (container)

A proposal is a draft written by Claude from static triage only: label `benign`, the file a hook
runs and its first lines. It is never used for measurement until a person other than the drafter
marks it `verified` in the round sheet. Group A is proposed by default; `--group B` proposes only
"light" group B rows (child_process / network calls, nothing heavier) and says what to read. Clusters are capped so no family dominates (plan, section 2).
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


# Group B rows a reviewer can still judge quickly: only child_process and/or network calls on the
# install path, no secret/env flow, no shell script or inline code, no obfuscation, no code fetched
# from outside, complete scan. The draft tells the reviewer exactly what to look at.
B_LIGHT_RISKY = {"child_process", "network_api"}
B_HEAVY_REASONS = ("shell script", "inline code", "pipes output", "obfuscated", "outside the package",
                   "require depth", "file limit", "indicator limit", "native binaries", "install source not readable")


def b_light(row: dict) -> bool:
    risky = json.loads(row.get("risky") or "{}")
    reasons = [reason for reason in row.get("reasons", "").split(" | ") if reason]
    return (row["group"] == "B" and not row.get("flows") and set(risky) <= B_LIGHT_RISKY
            and not any(word in reason for reason in reasons for word in B_HEAVY_REASONS))


def draft(row: dict) -> dict | None:
    """Draft proposal for one group A (or light group B) triage row, or None when there is nothing to cite."""
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
    if row["group"] == "B":
        seen = ", ".join(sorted(json.loads(row.get("risky") or "{}"))) or "endpoints"
        finding, technique = f"static triage saw {seen} on the install path: read them and judge", "draft-b-light"
    else:
        finding, technique = "static triage found no risky sign", "draft-no-risky-sign"
    return {"id": f"cand-{slug}-{row['version']}", "name": row["package"], "version": row["version"],
            "label": "benign",
            "behavior_main": f"{action}; {finding} (draft, read before verifying)",
            "technique": technique, "file": file, "lines": lines, "source": row["tarball"],
            "split": "pending", "cluster": cluster_of(row["package"])}


def propose(triage: Path, labels: Path, proposals: Path, limit: int, cap: int = CLUSTER_CAP,
            group: str = "A") -> list[dict]:
    """Append up to `limit` new drafts (group A, or light group B) to `proposals`; returns the rows added."""
    existing = load_labels(labels) + (load_labels(proposals) if proposals.is_file() else [])
    taken = {(row["name"], row["version"]) for row in existing}
    per_cluster = Counter(row["cluster"] for row in existing)
    with triage.open(encoding="utf-8", newline="") as stream:
        rows = [row for row in csv.DictReader(stream)
                if (row["group"] == "A" if group == "A" else b_light(row))]
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


DATADOG_DIR = Path("data/datadog")


def datadog_draft(item: dict) -> dict | None:
    """Draft for one Datadog sample: the label is Datadog's (independent expert source); the
    reviewer confirms the behavior on the cited install path."""
    entries = item.get("entries") or []
    if item.get("error") or not item.get("has_hook") or not entries or not item.get("install_hash"):
        return None
    entry = entries[0]
    if entry["file"] == "package.json" and entry.get("line"):
        file, lines, action = "package.json", str(entry["line"]), f"{entry['hook']} runs an inline command"
    elif entry.get("lines"):
        file, lines = entry["file"], f"1-{min(entry['lines'], MAX_CITED_LINES)}"
        action = f"{entry['hook']} runs {file}"
    else:
        return None
    # The package's own manifest names it; dataset folders encode `@scope/name` as `@scope@name`.
    from data.scripts.datadog_container import dataset_name
    name, _, version = (item.get("manifest") or "").rpartition("@")
    if not name or version != item["version"]:
        name, version = dataset_name(item["name"]), item["version"]
    slug = re.sub(r"[^a-z0-9.]+", "-", name.lower()).strip("-")
    return {"id": f"dd-{slug}-{version}", "name": name, "version": version,
            "label": "malicious",
            "behavior_main": f"Datadog malicious_intent sample; {action} (draft: read the install path and name the behavior)",
            "technique": "draft-datadog", "file": file, "lines": lines, "source": item["archive"],
            "split": "pending", "cluster": "dd-" + item["install_hash"][:12]}


def propose_datadog(source_dir: Path, labels: Path, proposals: Path, limit: int, cap: int = CLUSTER_CAP) -> list[dict]:
    """Append up to `limit` Datadog drafts, one cluster at a time (round robin) for diversity."""
    existing = load_labels(labels) + (load_labels(proposals) if proposals.is_file() else [])
    taken = {(row["name"], row["version"]) for row in existing}
    per_cluster = Counter(row["cluster"] for row in existing)
    queues: dict[str, list[dict]] = {}
    for path in sorted(source_dir.glob("candidates-batch-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            proposal = datadog_draft(json.loads(line)) if line.strip() else None
            if proposal and (proposal["name"], proposal["version"]) not in taken:
                taken.add((proposal["name"], proposal["version"]))
                queues.setdefault(proposal["cluster"], []).append(proposal)
    added = []
    while len(added) < limit and any(queues.values()):
        for cluster in sorted(queues, key=lambda name: (per_cluster[name], name)):
            if len(added) == limit:
                break
            if queues[cluster] and per_cluster[cluster] < cap:
                added.append(queues[cluster].pop(0))
                per_cluster[cluster] += 1
            elif per_cluster[cluster] >= cap:
                queues[cluster] = []
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
    parser.add_argument("--group", choices=("A", "B"), default="A", help="B = light group B only")
    parser.add_argument("--datadog", action="store_true", help="propose Datadog samples (data/datadog) instead")
    args = parser.parse_args()
    if args.round < 5:
        parser.error("rounds 1-4 are the fixed week 2 rounds")
    sheet = ROUNDS_DIR / f"round-{args.round}.csv"
    if sheet.exists():
        parser.error(f"{sheet} exists; a sheet is never overwritten")
    added = (propose_datadog(DATADOG_DIR, LABELS, PROPOSALS, args.limit) if args.datadog
             else propose(TRIAGE, LABELS, PROPOSALS, args.limit, group=args.group))
    if not added:
        raise SystemExit("no new candidate to propose")
    count = build_sheet(PROPOSALS, args.round, sheet, [row["id"] for row in added])
    print(json.dumps({"proposed": len(added), "sheet": str(sheet), "rows": count,
                      "next": f"py -3.14 -m data.scripts.review_evidence {args.round} --labels {PROPOSALS}"}))


if __name__ == "__main__":
    main()
