"""Extract step-by-step SFT training conversations from verified agent traces (T5 step 3).

Strict rules (KE_HOACH_TUAN_7_9 §4.3 & BAN_GIAO T5):
- Only `split == "train"` rows may enter the dataset; `dev` and `test` are rejected.
- Keep only runs whose final decision matches the ground-truth label and every cited
  behavior has `exists is True`.
- Trace text is decoded in memory only via `decode_fields` / `read_events` and blinded
  with `BLIND_ALIAS` so the trained model matches inference blinding (`A-SLM-X`).
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from agent.run import DEFAULT_TOOLS, EXPLORE_HINT, SYSTEM, tool_schemas
from agent.semantics import BLIND_ALIAS, blind_text
from experiments.dataset import load_labels
from experiments.encoding import decode_fields, read_events
from experiments.run_batch import load_config


def load_train_partition(labels_path: Path, split: str = "train") -> tuple[dict[tuple[str, str], dict], set[tuple[str, str]], set[str]]:
    """Return `(train_by_pkg, forbidden_keys, forbidden_clusters)`; only `split='train'` is allowed."""
    if split != "train":
        raise ValueError("SFT extraction allows only split='train'; dev and test are strictly forbidden")
    rows = load_labels(labels_path)
    forbidden_keys = {(r["name"], r["version"]) for r in rows if r["split"] != "train"}
    forbidden_clusters = {r["cluster"] for r in rows if r["split"] != "train" and r.get("cluster")}
    train_by_pkg = {}
    for row in rows:
        if row["split"] != "train":
            continue
        key = (row["name"], row["version"])
        if key in forbidden_keys or (row.get("cluster") and row["cluster"] in forbidden_clusters):
            continue
        train_by_pkg[key] = row
    return train_by_pkg, forbidden_keys, forbidden_clusters


def accepted_decision(result: dict, events: list[dict], expected_label: str) -> tuple[bool, str]:
    """Verify ground-truth label match, `valid=True` verdict, and `exists=True` on all checks."""
    decision_ev = next((ev for ev in reversed(events) if ev.get("type") == "decision"), None)
    if decision_ev is not None:
        final_label = decision_ev.get("final_label")
        checks = decision_ev.get("evidence_checks")
    else:
        decision = result.get("decision") or {}
        final_label = decision.get("label")
        checks = None

    if final_label != expected_label:
        return False, "label_mismatch"
    if not isinstance(checks, list) or not checks:
        return False, "missing_evidence_checks"
    if not all(isinstance(c, dict) and c.get("exists") is True for c in checks):
        return False, "unverified_evidence"

    verdict_ev = next((ev for ev in reversed(events) if ev.get("type") == "verdict" and ev.get("valid") is True), None)
    if verdict_ev is None or not isinstance(verdict_ev.get("verdict"), dict):
        return False, "no_valid_verdict"
    return True, "ok"


def _blind_payload(obj, names: list[str]):
    if isinstance(obj, str):
        return blind_text(obj, names)
    if isinstance(obj, list):
        return [_blind_payload(item, names) for item in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "package":
                out[k] = BLIND_ALIAS
            else:
                out[k] = _blind_payload(v, names)
        return out
    return obj


def _strip_evidence_checks(events: list[dict]) -> list[dict]:
    """Remove host-side `Evidence check` read_file calls/results emitted during verdict checks."""
    cleaned: list[dict] = []
    i = 0
    while i < len(events):
        ev = events[i]
        if (
            ev.get("type") == "tool_call"
            and i + 1 < len(events)
            and events[i + 1].get("type") == "tool_result"
            and events[i + 1].get("summary") == "Evidence check"
        ):
            i += 2
            continue
        if ev.get("type") == "tool_result" and ev.get("summary") == "Evidence check":
            i += 1
            continue
        cleaned.append(ev)
        i += 1
    return cleaned


def build_sft_conversation(
    package_id: str,
    result: dict,
    events: list[dict],
    *,
    tools: tuple[str, ...] = DEFAULT_TOOLS,
) -> dict | None:
    """Convert one verified trace into ChatML/Ollama `messages` + `tools`."""
    pkg_name, _, _ = package_id.rpartition("@")
    names = [pkg_name, pkg_name.rsplit("/", 1)[-1]] if pkg_name else []
    cleaned = _strip_evidence_checks(events)

    manifest_preview = None
    indicators_preview = None
    body_start = 0
    for idx, ev in enumerate(cleaned):
        etype = ev.get("type")
        if etype == "run_start":
            body_start = idx + 1
            continue
        if etype == "tool_call" and ev.get("tool") in ("read_manifest", "extract_indicators") and body_start <= idx + 1:
            continue
        if etype == "tool_result" and ev.get("tool") == "read_manifest" and manifest_preview is None:
            manifest_preview = ev.get("data_preview") or ""
            body_start = idx + 1
            continue
        if etype == "tool_result" and ev.get("tool") == "extract_indicators" and indicators_preview is None:
            indicators_preview = ev.get("data_preview") or ""
            body_start = idx + 1
            continue
        break

    final_verdict_idx = None
    for idx in range(len(cleaned) - 1, -1, -1):
        ev = cleaned[idx]
        if ev.get("type") == "verdict" and ev.get("valid") is True and isinstance(ev.get("verdict"), dict):
            final_verdict_idx = idx
            break
    if final_verdict_idx is None:
        return None

    tool_tuple = tuple(tools)
    system = SYSTEM + (EXPLORE_HINT if set(tool_tuple) - set(DEFAULT_TOOLS) else "")
    prompt_parts = [f"Analyze {BLIND_ALIAS}."]
    if manifest_preview is not None:
        prompt_parts.append(f"Manifest data: {blind_text(str(manifest_preview), names)}.")
    if indicators_preview is not None:
        prompt_parts.append(f"Static indicator candidates (untrusted): {blind_text(str(indicators_preview), names)}.")
    prompt_parts.append("Inspect required install source files with read_file and return one valid JSON verdict.")

    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": " ".join(prompt_parts)},
    ]

    pending_thought = ""
    i = body_start
    while i < final_verdict_idx:
        ev = cleaned[i]
        etype = ev.get("type")
        if etype == "thought":
            pending_thought = str(ev.get("text") or "").strip()
            i += 1
            continue
        if etype == "tool_call":
            # Group consecutive tool_call -> tool_result pairs from one model turn
            calls = []
            results = []
            j = i
            while j < final_verdict_idx and cleaned[j].get("type") in ("tool_call", "tool_result"):
                cur = cleaned[j]
                if cur.get("type") == "tool_call":
                    args = cur.get("args") if isinstance(cur.get("args"), dict) else {}
                    calls.append({
                        "type": "function",
                        "function": {"name": cur.get("tool"), "arguments": _blind_payload(args, names)},
                    })
                elif cur.get("type") == "tool_result":
                    preview = cur.get("data_preview")
                    content = (
                        blind_text(preview, names)
                        if isinstance(preview, str)
                        else json.dumps(_blind_payload(preview, names), ensure_ascii=False)
                    )
                    results.append({
                        "role": "tool",
                        "tool_name": str(cur.get("tool") or ""),
                        "content": content or str(cur.get("summary") or ""),
                    })
                j += 1
            if calls and results:
                messages.append({
                    "role": "assistant",
                    "content": blind_text(pending_thought, names) if pending_thought else "",
                    "tool_calls": calls,
                })
                messages.extend(results)
            pending_thought = ""
            i = j
            continue
        if etype in ("hint", "self_check"):
            text = ev.get("question") if etype == "self_check" else ev.get("text")
            if text:
                messages.append({"role": "user", "content": blind_text(str(text), names)})
            i += 1
            continue
        # Skip intermediate invalid verdicts and retry error lines before final verdict
        pending_thought = ""
        i += 1

    blinded_verdict = _blind_payload(cleaned[final_verdict_idx]["verdict"], names)
    messages.append({"role": "assistant", "content": json.dumps(blinded_verdict, ensure_ascii=False)})
    return {"messages": messages, "tools": tool_schemas(tool_tuple)}


def _config_tools(variant: str, configs: Path = Path("experiments/configs")) -> tuple[str, ...]:
    cfg = load_config(variant, configs)
    raw = cfg.get("tools", "")
    if isinstance(raw, str) and raw.startswith("[") and raw.endswith("]"):
        items = [part.strip().strip("'\"") for part in raw[1:-1].split(",") if part.strip()]
        if items:
            return tuple(items)
    if isinstance(raw, (list, tuple)) and raw:
        return tuple(raw)
    return DEFAULT_TOOLS


def extract_sft_dataset(
    run_dir: Path,
    labels_path: Path,
    output_path: Path,
    *,
    split: str = "train",
    config_variant: str = "A-SLM-X",
    configs_dir: Path = Path("experiments/configs"),
) -> dict:
    """Filter `run_dir` to verified `train` traces only and write JSONL atomically."""
    train_by_pkg, forbidden_keys, forbidden_clusters = load_train_partition(labels_path, split=split)
    tools = _config_tools(config_variant, configs_dir) if (configs_dir / f"{config_variant}.yaml").is_file() else DEFAULT_TOOLS

    skipped: Counter[str] = Counter()
    records = []
    matched = 0

    for path in sorted(run_dir.glob("*.json")):
        if path.name == "run_meta.json":
            continue
        result = decode_fields(json.loads(path.read_text(encoding="utf-8")))
        pkg_id = str(result.get("package") or "")
        name, _, version = pkg_id.rpartition("@")
        key = (name, version)
        if key in forbidden_keys:
            skipped["forbidden_split"] += 1
            continue
        row = train_by_pkg.get(key)
        if row is None:
            skipped["not_in_train"] += 1
            continue
        if row.get("cluster") and row["cluster"] in forbidden_clusters:
            skipped["forbidden_cluster"] += 1
            continue
        matched += 1

        trace_rel = result.get("trace")
        if not trace_rel or not (run_dir / trace_rel).is_file():
            skipped["missing_trace"] += 1
            continue
        events = read_events(run_dir / trace_rel)
        ok, reason = accepted_decision(result, events, row["label"])
        if not ok:
            skipped[reason] += 1
            continue

        sample = build_sft_conversation(pkg_id, result, events, tools=tools)
        if sample is None:
            skipped["empty_conversation"] += 1
            continue
        records.append({
            "id": row["id"],
            "package": pkg_id,
            "label": row["label"],
            "cluster": row["cluster"],
            "split": "train",
            "source_run": run_dir.name,
            **sample,
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp_path.write_text(
        "".join(json.dumps(rec, ensure_ascii=False) + "\n" for rec in records),
        encoding="utf-8",
    )
    tmp_path.replace(output_path)

    return {
        "total_train": len(train_by_pkg),
        "matched_traces": matched,
        "kept": len(records),
        "skipped": dict(skipped),
        "output": str(output_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract verified train-only SFT conversations from agent traces")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--labels", type=Path, default=Path("data/labels-v2.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/sft/train.jsonl"))
    parser.add_argument("--split", default="train", help="Only 'train' is accepted")
    parser.add_argument("--config", default="A-SLM-X", help="Target tool config (e.g. A-SLM-X)")
    args = parser.parse_args()
    summary = extract_sft_dataset(
        args.run_dir,
        args.labels,
        args.output,
        split=args.split,
        config_variant=args.config,
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
