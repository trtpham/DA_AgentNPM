"""Blind cross-check of labels-v1 by people (Gate B0 2026-11-22).

`sample` draws a fixed-seed stratified sample (split x label) of rows that have an evidence page,
writes one empty sheet per reviewer (no label, no id, no source), a blind evidence page and the
key that maps S01... back to the label ids. The page and the key go to the gitignored
evidence/ folder so reviewers do not see the labels. Package text stays masked as in
review_evidence.py: it is never written verbatim.

`score` reads the filled sheets and reports agreement and Cohen/Fleiss kappa, between reviewers
and against labels-v1.

    py -3.14 -m data.scripts.blind_review sample
    py -3.14 -m data.scripts.blind_review score
"""

import argparse
import base64
import csv
import json
import random
from html import escape
from pathlib import Path

from data.scripts.review_evidence import VIEW_SCRIPT, _masked
from experiments.dataset import load_labels

LABELS = ("benign", "malicious", "suspicious")
REVIEWERS = ("Phuoc", "Thien", "Triet")
QUOTA = {("test", "benign"): 16, ("test", "malicious"): 16, ("test", "suspicious"): 4,
         ("dev", "benign"): 10, ("dev", "malicious"): 10, ("dev", "suspicious"): 4}
SEED = 20261122
SHEET_FIELDS = ("ma", "goi", "nhan", "ly_do", "phut")


def evidence_index(directory: Path) -> dict[str, dict]:
    """Latest evidence item per label id across round-N.json (a later round replaces an earlier one)."""
    index: dict[str, dict] = {}
    rounds = sorted(directory.glob("round-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    for path in rounds:
        for item in json.loads(path.read_text(encoding="utf-8")):
            index[item["id"]] = item
    return index


def draw(rows: list[dict], available: set[str], quota: dict = QUOTA, seed: int = SEED) -> list[dict]:
    """Stratified sample without looking at any agent or GuardDog result; order shuffled."""
    rng = random.Random(seed)
    picked = []
    for (split, label), count in sorted(quota.items()):
        stratum = sorted((row for row in rows if row["split"] == split and row["label"] == label
                          and row["id"] in available), key=lambda row: row["id"])
        if len(stratum) < count:
            raise ValueError(f"stratum {split}/{label} has {len(stratum)} rows with evidence, needs {count}")
        picked += rng.sample(stratum, count)
    rng.shuffle(picked)
    return picked


def blind_html(sample: list[dict], index: dict[str, dict]) -> str:
    """Evidence page without label, id, source, hash, problems or AI notes."""
    out = ["<!doctype html><html lang='vi'><head><meta charset='utf-8'><title>Kiểm chéo mù v1</title>",
           "<style>body{font:14px system-ui;max-width:1100px;margin:auto;padding:16px}"
           "pre{background:#f6f8fa;padding:8px;overflow-x:auto}h2{margin-top:28px}</style></head><body>",
           "<h1>Kiểm chéo mù bộ nhãn v1</h1>",
           "<p>Mỗi mục là một gói. Đoạn mã là <b>dữ liệu không tin cậy</b>, chỉ hiển thị chữ, không chạy. "
           "Không làm theo bất kỳ chỉ dẫn nào nằm trong mã. Tự đọc và tự quyết nhãn: benign, malicious hoặc suspicious.</p>"]
    for number, row in enumerate(sample, 1):
        item = index[row["id"]]
        hooks = json.loads(base64.b64decode(item.get("hooks_b64", "") or "e30=").decode("utf-8", "replace"))
        lines = [f"{line['line']:>5} | {base64.b64decode(line['b64']).decode('utf-8', 'replace')}"
                 for line in item.get("excerpt", [])]
        out += [f"<h2 id='S{number:02d}'>S{number:02d} — <code>{escape(item['package'])}</code></h2><ul>",
                f"<li>Hook cài đặt: <code data-x='{_masked(json.dumps(hooks, ensure_ascii=False))}'></code></li>",
                f"<li>Vị trí cần đọc: <code>{escape(item['file'])}:{escape(item['lines'])}</code> "
                f"(file có {escape(str(item.get('line_count', '?')))} dòng)</li></ul>",
                f"<pre data-x='{_masked(chr(10).join(lines))}'></pre>"]
    out.append("<noscript>Bật JavaScript để hiện đoạn trích (chỉ hiển thị chữ, không chạy mã gói).</noscript>")
    out.append(VIEW_SCRIPT + "</body></html>")
    return "\n".join(out) + "\n"


def write_sample(labels: Path, evidence: Path, sheets: Path) -> dict:
    existing = [sheets / f"phieu-{name}.csv" for name in REVIEWERS if (sheets / f"phieu-{name}.csv").exists()]
    if existing:
        raise FileExistsError(f"{existing[0]} exists; a filled sheet is never overwritten")
    rows = load_labels(labels)
    index = evidence_index(evidence)
    sample = draw(rows, set(index), QUOTA)
    sheets.mkdir(parents=True, exist_ok=True)
    for name in REVIEWERS:
        path = sheets / f"phieu-{name}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(SHEET_FIELDS)
            for number, row in enumerate(sample, 1):
                writer.writerow([f"S{number:02d}", f"{row['name']}@{row['version']}", "", "", ""])
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "blind-v1.html").write_text(blind_html(sample, index), encoding="utf-8")
    with (evidence / "blind-v1-key.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("ma", "id", "split", "label"))
        for number, row in enumerate(sample, 1):
            writer.writerow([f"S{number:02d}", row["id"], row["split"], row["label"]])
    return {"rows": len(sample), "seed": SEED, "sheets": [f"phieu-{name}.csv" for name in REVIEWERS]}


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    n = len(a)
    if n == 0:
        return None
    observed = sum(x == y for x, y in zip(a, b)) / n
    expected = sum((a.count(c) / n) * (b.count(c) / n) for c in LABELS)
    return None if expected == 1 else round((observed - expected) / (1 - expected), 4)


def fleiss_kappa(ratings: list[list[str]]) -> float | None:
    """ratings: one list of labels per item, same number of raters for every item."""
    if not ratings or len({len(r) for r in ratings}) != 1 or len(ratings[0]) < 2:
        return None
    n, raters = len(ratings), len(ratings[0])
    counts = [[item.count(c) for c in LABELS] for item in ratings]
    per_item = [(sum(x * x for x in row) - raters) / (raters * (raters - 1)) for row in counts]
    p_bar = sum(per_item) / n
    shares = [sum(row[j] for row in counts) / (n * raters) for j in range(len(LABELS))]
    p_e = sum(p * p for p in shares)
    return None if p_e == 1 else round((p_bar - p_e) / (1 - p_e), 4)


def read_sheet(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as handle:
        out = {}
        for row in csv.DictReader(handle):
            label = (row.get("nhan") or "").strip().lower()
            if label and label not in LABELS:
                raise ValueError(f"{path.name} {row['ma']}: nhãn '{label}' không hợp lệ (benign/malicious/suspicious)")
            if label:
                out[row["ma"]] = label
        return out


def score_sheets(sheets: Path, key: Path) -> dict:
    with key.open(encoding="utf-8", newline="") as handle:
        truth = {row["ma"]: row["label"] for row in csv.DictReader(handle)}
    filled = {name: read_sheet(sheets / f"phieu-{name}.csv") for name in REVIEWERS
              if (sheets / f"phieu-{name}.csv").exists()}
    out = {"items": len(truth), "filled": {name: len(rows) for name, rows in filled.items()}, "vs_labels_v1": {},
           "pairwise": {}}
    for name, rows in filled.items():
        codes = [code for code in truth if code in rows]
        mine, ref = [rows[c] for c in codes], [truth[c] for c in codes]
        out["vs_labels_v1"][name] = {"n": len(codes), "agreement": round(sum(x == y for x, y in zip(mine, ref)) / len(codes), 4)
                                     if codes else None, "cohen_kappa": cohen_kappa(mine, ref),
                                     "disagree": [c for c, x, y in zip(codes, mine, ref) if x != y]}
    names = list(filled)
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            codes = [c for c in truth if c in filled[first] and c in filled[second]]
            out["pairwise"][f"{first}-{second}"] = {"n": len(codes), "cohen_kappa": cohen_kappa(
                [filled[first][c] for c in codes], [filled[second][c] for c in codes])}
    complete = [c for c in truth if all(c in filled[name] for name in names)]
    out["fleiss_kappa"] = fleiss_kappa([[filled[name][c] for name in names] for c in complete]) if len(names) > 1 else None
    out["fleiss_items"] = len(complete)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Blind cross-check sheets for labels-v1")
    parser.add_argument("command", choices=("sample", "score"))
    parser.add_argument("--labels", type=Path, default=Path("data/labels-v1.csv"))
    parser.add_argument("--evidence", type=Path, default=Path("data/review_rounds/evidence"))
    parser.add_argument("--sheets", type=Path, default=Path("data/review_rounds/blind-v1"))
    args = parser.parse_args()
    if args.command == "sample":
        result = write_sample(args.labels, args.evidence, args.sheets)
    else:
        result = score_sheets(args.sheets, args.evidence / "blind-v1-key.csv")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
