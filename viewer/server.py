"""Loopback-only, read-only HTTP access to agent traces."""

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from agent.trace import trace_filename


RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
PACKAGE = re.compile(r"(?:@[a-z0-9._-]+/)?[a-z0-9._-]+@[A-Za-z0-9._+-]+\Z")
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/index.html": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}
SAMPLE_RUN = "sample_traces"


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
                events.append(event)
            except (json.JSONDecodeError, ValueError):
                valid = False
    return events, valid


def make_server(reports: str | Path, port: int = 8765) -> ThreadingHTTPServer:
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
                events, valid_lines = _events(path)
                if not events:
                    continue
                package = events[0].get("package")
                if not isinstance(package, str) or not PACKAGE.fullmatch(package):
                    continue
                if path.name != trace_filename(package) or events[0].get("run_id") != run_id:
                    continue
                start = next((event for event in events if event.get("type") == "run_start"), {})
                verdict = next((event for event in reversed(events) if event.get("type") == "verdict"), {})
                end = next((event for event in reversed(events) if event.get("type") == "run_end"), {})
                decision = next((event for event in reversed(events) if event.get("type") == "decision"), {})
                final_verdict = verdict.get("verdict") if verdict.get("valid") else None
                packages.append({"package": package, "model": start.get("model"),
                                 "label": decision.get("final_label") or (final_verdict or {}).get("label"),
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
            return [event for event in events if event.get("run_id") == run_id
                    and event.get("package") == package and type(event.get("seq")) is int
                    and event["seq"] > int(after_text)]

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
                elif path == "/api/trace":
                    self._json(200, self._trace(parsed.query))
                else:
                    self._json(404, {"error": "not_found"})
            except (ValueError, UnicodeError) as error:
                self._json(400, {"error": str(error)})
            except FileNotFoundError:
                self._json(404, {"error": "not_found"})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
