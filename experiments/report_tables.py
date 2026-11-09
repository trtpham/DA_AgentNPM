"""Chapter 4 tables from finished runs (Gate B0 2026-11-09). Reads reports/ only.

Accuracy uses experiments.metrics.score unchanged, plus the two numbers the report needs that it does
not give: malicious packages approved (the worst mistake) and the median time per package. Peak
memory comes from run_meta.json -> resources (experiments.resources). Error cases list every false
positive, miss and approved malicious package with its rule and trace file, to open in the viewer.

    py -3.14 -m experiments.report_tables reports/test-v1-a-llm-x reports/test-v1-a-slm-x \
        --guarddog reports/test-v1-guarddog/guarddog --labels data/labels-v1.csv --split test --out reports/chapter4.md
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

from experiments.dataset import load_labels
from experiments.metrics import load_results, score


def _fmt(value, digits: int = 3) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}".replace(".", ",") if isinstance(value, float) else str(value)


def agent_row(run_dir: Path, labels: list[dict]) -> dict:
    results = load_results(run_dir, [])
    metrics = score(results, labels, "agent")
    truth = {f"{row['name']}@{row['version']}": row["label"] for row in labels}
    scored = [result for result in results if result.get("package") in truth]
    meta_path = run_dir / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    resources = meta.get("resources") or {}
    models = resources.get("ollama") or {}
    seconds = [result["elapsed_s"] for result in scored if result.get("elapsed_s") is not None]
    return {
        "name": (meta.get("config") or {}).get("name") or run_dir.name,
        "run_id": run_dir.name,
        "contexts": bool(meta.get("contexts")),
        "metrics": metrics,
        "malicious_approved": sum(truth[result["package"]] != "benign"
                                  and (result.get("decision") or {}).get("action") == "approve" for result in scored),
        "median_seconds": round(statistics.median(seconds), 1) if seconds else None,
        "container_peak_mb": resources.get("container_peak_mb"),
        "model_mb": max((values.get("size_mb", 0) for values in models.values()), default=None),
        "model_vram_mb": max((values.get("vram_mb", 0) for values in models.values()), default=None),
        "errors": error_cases(scored, truth, run_dir.name),
    }


def error_cases(results: list[dict], truth: dict[str, str], run_id: str) -> list[dict]:
    cases = []
    for result in results:
        decision = result.get("decision") or {}
        actual, action, label = truth[result["package"]], decision.get("action"), decision.get("label")
        flagged = label in ("suspicious", "malicious")
        kind = None
        if actual != "benign" and action == "approve":
            kind = "malicious approved"
        elif actual != "benign" and not flagged:
            kind = "miss"
        elif actual == "benign" and flagged:
            kind = "false positive"
        if kind:
            cases.append({"kind": kind, "package": result["package"], "expected": actual, "label": label,
                          "action": action, "rule": decision.get("rule"),
                          "reason": "; ".join(decision.get("reasons") or [])[:160],
                          "run_id": run_id, "trace": result.get("trace")})
    order = {"malicious approved": 0, "miss": 1, "false positive": 2}
    return sorted(cases, key=lambda case: (order[case["kind"]], case["package"]))


def guarddog_row(directory: Path, labels: list[dict]) -> dict:
    return {"name": "GuardDog", "metrics": score(load_results(directory, []), labels, "guarddog")}


def markdown(agents: list[dict], guarddog: dict | None) -> str:
    out = ["## Bảng: Độ chính xác", "",
           "| Cấu hình | OSV | Precision | Recall | F1 | FPR | Độc bị approve | Tỉ lệ review | JSON hợp lệ | Số gói |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    if guarddog:
        m = guarddog["metrics"]
        out.append(f"| GuardDog | — | {_fmt(m['precision'])} | {_fmt(m['recall'])} | {_fmt(m['f1'])} | "
                   f"{_fmt(m['fpr'])} | — | — | — | {m['scored']} |")
    for row in agents:
        m = row["metrics"]
        out.append(f"| {row['name']} | {'có' if row['contexts'] else 'không'} | {_fmt(m['precision'])} | "
                   f"{_fmt(m['recall'])} | {_fmt(m['f1'])} | {_fmt(m['fpr'])} | {row['malicious_approved']} | "
                   f"{_fmt(m['review_rate'])} | {_fmt(m['valid_json_rate'])} | {m['scored']} |")
    out += ["", "## Bảng: Hiệu năng", "",
            "| Cấu hình | Giây/gói (trung vị) | Giây/gói (TB) | Số bước TB | RAM container đỉnh (MB) | Bộ nhớ mô hình (MB) | Trên GPU (MB) |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    for row in agents:
        m = row["metrics"]
        out.append(f"| {row['name']} | {_fmt(row['median_seconds'], 1)} | {_fmt(m['mean_seconds'], 1)} | "
                   f"{_fmt(m['mean_steps'], 2)} | {_fmt(row['container_peak_mb'], 1)} | {_fmt(row['model_mb'], 1)} | "
                   f"{_fmt(row['model_vram_mb'], 1)} |")
    out += ["", "## Ca sai (mở trace trong viewer)", "",
            "| Loại | Cấu hình | Gói | Nhãn đúng | Quyết định | Luật | Lý do | Trace |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in agents:
        for case in row["errors"]:
            reason = case["reason"].replace("|", "/")
            out.append(f"| {case['kind']} | {row['name']} | `{case['package']}` | {case['expected']} | "
                       f"{case['label']}/{case['action']} | {case['rule']} | {reason} | "
                       f"`{case['run_id']}/{case['trace']}` |")
    return "\n".join(out) + "\n"


def main() -> None:
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Build the chapter 4 tables from finished runs")
    parser.add_argument("runs", nargs="+", type=Path, help="reports/<run_id> of agent runs")
    parser.add_argument("--guarddog", type=Path, help="reports/<run_id>/guarddog")
    parser.add_argument("--labels", type=Path, default=Path("data/labels-v1.csv"))
    parser.add_argument("--split", choices=("dev", "test"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    labels = [row for row in load_labels(args.labels) if not args.split or row["split"] == args.split]
    text = markdown([agent_row(run, labels) for run in args.runs],
                    guarddog_row(args.guarddog, labels) if args.guarddog else None)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
