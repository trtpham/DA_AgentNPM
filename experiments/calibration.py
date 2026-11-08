"""B6: how well does the model's own confidence match how often it is right? Measurement only.

For each run directory, the model's last valid verdict (from its trace, before any decision rule)
is compared with the expected label. Confidence is split into five bins; the script reports the
accuracy per bin, ECE (expected calibration error) and the Brier score. The 0.8 thresholds are not
changed here: changing them needs its own Gate, based on this table.

    py -3.14 -m experiments.calibration corpus-v2-a-llm corpus-v2-a-slm corpus-v2-a-tlm
    py -3.14 -m experiments.calibration <run_id> --labels data/labels.csv
"""

import argparse
import json
import sys
from pathlib import Path

from experiments.dataset import load_labels

CORPUS_EXPECTED = Path("tests/fixtures/corpus/EXPECTED.json")
BINS = 5


def expected_labels(labels: Path | None = None) -> dict[str, str]:
    if labels is None:
        return {package: entry["label"] for package, entry in
                json.loads(CORPUS_EXPECTED.read_text(encoding="utf-8")).items()}
    return {f"{row['name']}@{row['version']}": row["label"] for row in load_labels(labels)}


def model_verdict(run_dir: Path, result: dict) -> dict | None:
    """Last valid verdict the model produced (the trace keeps it before decide() changes the label)."""
    trace = run_dir / str(result.get("trace") or "")
    if result.get("trace") and trace.is_file():
        verdicts = [event["verdict"] for event in map(json.loads, trace.read_text(encoding="utf-8").splitlines())
                    if event.get("type") == "verdict" and event.get("valid") and event.get("verdict")]
        if verdicts:
            return verdicts[-1]
    return None


def samples(run_dir: Path, expected: dict[str, str]) -> list[tuple[float, bool]]:
    """(confidence, correct) for every package of the run that has an expected label and a verdict."""
    pairs = []
    for path in sorted(run_dir.glob("*.json")):
        if path.name == "run_meta.json":
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        verdict = model_verdict(run_dir, result)
        if verdict is None or result.get("package") not in expected:
            continue
        pairs.append((float(verdict["confidence"]), verdict["label"] == expected[result["package"]]))
    return pairs


def calibrate(pairs: list[tuple[float, bool]], bins: int = BINS) -> dict:
    """Per-bin accuracy, ECE = sum(n_b / N * |accuracy_b - confidence_b|) and Brier = mean((p - y)^2)."""
    rows = []
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [(p, y) for p, y in pairs if low <= p < high or (index == bins - 1 and p == 1.0)]
        rows.append({"bin": f"{low:.1f}-{high:.1f}", "n": len(members),
                     "confidence": round(sum(p for p, _ in members) / len(members), 3) if members else None,
                     "accuracy": round(sum(y for _, y in members) / len(members), 3) if members else None})
    total = len(pairs)
    ece = sum(row["n"] / total * abs(row["accuracy"] - row["confidence"]) for row in rows if row["n"]) if total else None
    brier = sum((p - y) ** 2 for p, y in pairs) / total if total else None
    return {"n": total, "bins": rows, "ece": round(ece, 4) if ece is not None else None,
            "brier": round(brier, 4) if brier is not None else None}


def markdown(results: dict[str, dict]) -> str:
    lines = ["| Run | N | ECE | Brier | " + " | ".join(f"acc {row['bin']}" for row in next(iter(results.values()))["bins"])
             + " |", "| --- | --- | --- | --- |" + " --- |" * BINS]
    for run_id, result in results.items():
        cells = [f"{row['accuracy']} (n={row['n']}, p={row['confidence']})" if row["n"] else "-" for row in result["bins"]]
        lines.append(f"| {run_id} | {result['n']} | {result['ece']} | {result['brier']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    # Model text and reasons are not limited to the console code page (cp1252 on Windows); a
    # character it cannot show must not stop a batch (2026-11-08: '→' did).
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Confidence calibration of finished runs (measurement only)")
    parser.add_argument("run_ids", nargs="+")
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    parser.add_argument("--labels", type=Path, help="labels.csv; default is the simulated corpus EXPECTED.json")
    args = parser.parse_args()
    expected = expected_labels(args.labels)
    results = {run_id: calibrate(samples(args.reports / run_id, expected)) for run_id in args.run_ids}
    print(markdown(results))


if __name__ == "__main__":
    main()
