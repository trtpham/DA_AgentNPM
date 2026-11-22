"""'Agent + OSV' from runs made without OSV, and an 'OSV only' baseline (read only).

OSV reaches a decision only through rule R5 of agent/decide.py: it is checked after R1-R4 and
only for a benign verdict, and turns it into suspicious/review. Every other input of decide() is
independent of OSV, so for a stored decision:
- rule R1-R4 (canary, failed run, unverified evidence): unchanged with OSV;
- verdict benign and OSV MAL: R5 (suspicious, review);
- anything else: unchanged.
The flag is derived exactly as agent/run.py does: osv.ok and osv.data.malicious.

    py -3.14 -m experiments.osv_ablation reports/dev-v1-a-llm --contexts reports/contexts-v1 \
        --labels data/labels-v1.csv --split dev
"""

import argparse
import json
from pathlib import Path

from experiments.dataset import load_labels
from experiments.metrics import load_results, score

BEFORE_R5 = ("R1", "R2", "R3", "R4")
KNOWN_RULES = BEFORE_R5 + ("R5", "R6", "R7", "R7_review", "R7_flow", "R7_sandbox", "R7_risk", "R8")


def context_name(package: str) -> str:
    return package.replace("/", "__") + ".json"


def osv_malicious(context: dict | None) -> bool:
    osv = (context or {}).get("osv") or {}
    return bool(osv.get("ok") and (osv.get("data") or {}).get("malicious"))


def load_osv(directory: Path, packages: list[str]) -> dict[str, bool | None]:
    """OSV MAL flag per package; None when the context file is missing or the lookup failed."""
    flags: dict[str, bool | None] = {}
    for package in packages:
        path = directory / context_name(package)
        if not path.is_file():
            flags[package] = None
            continue
        context = json.loads(path.read_text(encoding="utf-8"))
        flags[package] = osv_malicious(context) if (context.get("osv") or {}).get("ok") else None
    return flags


def with_osv(result: dict, flag: bool | None) -> tuple[dict, bool]:
    """The result as decide() would have returned it with the OSV flag; (result, changed)."""
    decision = result.get("decision")
    verdict = result.get("verdict")
    if not flag or not decision or decision.get("rule") in BEFORE_R5:
        return result, False
    if not isinstance(verdict, dict) or verdict.get("label") != "benign":
        return result, False
    changed = dict(result)
    changed["decision"] = {"label": "suspicious", "action": "review", "rule": "R5",
                           "reasons": ["OSV MAL signal blocks automatic approval"]}
    return changed, True


def consistency_problems(results: list[dict]) -> list[str]:
    """Stored decisions that do not fit the rule order, so R5 cannot be replayed safely on them."""
    problems = []
    for result in results:
        decision, verdict = result.get("decision"), result.get("verdict")
        package = result.get("package")
        if not decision:
            continue
        rule = decision.get("rule")
        if rule not in KNOWN_RULES:
            problems.append(f"{package}: unknown rule {rule}")
        elif rule == "R5":
            problems.append(f"{package}: run already used OSV (R5)")
        elif rule not in BEFORE_R5 and not isinstance(verdict, dict):
            problems.append(f"{package}: rule {rule} without a stored verdict")
        elif rule.startswith("R7") and verdict.get("label") != "benign":
            problems.append(f"{package}: rule {rule} with verdict {verdict.get('label')}")
        elif rule == "R6" and verdict.get("label") != "malicious":
            problems.append(f"{package}: rule R6 with verdict {verdict.get('label')}")
    return problems


def osv_only(packages: list[str], flags: dict[str, bool | None]) -> list[dict]:
    """Baseline: OSV MAL means malicious, otherwise benign; a failed lookup counts as no finding."""
    return [{"package": package, "status": "ok",
             "decision": {"label": "malicious" if flags.get(package) else "benign",
                          "action": "deny" if flags.get(package) else "approve", "rule": "OSV"}}
            for package in packages]


def ablate(results: list[dict], labels: list[dict], flags: dict[str, bool | None]) -> dict:
    labelled = {f"{row['name']}@{row['version']}" for row in labels}
    truth = {f"{row['name']}@{row['version']}": row["label"] for row in labels}
    adjusted, changed = [], []
    for result in results:
        new, did = with_osv(result, flags.get(result.get("package")))
        adjusted.append(new)
        if did and result.get("package") in labelled:
            changed.append(result["package"])

    def approved_not_benign(rows: list[dict]) -> int:
        return sum(1 for row in rows if row.get("package") in labelled
                   and truth[row["package"]] != "benign"
                   and (row.get("decision") or {}).get("action") == "approve")

    return {"without_osv": score(results, labels), "with_osv": score(adjusted, labels),
            "changed": sorted(changed),
            "approved_not_benign": {"without_osv": approved_not_benign(results),
                                    "with_osv": approved_not_benign(adjusted)},
            "osv_lookup_missing": sorted(p for p in labelled if flags.get(p) is None)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent with and without OSV (R5 replay), read only")
    parser.add_argument("results", type=Path, nargs="?", help="reports/<run_id>; omit with --osv-only")
    parser.add_argument("--contexts", type=Path, default=Path("reports/contexts-v1"))
    parser.add_argument("--labels", type=Path, default=Path("data/labels-v1.csv"))
    parser.add_argument("--split", choices=("dev", "test"))
    parser.add_argument("--osv-only", action="store_true", help="score the OSV-only baseline instead")
    args = parser.parse_args()
    labels = [row for row in load_labels(args.labels) if not args.split or row["split"] == args.split]
    packages = [f"{row['name']}@{row['version']}" for row in labels]
    flags = load_osv(args.contexts, packages)
    if args.osv_only:
        out = {"osv_only": score(osv_only(packages, flags), labels),
               "osv_lookup_missing": sorted(p for p in packages if flags[p] is None)}
    else:
        if args.results is None:
            parser.error("results directory required unless --osv-only")
        results = load_results(args.results)
        problems = consistency_problems(results)
        if problems:
            raise SystemExit("stored decisions do not fit the rule order:\n" + "\n".join(problems[:20]))
        out = ablate(results, labels, flags)
    out["split"] = args.split
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
