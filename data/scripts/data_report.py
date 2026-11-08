"""D-4: how far is the label set from the v1 targets? Read only.

    py -3.14 -m data.scripts.data_report

Takes the deduplicated, capped rows (D-3) of data/labels.csv and data/proposals.csv, joins the
cross-review decisions from every data/review_rounds/round-*.csv, and prints the targets of
plan KE_HOACH_DU_LIEU_400 (section 2) next to the measured values. Only rows marked `verified`
by a person count toward the targets; drafts and pending rows are shown separately.
"""

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

from data.scripts.dedupe_labels import CAP, DEFAULT_HASHES, DEFAULT_TABLES, dedupe, load_hashes
from experiments.dataset import load_labels

ROUNDS_DIR = Path("data/review_rounds")
TARGETS = {"total": 400, "benign": 180, "malicious": 180, "clusters": 40}


def decisions(rounds_dir: Path = ROUNDS_DIR) -> dict[str, str]:
    """Latest decision per id across all round sheets ('' when still pending)."""
    found = {}
    for path in sorted(rounds_dir.glob("round-*.csv"), key=lambda item: int(item.stem.split("-")[1])):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                found[row["id"]] = row.get("decision", "").strip()
    return found


def report(rows: list[dict], decided: dict[str, str], cap: int = CAP) -> dict:
    verified = [row for row in rows if decided.get(row["id"]) == "verified"]
    status = Counter(decided.get(row["id"]) or ("pending" if row["id"] in decided else "no sheet") for row in rows)
    clusters = Counter(row["cluster"] for row in verified)
    largest = max(clusters.values(), default=0)
    labels = Counter(row["label"] for row in verified)
    splits = Counter(row["split"] for row in verified)
    measured = {"total": len(verified), "benign": labels["benign"], "malicious": labels["malicious"],
                "clusters": len(clusters)}
    checks = {name: measured[name] >= target for name, target in TARGETS.items()}
    checks["cluster cap"] = largest <= cap
    return {"rows": len(rows), "review_status": dict(status), "verified": measured,
            "suspicious": labels["suspicious"], "splits": dict(splits), "largest_cluster": largest,
            "checks": checks, "ready": all(checks.values())}


def markdown(result: dict) -> str:
    lines = ["| Chỉ tiêu | Mục tiêu | Đã kiểm tra (verified) | Đạt |", "| --- | --- | --- | --- |"]
    for name, target in TARGETS.items():
        lines.append(f"| {name} | >= {target} | {result['verified'][name]} | {'có' if result['checks'][name] else 'chưa'} |")
    lines.append(f"| cụm lớn nhất | <= {CAP} | {result['largest_cluster']} | {'có' if result['checks']['cluster cap'] else 'chưa'} |")
    status = ", ".join(f"{key} {value}" for key, value in sorted(result["review_status"].items()))
    lines += ["", f"Sau lọc trùng: {result['rows']} dòng ({status}); suspicious đã kiểm tra: {result['suspicious']}; "
              f"split đã kiểm tra: {result['splits'] or '-'}. Sẵn sàng đóng băng v1: **{'có' if result['ready'] else 'chưa'}**."]
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Vietnamese table
    parser = argparse.ArgumentParser(description="Compare the label set with the v1 targets")
    parser.add_argument("--cap", type=int, default=CAP)
    args = parser.parse_args()
    tables = [load_labels(path) for path in DEFAULT_TABLES if path.is_file()]
    rows = dedupe(tables, load_hashes(list(DEFAULT_HASHES)), args.cap)["rows"]
    print(markdown(report(rows, decisions(), args.cap)))


if __name__ == "__main__":
    main()
