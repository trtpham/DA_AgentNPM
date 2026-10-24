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
        assert status == 200 and len(json.loads(body)) == 3
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
