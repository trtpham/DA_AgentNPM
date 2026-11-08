"""Score agent or GuardDog results against labels.csv (TV3-5).

Positive class = malicious or suspicious. Agent predictions use the final rule-based
decision, including the R2 fallback of a failed run; GuardDog predicts malicious when it
reports any issue. Failed runs count in error_rate and stay in the denominator.
"""

import argparse
import json
from pathlib import Path

from experiments.dataset import load_labels

CLASSES = ("benign", "suspicious", "malicious")


def _prediction(result: dict, source: str) -> str:
    if source == "guarddog":
        if not result.get("ok") or result.get("data") is None:
            return "error"
        return "malicious" if result["data"]["issues"] else "benign"
    decision = result.get("decision")
    return decision["label"] if decision else "error"


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def score(results: list[dict], labels: list[dict], source: str = "agent") -> dict:
    truth = {f"{row['name']}@{row['version']}": row["label"] for row in labels}
    confusion = {actual: {predicted: 0 for predicted in CLASSES + ("error",)} for actual in CLASSES}
    tp = fp = tn = fn = errors = review = valid = 0
    steps, seconds, unmatched = [], [], []
    for result in results:
        actual = truth.get(result.get("package"))
        if actual is None:
            unmatched.append(result.get("package"))
            continue
        predicted = _prediction(result, source)
        confusion[actual][predicted] += 1
        positive = actual != "benign"
        flagged = predicted in ("suspicious", "malicious")
        if predicted == "error":
            errors += 1
            # A failed run is not a detection; scoring it as negative keeps recall honest.
            fn += positive
            tn += not positive
        else:
            tp += positive and flagged
            fn += positive and not flagged
            fp += not positive and flagged
            tn += not positive and not flagged
        if source == "agent":
            # A failed run still has the R2 fallback decision, which is what gets scored above.
            errors += predicted != "error" and result.get("status") == "error"
            review += (result.get("decision") or {}).get("action") == "review"
            valid += result.get("status") == "ok"
            if result.get("steps") is not None:
                steps.append(result["steps"])
        if result.get("elapsed_s") is not None:
            seconds.append(result["elapsed_s"])
    total = tp + fp + tn + fn
    precision, recall = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    return {
        "source": source, "scored": total, "unmatched": unmatched,
        "per_class": {label: sum(confusion[label].values()) for label in CLASSES},
        "confusion": confusion,
        "binary": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "precision": precision, "recall": recall,
        "f1": round(2 * precision * recall / (precision + recall), 4) if precision and recall else None,
        "fpr": _ratio(fp, fp + tn), "error_rate": _ratio(errors, total),
        "review_rate": _ratio(review, total) if source == "agent" else None,
        "valid_json_rate": _ratio(valid, total) if source == "agent" else None,
        "mean_steps": round(sum(steps) / len(steps), 2) if steps else None,
        "mean_seconds": round(sum(seconds) / len(seconds), 1) if seconds else None,
    }


def load_results(directory: Path, unreadable: list[str] | None = None) -> list[dict]:
    """Result files of a run. A file the OS refuses to open (e.g. quarantined by antivirus) is listed
    in `unreadable` instead of stopping the whole scoring."""
    results = []
    for path in sorted(directory.glob("*.json")):
        if path.name in ("run_meta.json", "guarddog_meta.json"):
            continue
        try:
            results.append(json.loads(path.read_text(encoding="utf-8")))
        except OSError:
            if unreadable is None:
                raise
            unreadable.append(path.name)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute metrics for one run directory")
    parser.add_argument("results", type=Path, help="reports/<run_id> or reports/<run_id>/guarddog")
    parser.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    parser.add_argument("--source", choices=("agent", "guarddog"), default="agent")
    args = parser.parse_args()
    unreadable: list[str] = []
    result = score(load_results(args.results, unreadable), load_labels(args.labels), args.source)
    result["unreadable"] = unreadable
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
