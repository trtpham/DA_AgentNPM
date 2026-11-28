"""Loopback-only, read-only HTTP access to agent traces."""

import csv
import json
import re
import statistics
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from agent.trace import trace_filename
from experiments.dataset import load_labels
# Gate B0 2026-11-21: free text in traces is stored as `<field>_b64` + `<field>_encoding`. The viewer decodes
# with the one shared reader, in memory only; nothing decoded is written to disk.
from experiments.encoding import decode_fields
from experiments.metrics import load_results, score
from experiments.run_batch import result_name
from viewer.benchmarks import build_benchmarks


RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
PACKAGE = re.compile(r"(?:@[a-z0-9._-]+/)?[a-z0-9._-]+@[A-Za-z0-9._+-]+\Z")
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/index.html": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/ui.mjs": ("ui.mjs", "text/javascript; charset=utf-8"),
          "/summary.mjs": ("summary.mjs", "text/javascript; charset=utf-8"),
          # 3D office (KE_HOACH_VAN_PHONG_3D.md): read-only view of the same traces; Three.js is vendored.
          "/office": ("office.html", "text/html; charset=utf-8"),
          "/office.html": ("office.html", "text/html; charset=utf-8"),
          "/office.css": ("office.css", "text/css; charset=utf-8"),
          **{f"/office/{name}": (f"office/{name}", "text/javascript; charset=utf-8")
             for name in ("main.mjs", "scene.mjs", "events.mjs", "explain.mjs", "people.mjs", "props.mjs", "outdoor.mjs", "logistics.mjs", "truck.mjs", "scenarios.mjs", "fx.mjs", "rules.mjs")},
          **{f"/vendor/{name}": (f"vendor/{name}", "text/javascript; charset=utf-8")
             for name in ("three.module.min.js", "OrbitControls.js")}}
SAMPLE_RUN = "sample_traces"
# Reference labels for the "wrong vs reference" filter and run scoring. Never reads data/samples/.
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
LABELS_FILE = DATA_DIR / "labels-v1.csv" if (DATA_DIR / "labels-v1.csv").is_file() else DATA_DIR / "labels.csv"
REFERENCE_LABELS = {"benign", "suspicious", "malicious"}
SUMMARY_EVENT_TYPES = {"run_start", "verdict", "decision", "run_end", "limit"}
RULE_ORDER = ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R7_review", "R7_flow", "R7_sandbox", "R7_risk", "R8")
# experiments/run_isolated.py writes each trace inside its container at /tmp/run, so the trace's own run_id is
# "run" and not the folder name. A trace is identified by its folder and its hashed file name; inside a run
# folder such a trace belongs to that folder's run (agreed by the PO through the coordinating session, 22/11).
ISOLATED_RUN_ID = "run"


def _same_run(event_run_id, run_id: str) -> bool:
    return event_run_id == run_id or event_run_id == ISOLATED_RUN_ID


def reference_labels(path: Path = LABELS_FILE) -> dict[str, str]:
    """`name@version` -> reference label from labels.csv; an unreadable or missing file gives {}."""
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error, UnicodeError):
        return {}
    labels = {}
    for row in rows:
        name, version, label = (row.get("name") or "").strip(), (row.get("version") or "").strip(), (row.get("label") or "").strip()
        package = f"{name}@{version}"
        if label in REFERENCE_LABELS and PACKAGE.fullmatch(package):
            labels[package] = label
    return labels


def _inside(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


def _events(path: Path) -> tuple[list[dict], bool]:
    events = []
    valid = True
    with path.open("r", encoding="utf-8", errors="replace") as source:
        for line in source:
            if not line.endswith("\n"):
                continue  # Writer may still be appending this line.
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("trace event is not an object")
                # Old plain traces pass through unchanged; a field that cannot be decoded drops its line,
                # like any other malformed line, instead of breaking the whole trace.
                events.append(decode_fields(event))
            except (json.JSONDecodeError, ValueError, TypeError):
                valid = False
    return events, valid


def _package_summary_events(path: Path) -> tuple[dict | None, list[dict], bool]:
    """Fast scan of one trace for /api/runs/<run>/packages: decodes only summary event types."""
    first = None
    summary_events = []
    valid = True
    with path.open("r", encoding="utf-8", errors="replace") as source:
        for line in source:
            if not line.endswith("\n"):
                continue
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("trace event is not an object")
                if first is None:
                    first = event
                if event.get("type") in SUMMARY_EVENT_TYPES:
                    decoded = decode_fields(event)
                    summary_events.append(decoded)
            except (json.JSONDecodeError, ValueError, TypeError):
                valid = False
    return first, summary_events, valid


def _load_label_rows(path: Path) -> list[dict[str, str]]:
    """Read label rows for experiments.metrics.score(); unreadable/missing file gives []."""
    try:
        return load_labels(path)
    except ValueError:
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
        except (OSError, csv.Error, UnicodeError):
            return []
        cleaned = []
        for row in rows:
            name, version, label = (row.get("name") or "").strip(), (row.get("version") or "").strip(), (row.get("label") or "").strip()
            if label in REFERENCE_LABELS and PACKAGE.fullmatch(f"{name}@{version}"):
                cleaned.append({"name": name, "version": version, "label": label, "split": (row.get("split") or "").strip()})
        return cleaned
    except (OSError, csv.Error, UnicodeError):
        return []


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return decode_fields(data)
    except (ValueError, TypeError):
        return None


def _safe_report_subpath(reports_root: Path, value: str | None) -> Path | None:
    if not value or not isinstance(value, str):
        return None
    raw = Path(value)
    candidates = [raw] if raw.is_absolute() else [reports_root / raw, reports_root.parent / raw]
    for candidate in candidates:
        resolved = candidate.resolve()
        if _inside(resolved, reports_root) and resolved.is_dir():
            return resolved
    return None


def _rule_sort_key(rule: str) -> tuple[int, int, str]:
    if rule in RULE_ORDER:
        return (0, RULE_ORDER.index(rule), rule)
    return (1, 0, rule)


def _rule_distribution(items: list[dict]) -> list[dict]:
    counts: dict[str, dict] = {}
    for item in items:
        decision = item.get("decision") if isinstance(item.get("decision"), dict) else item
        rule = decision.get("rule") or "none"
        action = decision.get("action")
        bucket = counts.setdefault(rule, {"rule": rule, "total": 0, "deny": 0, "review": 0, "approve": 0})
        bucket["total"] += 1
        if action in ("deny", "review", "approve"):
            bucket[action] += 1
    return [counts[key] for key in sorted(counts, key=_rule_sort_key)]


def _summary_cases(results: list[dict], truth: dict[str, str], run_dir: Path) -> list[dict]:
    cases = []
    for result in results:
        package = result.get("package")
        if not package:
            continue
        decision = result.get("decision") or {}
        verdict = result.get("verdict") if isinstance(result.get("verdict"), dict) else {}
        summary = result.get("verdict_summary") if isinstance(result.get("verdict_summary"), dict) else {}
        expected = truth.get(package)
        label = decision.get("label")
        action = decision.get("action")
        proposal_label = summary.get("label") or verdict.get("label")
        proposal_action = summary.get("action") or verdict.get("action")
        confidence = summary.get("confidence") if summary.get("confidence") is not None else verdict.get("confidence")
        flagged = label in ("suspicious", "malicious")
        kinds = []
        if expected and expected != "benign" and action == "approve":
            kinds.append("malicious_approved")
        elif expected and expected != "benign" and not flagged:
            kinds.append("miss")
        elif expected == "benign" and flagged:
            kinds.append("false_positive")
        if proposal_label and label and (proposal_label != label or (proposal_action and action and proposal_action != action)):
            kinds.append("disagree")
        if result.get("status") == "error":
            kinds.append("error")
        trace_name = result.get("trace")
        has_trace = bool(trace_name and isinstance(trace_name, str) and _inside(run_dir / trace_name, run_dir) and (run_dir / trace_name).is_file())
        cases.append({
            "package": package,
            "expected": expected,
            "label": label,
            "action": action,
            "rule": decision.get("rule"),
            "reason": "; ".join(decision.get("reasons") or [])[:240],
            "proposal_label": proposal_label,
            "proposal_action": proposal_action,
            "confidence": confidence,
            "status": result.get("status"),
            "error": result.get("error"),
            "steps": result.get("steps"),
            "elapsed_s": result.get("elapsed_s"),
            "has_trace": has_trace,
            "kinds": kinds,
        })
    order = {"malicious_approved": 0, "miss": 1, "false_positive": 2, "error": 3, "disagree": 4}
    return sorted(cases, key=lambda item: (min((order[k] for k in item["kinds"]), default=9), item["package"]))


def make_server(reports: str | Path, port: int = 8765, labels_file: Path = LABELS_FILE) -> ThreadingHTTPServer:
    reports_root = Path(reports).resolve()
    viewer_root = Path(__file__).parent.resolve()
    forbidden = (viewer_root.parent / "data" / "samples").resolve()
    if _inside(reports_root, forbidden) or _inside(forbidden, reports_root):
        raise ValueError("reports must not include data/samples")
    static_root = (viewer_root / "static").resolve()
    sample_root = (viewer_root / SAMPLE_RUN).resolve()
    if not _inside(static_root, viewer_root) or not _inside(sample_root, viewer_root):
        raise ValueError("viewer assets outside viewer directory")

    class Handler(BaseHTTPRequestHandler):
        def __getattr__(self, name):
            if name.startswith("do_"):
                return self._method_not_allowed
            raise AttributeError(name)

        def _send(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8",
                  *, allow: bool = False) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Security-Policy", "default-src 'self'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            if allow:
                self.send_header("Allow", "GET, HEAD")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, value, *, allow: bool = False) -> None:
            self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), allow=allow)

        def _method_not_allowed(self) -> None:
            self._json(405, {"error": "method_not_allowed"}, allow=True)

        def _run_dir(self, run_id: str) -> Path:
            if not RUN_ID.fullmatch(run_id):
                raise ValueError("invalid run_id")
            if run_id == SAMPLE_RUN:
                return sample_root
            run_dir = reports_root / run_id
            if not _inside(run_dir, reports_root):
                raise ValueError("run outside reports")
            if not run_dir.is_dir():
                raise FileNotFoundError(run_id)
            return run_dir

        def _trace_file(self, run_id: str, package: str) -> Path:
            if not PACKAGE.fullmatch(package):
                raise ValueError("invalid package")
            run_dir = self._run_dir(run_id)
            path = run_dir / trace_filename(package)
            if not _inside(path, run_dir):
                raise ValueError("trace outside run")
            if not path.is_file():
                raise FileNotFoundError(package)
            return path

        def _runs(self) -> list[str]:
            runs = {SAMPLE_RUN} if sample_root.is_dir() else set()
            if reports_root.is_dir():
                runs.update(path.name for path in reports_root.iterdir()
                            if path.is_dir() and RUN_ID.fullmatch(path.name)
                            and _inside(path, reports_root) and path.name != SAMPLE_RUN)
            return sorted(runs)

        def _packages(self, run_id: str) -> list[dict]:
            run_dir = self._run_dir(run_id)
            packages = []
            for path in run_dir.glob("*.trace.jsonl"):
                if not _inside(path, run_dir) or not path.is_file():
                    continue
                first, events, valid_lines = _package_summary_events(path)
                if not first:
                    continue
                package = first.get("package")
                if not isinstance(package, str) or not PACKAGE.fullmatch(package):
                    continue
                if path.name != trace_filename(package) or not _same_run(first.get("run_id"), run_id):
                    continue
                start = next((event for event in events if event.get("type") == "run_start"), {})
                verdict = next((event for event in reversed(events) if event.get("type") == "verdict"), {})
                end = next((event for event in reversed(events) if event.get("type") == "run_end"), {})
                decision = next((event for event in reversed(events) if event.get("type") == "decision"), {})
                final_verdict = verdict.get("verdict") if verdict.get("valid") else None
                checks = decision.get("evidence_checks") if isinstance(decision.get("evidence_checks"), list) else []
                packages.append({"package": package, "model": start.get("model"),
                                 "label": decision.get("final_label") or (final_verdict or {}).get("label"),
                                 "action": decision.get("final_action"), "rule": decision.get("rule"),
                                 "proposal_label": (final_verdict or {}).get("label"),
                                 "proposal_action": (final_verdict or {}).get("action"),
                                 "evidence_total": len(checks),
                                 "evidence_ok": sum(1 for check in checks if isinstance(check, dict) and check.get("exists") is True),
                                 "confidence": (final_verdict or {}).get("confidence"),
                                 "steps": end.get("steps"), "elapsed_s": end.get("elapsed_s"),
                                 "valid_json": valid_lines and verdict.get("valid") if verdict else None,
                                 "status": "error" if any(event.get("type") == "limit" for event in events)
                                 else "done" if end else "running"})
            return sorted(packages, key=lambda item: item["package"])

        def _trace(self, query: str) -> list[dict]:
            params = parse_qs(query, keep_blank_values=True, max_num_fields=3)
            if set(params) != {"run", "pkg", "after"} or any(len(values) != 1 for values in params.values()):
                raise ValueError("invalid trace query")
            after_text = params["after"][0]
            if not re.fullmatch(r"-?[0-9]{1,10}", after_text) or int(after_text) < -1:
                raise ValueError("invalid after")
            run_id, package = params["run"][0], params["pkg"][0]
            events, _ = _events(self._trace_file(run_id, package))
            return [event for event in events if _same_run(event.get("run_id"), run_id)
                    and event.get("package") == package and type(event.get("seq")) is int
                    and event["seq"] > int(after_text)]

        def _summary(self, run_id: str, query: str) -> dict:
            params = parse_qs(query, keep_blank_values=True, max_num_fields=2) if query else {}
            if not set(params) <= {"split"} or any(len(values) != 1 for values in params.values()):
                raise ValueError("invalid summary query")
            asked_split = params.get("split", ["auto"])[0]
            if asked_split not in ("auto", "dev", "test", "all"):
                raise ValueError("invalid split")
            run_dir = self._run_dir(run_id)
            meta = _read_json(run_dir / "run_meta.json") or {}
            unreadable: list[str] = []
            results = load_results(run_dir, unreadable) if run_id != SAMPLE_RUN else []
            all_labels = _load_label_rows(labels_file)
            seen_packages = {item.get("package") for item in results if item.get("package")}
            if not seen_packages:
                seen_packages = {item["package"] for item in self._packages(run_id)}
            if asked_split == "auto":
                splits = {row.get("split") for row in all_labels if f"{row['name']}@{row['version']}" in seen_packages and row.get("split")}
                resolved_split = next(iter(splits)) if len(splits) == 1 and splits <= {"dev", "test"} else None
            else:
                resolved_split = None if asked_split == "all" else asked_split
            selected_labels = [row for row in all_labels if not resolved_split or row.get("split") == resolved_split]
            truth = {f"{row['name']}@{row['version']}": row["label"] for row in selected_labels}

            if results:
                metrics = score(results, selected_labels, "agent")
                scored_items = [item for item in results if item.get("package") in truth]
                seconds = [item["elapsed_s"] for item in scored_items if isinstance(item.get("elapsed_s"), (int, float))]
                malicious_approved = sum(
                    truth[item["package"]] == "malicious" and (item.get("decision") or {}).get("action") == "approve"
                    for item in scored_items
                )
                suspicious_approved = sum(
                    truth[item["package"]] == "suspicious" and (item.get("decision") or {}).get("action") == "approve"
                    for item in scored_items
                )
                rules = _rule_distribution(results)
                cases = _summary_cases(results, truth, run_dir)
                total_packages = len(results)
            else:
                pkg_items = self._packages(run_id)
                metrics = score([], selected_labels, "agent")
                seconds = [item["elapsed_s"] for item in pkg_items if isinstance(item.get("elapsed_s"), (int, float))]
                malicious_approved = 0
                suspicious_approved = 0
                rules = _rule_distribution(pkg_items)
                cases = []
                total_packages = len(pkg_items)

            guarddog = None
            guarddog_source = None
            if selected_labels and run_id != SAMPLE_RUN:
                for candidate in (run_dir / "guarddog", reports_root / "guarddog-v1" / "guarddog"):
                    resolved = candidate.resolve()
                    if not _inside(resolved, reports_root) or not resolved.is_dir():
                        continue
                    gd_unreadable: list[str] = []
                    gd_metrics = score(load_results(resolved, gd_unreadable), selected_labels, "guarddog")
                    if gd_metrics["scored"] > 0:
                        guarddog = {**gd_metrics, "unreadable": gd_unreadable}
                        guarddog_source = resolved.relative_to(reports_root).as_posix()
                        break

            config = meta.get("config") if isinstance(meta.get("config"), dict) else {}
            return {
                "run_id": run_id,
                "split": resolved_split or "all",
                "asked_split": asked_split,
                "total_packages": total_packages,
                "has_results": bool(results),
                "meta": {
                    "model": meta.get("model") or config.get("model"),
                    "config_name": config.get("name"),
                    "deny_threshold": config.get("deny_threshold"),
                    "approve_threshold": config.get("approve_threshold"),
                    "contexts_used": bool(meta.get("contexts")),
                    "sandbox_used": bool(meta.get("sandbox_results")),
                    "resources": meta.get("resources"),
                },
                "metrics": metrics,
                "malicious_approved": malicious_approved,
                "suspicious_approved": suspicious_approved,
                "median_seconds": round(statistics.median(seconds), 1) if seconds else None,
                "unreadable": unreadable,
                "guarddog": guarddog,
                "guarddog_source": guarddog_source,
                "rules": rules,
                "cases": cases,
            }

        def _package_extra(self, query: str) -> dict:
            params = parse_qs(query, keep_blank_values=True, max_num_fields=2)
            if set(params) != {"run", "pkg"} or any(len(values) != 1 for values in params.values()):
                raise ValueError("invalid package-extra query")
            run_id, package = params["run"][0], params["pkg"][0]
            if not PACKAGE.fullmatch(package):
                raise ValueError("invalid package")
            run_dir = self._run_dir(run_id)
            meta = _read_json(run_dir / "run_meta.json") or {}
            filename = result_name(package)

            result_path = run_dir / filename
            raw_result = _read_json(result_path) if _inside(result_path, run_dir) and result_path.is_file() else None
            result_info = None
            if raw_result:
                result_info = {
                    "status": raw_result.get("status"),
                    "error": raw_result.get("error"),
                    "decision": raw_result.get("decision"),
                    "planned_command": raw_result.get("planned_command"),
                    "container_peak_mb": raw_result.get("container_peak_mb"),
                    "verdict_summary": raw_result.get("verdict_summary"),
                    "errors": raw_result.get("errors"),
                    "steps": raw_result.get("steps"),
                    "elapsed_s": raw_result.get("elapsed_s"),
                }

            osv_info = None
            ctx_dir = _safe_report_subpath(reports_root, meta.get("contexts"))
            ctx_used = bool(ctx_dir)
            if ctx_dir is None and run_id != SAMPLE_RUN:
                fallback = (reports_root / "contexts-v1").resolve()
                if _inside(fallback, reports_root) and fallback.is_dir():
                    ctx_dir = fallback
            if ctx_dir is not None:
                ctx_file = ctx_dir / filename
                ctx_data = _read_json(ctx_file) if _inside(ctx_file, ctx_dir) and ctx_file.is_file() else None
                if ctx_data:
                    osv_block = ctx_data.get("osv") if isinstance(ctx_data.get("osv"), dict) else {}
                    osv_data = osv_block.get("data") if isinstance(osv_block.get("data"), dict) else {}
                    reg_block = ctx_data.get("registry") if isinstance(ctx_data.get("registry"), dict) else {}
                    reg_data = reg_block.get("data") if isinstance(reg_block.get("data"), dict) else {}
                    osv_info = {
                        "used_in_run": ctx_used,
                        "ok": bool(osv_block.get("ok")),
                        "malicious": bool(osv_data.get("malicious")),
                        "vulns": (osv_data.get("vulns") or [])[:10],
                        "error": osv_block.get("error"),
                        "registry": {
                            "ok": bool(reg_block.get("ok")),
                            "versions": reg_data.get("versions"),
                            "previous_version": reg_data.get("previous_version"),
                            "hooks_changed_since_previous": reg_data.get("hooks_changed_since_previous"),
                            "maintainers": reg_data.get("maintainers"),
                            "deprecated": reg_data.get("deprecated"),
                        } if reg_block else None,
                    }

            sandbox_info = None
            sbx_dir = _safe_report_subpath(reports_root, meta.get("sandbox_results"))
            sbx_used = bool(sbx_dir)
            sbx_candidates = [sbx_dir] if sbx_dir is not None else []
            if sbx_dir is None and run_id != SAMPLE_RUN:
                for name in ("sbx-test-v1b/sandbox", "sbx-dev-v1b/sandbox"):
                    cand = (reports_root / name).resolve()
                    if _inside(cand, reports_root) and cand.is_dir():
                        sbx_candidates.append(cand)
            for cand in sbx_candidates:
                sbx_file = cand / filename
                sbx_raw = _read_json(sbx_file) if _inside(sbx_file, cand) and sbx_file.is_file() else None
                if sbx_raw:
                    data = sbx_raw.get("data") if isinstance(sbx_raw.get("data"), dict) else {}
                    behavior = data.get("behavior") if isinstance(data.get("behavior"), dict) else {}
                    by_actor = data.get("by_actor") if isinstance(data.get("by_actor"), dict) else {}
                    pkg_files = (by_actor.get("package") or {}).get("files_outside_package") or []
                    sandbox_info = {
                        "used_in_run": sbx_used,
                        "source_dir": cand.relative_to(reports_root).as_posix(),
                        "ok": bool(sbx_raw.get("ok")),
                        "outcome": data.get("outcome"),
                        "script_ran": data.get("script_ran"),
                        "fail_reason": sbx_raw.get("fail_reason") or data.get("fail_reason"),
                        "error": sbx_raw.get("error"),
                        "canary_touched": list(data.get("canary_touched") or []),
                        "connects": (behavior.get("connects") or [])[:20],
                        "persistence_writes": (behavior.get("persistence_writes") or [])[:20],
                        "process_tree": (behavior.get("process_tree") or [])[:20],
                        "package_files_outside": list(pkg_files)[:20],
                    }
                    break

            return {"result": result_info, "osv": osv_info, "sandbox": sandbox_info}

        def do_GET(self) -> None:
            self._get()

        def do_HEAD(self) -> None:
            self._get()

        def _get(self) -> None:
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)
            try:
                if path in STATIC:
                    name, content_type = STATIC[path]
                    file = static_root / name
                    if not _inside(file, static_root) or not file.is_file():
                        raise FileNotFoundError(name)
                    self._send(200, file.read_bytes(), content_type)
                elif path == "/api/runs":
                    self._json(200, self._runs())
                elif path.startswith("/api/runs/") and path.endswith("/packages"):
                    parts = path.split("/")
                    if len(parts) != 5:
                        raise ValueError("invalid run path")
                    self._json(200, self._packages(parts[3]))
                elif path.startswith("/api/runs/") and path.endswith("/summary"):
                    parts = path.split("/")
                    if len(parts) != 5:
                        raise ValueError("invalid run path")
                    self._json(200, self._summary(parts[3], parsed.query))
                elif path == "/api/trace":
                    self._json(200, self._trace(parsed.query))
                elif path == "/api/package-extra":
                    self._json(200, self._package_extra(parsed.query))
                elif path == "/api/labels":
                    self._json(200, reference_labels(labels_file))
                elif path == "/api/benchmarks":
                    self._json(200, build_benchmarks(reports_root, labels_file.parent))
                else:
                    self._json(404, {"error": "not_found"})
            except (ValueError, UnicodeError) as error:
                self._json(400, {"error": str(error)})
            except FileNotFoundError:
                self._json(404, {"error": "not_found"})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
