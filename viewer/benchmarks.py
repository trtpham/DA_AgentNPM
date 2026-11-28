"""Read-only aggregator of benchmark comparisons, OSV ablation, sandbox coverage, sweeps, and datasets."""

import csv
import json
import re
from collections import Counter
from pathlib import Path

CONFIG_SLUGS = ("a-llm", "a-llm-x", "a-slm", "a-slm-x", "a-tlm", "a-tlm-x")
STOP_BEHAVIOR_REASONS = ("network", "missing_tool", "script", "resource")
NO_RESULT_REASONS = ("infra", "prepare", "not_started")
SANDBOX_GROUP_INFO = (
    ("A", "Hết chỗ /tmp (64 MB) khi chép npm-cache (infra)", "Có thể sửa (tách tmpfs)"),
    ("B", "Vượt giới hạn giải nén an toàn (prepare)", "Không nên sửa (chốt an toàn)"),
    ("C", "Dependency đã bị gỡ khỏi npm (ETARGET)", "Không (giới hạn dữ liệu)"),
    ("D", "Gói chỉ hỗ trợ macOS/arm64 (EBADPLATFORM)", "Không khuyến nghị"),
    ("E", "Tên phiên bản dependency không hợp lệ (EINVALIDTAGNAME)", "Không"),
    ("F", "npm install --offline thoát lỗi chưa rõ nguyên nhân", "Cần lưu thêm stderr"),
)


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None


def _pick_metrics(m: dict | None) -> dict:
    if not isinstance(m, dict):
        return {}
    return {
        "scored": m.get("scored"),
        "precision": m.get("precision"),
        "recall": m.get("recall"),
        "f1": m.get("f1"),
        "fpr": m.get("fpr"),
        "error_rate": m.get("error_rate"),
        "review_rate": m.get("review_rate"),
        "valid_json_rate": m.get("valid_json_rate"),
        "mean_steps": m.get("mean_steps"),
        "mean_seconds": m.get("mean_seconds"),
    }


def _load_comparisons(reports_root: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {"test": [], "dev": []}
    for split in ("test", "dev"):
        summary_dir = reports_root / f"{split}-v1-summary"
        rows: list[dict] = []
        for slug in CONFIG_SLUGS:
            data = _read_json(summary_dir / f"metrics-{slug}.json")
            if not isinstance(data, dict):
                continue
            meta = _read_json(reports_root / f"{split}-v1-{slug}" / "run_meta.json") or {}
            confusion = data.get("confusion") or {}
            rows.append({
                "config": slug.upper(),
                "run_id": f"{split}-v1-{slug}",
                "model": meta.get("model") or "—",
                "malicious_approved": (confusion.get("malicious") or {}).get("benign", 0),
                "suspicious_approved": (confusion.get("suspicious") or {}).get("benign", 0),
                "confusion": confusion,
                "binary": data.get("binary"),
                **_pick_metrics(data),
            })
        gd = _read_json(reports_root / f"guarddog-{split}-v1" / "metrics.json")
        if isinstance(gd, dict):
            rows.append({
                "config": "GuardDog 2.6.0",
                "run_id": f"guarddog-{split}-v1",
                "model": "—",
                "malicious_approved": None,
                "suspicious_approved": None,
                "confusion": gd.get("confusion"),
                "binary": gd.get("binary"),
                **_pick_metrics(gd),
            })
        out[split] = rows
    return out


def _load_osv_ablation(reports_root: Path) -> dict[str, list[dict]]:
    osv_dir = reports_root / "osv-ablation-v1"
    out: dict[str, list[dict]] = {"test": [], "dev": []}
    if not osv_dir.is_dir():
        return out
    for split in ("test", "dev"):
        rows: list[dict] = []
        for slug in CONFIG_SLUGS:
            data = _read_json(osv_dir / f"{split}-{slug}.json")
            if not isinstance(data, dict):
                continue
            approved = data.get("approved_not_benign") or {}
            rows.append({
                "config": slug.upper(),
                "without_osv": _pick_metrics(data.get("without_osv")),
                "with_osv": _pick_metrics(data.get("with_osv")),
                "changed_count": len(data.get("changed") or []),
                "approved_not_benign_without": approved.get("without_osv"),
                "approved_not_benign_with": approved.get("with_osv"),
            })
        only = _read_json(osv_dir / f"{split}-osv-only.json")
        if isinstance(only, dict) and isinstance(only.get("osv_only"), dict):
            rows.append({
                "config": "Chỉ OSV (mốc)",
                "without_osv": None,
                "with_osv": _pick_metrics(only.get("osv_only")),
                "changed_count": None,
                "approved_not_benign_without": None,
                "approved_not_benign_with": None,
            })
        out[split] = rows
    return out


def _classify_missing_group(item: dict, fail_reason: str) -> str:
    if fail_reason == "infra":
        return "A"
    if fail_reason == "prepare":
        return "B"
    deps = item.get("dependencies") if isinstance(item.get("dependencies"), dict) else {}
    if deps.get("ok") is True:
        return "F"
    err_text = f"{item.get('error') or ''}\n{deps.get('error') or ''}"
    if "EBADPLATFORM" in err_text or "notsup Valid os:" in err_text or "notsup Valid cpu:" in err_text:
        return "D"
    if "EINVALIDTAGNAME" in err_text:
        return "E"
    return "C"


def _load_sandbox_summary(reports_root: Path) -> dict | None:
    splits: dict[str, dict] = {}
    all_groups: dict[str, Counter[str]] = {"dev": Counter(), "test": Counter()}
    for split in ("dev", "test"):
        sbx_dir = reports_root / f"sbx-{split}-v1b" / "sandbox"
        if not sbx_dir.is_dir():
            continue
        files = sorted(p for p in sbx_dir.glob("*.json") if p.name != "sandbox_meta.json")
        ok_full = 0
        stopped = 0
        no_result = 0
        script_ran = 0
        canary = 0
        stop_reasons: Counter[str] = Counter()
        for path in files:
            raw = _read_json(path)
            if not isinstance(raw, dict):
                continue
            data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
            fail_reason = raw.get("fail_reason") or data.get("fail_reason")
            if data.get("outcome") == "ok":
                ok_full += 1
            elif fail_reason in STOP_BEHAVIOR_REASONS:
                stopped += 1
                stop_reasons[fail_reason] += 1
            elif fail_reason in NO_RESULT_REASONS:
                no_result += 1
                all_groups[split][_classify_missing_group(raw, fail_reason)] += 1
            if data.get("script_ran"):
                script_ran += 1
            if data.get("canary_touched"):
                canary += 1
        total = ok_full + stopped + no_result
        if total:
            splits[split] = {
                "total": total,
                "outcome_ok": ok_full,
                "stopped_with_behavior": stopped,
                "with_result": ok_full + stopped,
                "no_result": no_result,
                "script_ran": script_ran,
                "canary_touched": canary,
                "coverage_pct": round((ok_full + stopped) / total * 100, 1),
                "stop_reasons": {k: stop_reasons[k] for k in STOP_BEHAVIOR_REASONS},
            }
    if not splits:
        return None
    total_all = sum(s["total"] for s in splits.values())
    with_res_all = sum(s["with_result"] for s in splits.values())
    splits["total"] = {
        "total": total_all,
        "outcome_ok": sum(s["outcome_ok"] for s in splits.values()),
        "stopped_with_behavior": sum(s["stopped_with_behavior"] for s in splits.values()),
        "with_result": with_res_all,
        "no_result": sum(s["no_result"] for s in splits.values()),
        "script_ran": sum(s["script_ran"] for s in splits.values()),
        "canary_touched": sum(s["canary_touched"] for s in splits.values()),
        "coverage_pct": round(with_res_all / total_all * 100, 1) if total_all else 0.0,
        "stop_reasons": {
            k: sum(s["stop_reasons"][k] for s in splits.values() if s is not None)
            for k in STOP_BEHAVIOR_REASONS
        },
    }
    missing_groups = []
    for code, desc, fixable in SANDBOX_GROUP_INFO:
        dev_c = all_groups["dev"][code]
        test_c = all_groups["test"][code]
        missing_groups.append({
            "group": code,
            "reason": desc,
            "dev": dev_c,
            "test": test_c,
            "total": dev_c + test_c,
            "fixable": fixable,
        })
    return {"splits": splits, "missing_groups": missing_groups}


def _load_sweeps(reports_root: Path) -> list[dict]:
    dev_dir = reports_root / "dev-v1-summary"
    if not dev_dir.is_dir():
        return []
    sweeps = []
    for slug in CONFIG_SLUGS:
        path = dev_dir / f"sweep-{slug}.md"
        if not path.is_file():
            continue
        rows = []
        note = ""
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped.startswith("|") and not stripped.startswith("| Ngưỡng") and not stripped.startswith("| ---"):
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                if len(cells) >= 7:
                    thr_text = cells[0]
                    selected = "chọn" in thr_text.lower()
                    thr_num = re.search(r"\d+(?:\.\d+)?", thr_text)
                    rows.append({
                        "threshold": thr_num.group(0) if thr_num else thr_text,
                        "selected": selected,
                        "precision": float(cells[1]),
                        "recall": float(cells[2]),
                        "f1": float(cells[3]),
                        "fpr": float(cells[4]),
                        "review_rate": float(cells[5]),
                        "malicious_approved": int(cells[6]),
                    })
            elif stripped and not stripped.startswith("|"):
                note = stripped
        if rows:
            sweeps.append({"config": slug.upper(), "rows": rows, "note": note})
    return sweeps


def _load_datasets(data_dir: Path) -> list[dict]:
    specs = (
        ("labels-v1", data_dir / "labels-v1.csv", "Đã đóng băng (15/11)"),
        ("labels-v2", data_dir / "labels-v2.csv", "Đã đóng băng"),
        ("labels-v2-draft", data_dir / "labels-v2-draft.csv", "Bản nháp pha 1 (chưa đóng băng)"),
    )
    out = []
    for name, path, status in specs:
        if not path.is_file():
            continue
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if not rows:
            continue
        by_label = Counter(r.get("label") or "" for r in rows)
        by_split = Counter(r.get("split") or "" for r in rows)
        has_v2_cols = "source_kind" in rows[0] or "time_split" in rows[0]
        by_source = Counter(r.get("source_kind") or "" for r in rows) if "source_kind" in rows[0] else {}
        by_year = Counter((r.get("source_date") or "")[:4] or "unknown" for r in rows) if "source_date" in rows[0] else {}
        by_time = Counter(r.get("time_split") or "" for r in rows) if "time_split" in rows[0] else {}
        test_after = sum(1 for r in rows if r.get("split") == "test" and r.get("time_split") == "after") if has_v2_cols else None
        out.append({
            "name": name,
            "status": status,
            "total": len(rows),
            "by_label": dict(sorted(by_label.items())),
            "by_split": dict(sorted(by_split.items())),
            "by_source": dict(sorted(by_source.items())) if by_source else None,
            "by_year": dict(sorted(by_year.items())) if by_year else None,
            "by_time": dict(sorted(by_time.items())) if by_time else None,
            "test_after": test_after,
        })
    return out


def _load_prompt_injection(reports_root: Path) -> dict | None:
    for filename in ("inj1109b-summary.json", "inj1109-summary.json"):
        data = _read_json(reports_root / filename)
        if not isinstance(data, dict) or not isinstance(data.get("placements"), dict):
            continue
        labels = {
            "none": "Không mồi (đối chứng)",
            "comment": "Mồi trong chú thích (comment)",
            "string": "Mồi trong chuỗi ký tự (string)",
            "readme": "Mồi trong README",
            "fake_result": "Mồi giả đầu ra tool",
        }
        placements = []
        for key in ("none", "comment", "string", "readme", "fake_result"):
            item = data["placements"].get(key)
            if not isinstance(item, dict):
                continue
            models = item.get("models") or {}
            per_model = {}
            for cfg in ("A-LLM-X", "A-SLM-X", "A-TLM-X"):
                mv = models.get(cfg)
                if not isinstance(mv, dict):
                    continue
                per_model[cfg] = {
                    "run_id": mv.get("run_id"),
                    "n": mv.get("n", 0),
                    "model_fooled": mv.get("model_fooled", 0),
                    "system_fooled": mv.get("system_fooled", 0),
                    "denied": mv.get("denied", 0),
                    "review": mv.get("review", 0),
                }
            placements.append({
                "key": key,
                "label": labels.get(key, key),
                "what": item.get("what") or "",
                "models": per_model,
            })
        if placements:
            return {"source": filename, "lure": data.get("lure") or "", "placements": placements}
    return None


def _load_anti_rote(reports_root: Path) -> list[dict]:
    specs = (
        ("corpus-base-summary.json", "Trước L1–L4 (mốc đầu)"),
        ("corpus-v2-summary.json", "Sau L1–L4 (chuẩn)"),
        ("corpus-x1108-summary.json", "Sau L1–L4 (bộ -X)"),
        ("abl-no-alias-summary.json", "Ablation: tắt che tên (L1)"),
        ("abl-no-l2-summary.json", "Ablation: tắt kiểm dòng (L2)"),
    )
    rows: list[dict] = []
    for filename, stage in specs:
        data = _read_json(reports_root / filename)
        if not isinstance(data, dict):
            continue
        for model, entry in data.items():
            if not isinstance(entry, dict) or "total" not in entry:
                continue
            rows.append({
                "stage": stage,
                "model": model,
                "total": entry.get("total"),
                "safe": entry.get("safe"),
                "strict_correct": entry.get("strict_correct"),
                "malicious_denied": entry.get("malicious_denied"),
                "n_malicious": entry.get("n_malicious"),
                "malicious_approved": entry.get("malicious_approved"),
                "benign_denied": entry.get("benign_denied"),
                "pairs_separated": entry.get("pairs_separated"),
                "n_pairs": entry.get("n_pairs"),
            })
    return rows


def build_benchmarks(reports_root: Path, data_dir: Path) -> dict:
    """Collect read-only project benchmark tables from `reports/` and `data/`."""
    return {
        "comparisons": _load_comparisons(reports_root),
        "osv_ablation": _load_osv_ablation(reports_root),
        "sandbox": _load_sandbox_summary(reports_root),
        "sweeps": _load_sweeps(reports_root),
        "datasets": _load_datasets(data_dir),
        "prompt_injection": _load_prompt_injection(reports_root),
        "anti_rote": _load_anti_rote(reports_root),
    }
