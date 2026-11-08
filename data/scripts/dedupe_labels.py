"""D-3: remove duplicates, merge look-alike clusters and cap clusters before freezing labels v1.

    py -3.14 -m data.scripts.dedupe_labels                         # report only
    py -3.14 -m data.scripts.dedupe_labels --output data/dataset-v1-draft.csv

Inputs are label tables in the 11-column contract (data/labels.csv first, then data/proposals.csv)
and hash tables with `package, version, tarball_sha256, install_hash` (D-1 triage; later the
Datadog filter run in the VM). Rules, in order (plan KE_HOACH_DU_LIEU_400, 3.3):
  1. same name@version            -> keep the first row (labels.csv wins over proposals)
  2. same tarball sha256          -> keep the first row (one archive published under two names)
  3. same install_hash            -> rows stay, their clusters are merged (look-alike code)
  4. more than CAP rows in a cluster -> keep the first CAP (labels.csv rows first, then by id)
  5. a cluster in both dev and test -> reported as leakage (prepare_labels splits by cluster)
Nothing is labelled here and data/labels.csv is never written.
"""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from experiments.dataset import FIELDS, load_labels

CAP = 12
DEFAULT_TABLES = (Path("data/labels.csv"), Path("data/proposals.csv"))
DEFAULT_HASHES = (Path("data/review_450/triage_450.csv"),)


def load_hashes(paths: list[Path]) -> dict[tuple[str, str], dict]:
    hashes = {}
    for path in paths:
        if not path.is_file():
            continue
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                hashes[(row["package"], row["version"])] = {"tarball_sha256": row.get("tarball_sha256", ""),
                                                            "install_hash": row.get("install_hash", "")}
    return hashes


def dedupe(tables: list[list[dict]], hashes: dict[tuple[str, str], dict], cap: int = CAP) -> dict:
    rows, dropped = [], []
    seen_version, seen_tarball = {}, {}
    for priority, table in enumerate(tables):
        for row in table:
            key = (row["name"], row["version"])
            known = hashes.get(key, {})
            if key in seen_version:
                dropped.append({"id": row["id"], "rule": "same name@version", "kept": seen_version[key]})
                continue
            tarball = known.get("tarball_sha256")
            if tarball and tarball in seen_tarball:
                dropped.append({"id": row["id"], "rule": "same tarball sha256", "kept": seen_tarball[tarball]})
                continue
            seen_version[key] = row["id"]
            if tarball:
                seen_tarball[tarball] = row["id"]
            rows.append({**row, "_priority": priority, "_install": known.get("install_hash", "")})
    # Rule 3: union-find over clusters that share install code.
    parent: dict[str, str] = {}

    def find(cluster: str) -> str:
        parent.setdefault(cluster, cluster)
        while parent[cluster] != cluster:
            parent[cluster] = parent[parent[cluster]]
            cluster = parent[cluster]
        return cluster

    first_cluster: dict[str, str] = {}
    for row in rows:
        find(row["cluster"])
        if row["_install"]:
            other = first_cluster.setdefault(row["_install"], row["cluster"])
            left, right = find(other), find(row["cluster"])
            if left != right:
                parent[right] = left
    merged = []
    for row in rows:
        root = find(row["cluster"])
        if root != row["cluster"]:
            merged.append({"id": row["id"], "from": row["cluster"], "to": root})
            row["cluster"] = root
    # Rule 4: cap each cluster, keeping reviewed labels first.
    by_cluster = defaultdict(list)
    for row in rows:
        by_cluster[row["cluster"]].append(row)
    kept = []
    for cluster, members in by_cluster.items():
        members.sort(key=lambda row: (row["_priority"], row["id"]))
        kept += members[:cap]
        dropped += [{"id": row["id"], "rule": f"cluster cap {cap}", "kept": cluster} for row in members[cap:]]
    kept.sort(key=lambda row: (row["_priority"], row["id"]))
    splits = defaultdict(set)
    for row in kept:
        if row["split"] in ("dev", "test"):
            splits[row["cluster"]].add(row["split"])
    leakage = sorted(cluster for cluster, values in splits.items() if len(values) > 1)
    clean = [{field: row[field] for field in FIELDS} for row in kept]
    return {"rows": clean, "dropped": dropped, "merged": merged, "leakage": leakage,
            "summary": {"kept": len(clean), "dropped": len(dropped), "merged_rows": len(merged),
                        "clusters": len({row["cluster"] for row in clean}),
                        "labels": dict(sorted(Counter(row["label"] for row in clean).items())),
                        "largest_clusters": Counter(row["cluster"] for row in clean).most_common(5),
                        "leaking_clusters": len(leakage)}}


def main() -> None:
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Deduplicate and cap label tables (never writes labels.csv)")
    parser.add_argument("--table", type=Path, action="append", help="label table, in priority order")
    parser.add_argument("--hashes", type=Path, action="append", help="table with package, version, hashes")
    parser.add_argument("--cap", type=int, default=CAP)
    parser.add_argument("--output", type=Path, help="write the kept rows here (not data/labels.csv)")
    parser.add_argument("--report", type=Path, help="write dropped/merged/leakage details as JSON")
    args = parser.parse_args()
    tables = [load_labels(path) for path in (args.table or DEFAULT_TABLES) if path.is_file()]
    result = dedupe(tables, load_hashes(args.hashes or list(DEFAULT_HASHES)), args.cap)
    if args.output:
        if args.output.resolve() == Path("data/labels.csv").resolve():
            raise SystemExit("refusing to overwrite data/labels.csv")
        with args.output.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, FIELDS)
            writer.writeheader()
            writer.writerows(result["rows"])
    if args.report:
        args.report.write_text(json.dumps({key: result[key] for key in ("summary", "dropped", "merged", "leakage")},
                                          ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
