"""Week 7: re-decide recorded verdicts under other thresholds (dev split only). No model is run.

    py -3.14 -m experiments.threshold_sweep reports/<dev_run_id> --labels data/labels-v1.csv

Each trace keeps the model's last valid verdict, the evidence checks and the other decide() inputs
(since 2026-11-08). For every threshold 0.50 .. 0.95 (same value for deny and approve) the sweep
calls agent.decide.decide exactly as the agent does and scores the result like experiments.metrics
(positive = malicious or suspicious). Traces without recorded inputs are counted as `skipped`.

Selection rule, fixed before looking at the test split (KE_HOACH giai đoạn 4):
  1. no malicious package approved;
  2. highest F1;
  3. tie -> the higher threshold (more conservative).
"""

import argparse
import json
import sys
from pathlib import Path

from agent.decide import decide
from agent.schema import Verdict
from experiments.dataset import load_labels

THRESHOLDS = [round(0.50 + 0.05 * step, 2) for step in range(10)]


def recorded(trace: Path) -> tuple[dict, list[dict], dict] | None:
    """(verdict, evidence checks, decide inputs) of one trace, or None if they were not all recorded."""
    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines() if line.strip()]
    verdicts = [event["verdict"] for event in events if event["type"] == "verdict" and event.get("valid")]
    decisions = [event for event in events if event["type"] == "decision"]
    if not verdicts or not decisions or not decisions[-1].get("inputs"):
        return None
    return verdicts[-1], decisions[-1]["evidence_checks"], decisions[-1]["inputs"]


def sweep(run_dir: Path, truth: dict[str, str], thresholds=THRESHOLDS) -> dict:
    cases, skipped = [], []
    for path in sorted(run_dir.glob("*.json")):
        if path.name == "run_meta.json":
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        package = result.get("package")
        if package not in truth:
            continue
        found = recorded(run_dir / str(result.get("trace") or "")) if result.get("trace") else None
        if found is None:
            # A failed run keeps its R2 fallback whatever the threshold; it still counts in the scores.
            fallback = (result.get("decision") or {}).get("label")
            if result.get("status") == "error" and fallback:
                cases.append((package, None, None, None, fallback))
            else:
                skipped.append(package)
            continue
        verdict, checks, inputs = found
        cases.append((package, Verdict.model_validate(verdict), checks, inputs, None))
    rows = []
    for threshold in thresholds:
        tp = fp = tn = fn = review = approved_malicious = 0
        for package, verdict, checks, inputs, fallback in cases:
            if verdict is None:
                label, action = fallback, "review"
            else:
                decision = decide(verdict, checks, deny_threshold=threshold, approve_threshold=threshold, **inputs)
                label, action = decision["label"], decision["action"]
            positive, flagged = truth[package] != "benign", label in ("malicious", "suspicious")
            tp += positive and flagged
            fn += positive and not flagged
            fp += not positive and flagged
            tn += not positive and not flagged
            review += action == "review"
            approved_malicious += truth[package] == "malicious" and action == "approve"
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
        rows.append({"threshold": threshold, "precision": precision, "recall": recall, "f1": f1,
                     "fpr": fp / (fp + tn) if fp + tn else None, "review_rate": review / len(cases) if cases else None,
                     "malicious_approved": approved_malicious})
    safe = [row for row in rows if row["malicious_approved"] == 0 and row["f1"] is not None]
    chosen = max(safe, key=lambda row: (row["f1"], row["threshold"]))["threshold"] if safe else None
    return {"cases": len(cases), "skipped": skipped, "rows": rows, "chosen": chosen}


def markdown(result: dict) -> str:
    def cell(value):
        return "-" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value)

    lines = ["| Ngưỡng | Precision | Recall | F1 | FPR | Tỷ lệ review | Gói độc được approve |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for row in result["rows"]:
        mark = " **(chọn)**" if row["threshold"] == result["chosen"] else ""
        lines.append(f"| {row['threshold']:.2f}{mark} | {cell(row['precision'])} | {cell(row['recall'])} | "
                     f"{cell(row['f1'])} | {cell(row['fpr'])} | {cell(row['review_rate'])} | {row['malicious_approved']} |")
    lines.append(f"\n{result['cases']} gói được tính; {len(result['skipped'])} trace thiếu dữ liệu quyết định (bỏ qua).")
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Re-decide recorded verdicts under thresholds 0.50-0.95 (dev only)")
    parser.add_argument("run", type=Path)
    parser.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    parser.add_argument("--split", default="dev", help="only rows of this split (never tune on test)")
    args = parser.parse_args()
    truth = {f"{row['name']}@{row['version']}": row["label"] for row in load_labels(args.labels)
             if row["split"] == args.split}
    print(markdown(sweep(args.run, truth)))


if __name__ == "__main__":
    main()
