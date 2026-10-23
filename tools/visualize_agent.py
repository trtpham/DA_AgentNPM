"""Generate a self-contained HTML timeline from a real agent run."""

import argparse
import json
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from agent.run import analyze


LIVE_SCRIPT = '''<script>
  const timeline = document.querySelector('.timeline');
  const result = document.querySelector('.result');
  const resultBody = document.getElementById('result-body');
  const status = document.getElementById('run-status');
  let seen = timeline.querySelectorAll('.event').length;
  function node(tag, text, parent, className) {
    const item = document.createElement(tag);
    item.textContent = text;
    if (className) item.className = className;
    parent.append(item);
    return item;
  }
  async function refresh() {
    try {
      const response = await fetch('/state', {cache: 'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const state = await response.json();
      if (state.trace.length > seen) timeline.querySelector('.empty')?.remove();
      for (const event of state.trace.slice(seen)) {
        const item = node('li', '', timeline, 'event ' + (['ok', 'retry', 'error', 'info'].includes(event.status) ? event.status : ''));
        node('span', String(event.step).padStart(2, '0'), item, 'step');
        const body = node('div', '', item);
        node('span', ({manifest:'Đọc manifest', model:'Lượt model', tool:'Gọi công cụ', feedback:'Yêu cầu đọc nguồn', validation:'Kiểm tra verdict', verdict:'Kết luận', run:'Lỗi chạy'})[event.kind] || event.kind, body, 'event-kind');
        node('p', event.detail, body);
      }
      seen = state.trace.length;
      const manifest = state.trace.find(event => event.kind === 'manifest');
      if (manifest) {
        document.getElementById('package-name').textContent = manifest.detail;
        document.title = 'Quy trình agent · ' + manifest.detail;
      }
      document.getElementById('step-count').textContent = Math.max(0, ...state.trace.map(event => event.step)) + ' bước';
      status.textContent = state.running ? 'Đang chạy' : state.verdict ? 'Đã xác thực' : 'Chưa có verdict hợp lệ';
      result.classList.toggle('pending', state.running);
      result.classList.toggle('bad', !state.running && !state.verdict);
      resultBody.replaceChildren();
      if (state.verdict) {
        const verdict = state.verdict;
        node('p', `${verdict.label} · ${verdict.action} · ${Math.round(verdict.confidence * 100)}% tin cậy`, resultBody, 'label');
        node('p', verdict.description, resultBody);
        node('h3', 'Bằng chứng đã kiểm tra', resultBody);
        const list = node('ul', '', resultBody, 'evidence');
        for (const behavior of verdict.behaviors) {
          const item = node('li', '', list);
          node('strong', behavior.behavior, item);
          node('span', behavior.evidence.file + ':' + behavior.evidence.lines, item);
          node('p', behavior.analysis, item);
        }
      } else {
        node('p', state.running ? 'Đang chờ model...' : 'Chưa thể đánh giá gói', resultBody, 'label');
        if (state.error) node('p', state.error, resultBody);
      }
      if (state.running) setTimeout(refresh, 400);
    } catch (error) {
      status.textContent = 'Mất kết nối với agent';
      setTimeout(refresh, 1500);
    }
  }
  refresh();
</script>'''


def render(variant: str, model: str, trace: list[dict], verdict=None, error: str = "", live: bool = False) -> str:
    clean = lambda value: escape(str(value), quote=True)
    package = next((event["detail"] for event in trace if event["kind"] == "manifest"), "Chưa đọc manifest")
    steps = max((event["step"] for event in trace), default=0)
    status = "Đang chạy" if live and not verdict and not error else "Đã xác thực" if verdict else "Chưa có verdict hợp lệ"
    tone = "pending" if live and not verdict and not error else "good" if verdict else "bad"
    names = {"manifest": "Đọc manifest", "model": "Lượt model", "tool": "Gọi công cụ", "feedback": "Yêu cầu đọc nguồn",
             "validation": "Kiểm tra verdict", "verdict": "Kết luận", "run": "Lỗi chạy"}
    timeline = "\n".join(
        f'<li class="event {clean(event["status"])}"><span class="step">{event["step"]:02d}</span>'
        f'<div><span class="event-kind">{clean(names.get(event["kind"], event["kind"]))}</span>'
        f'<p>{clean(event["detail"])}</p></div></li>' for event in trace
    ) or '<li class="empty">Agent chưa tạo bước nào.</li>'
    if verdict:
        evidence = "\n".join(
            f'<li><strong>{clean(item.behavior)}</strong><span>{clean(item.evidence.file)}:{clean(item.evidence.lines)}</span>'
            f'<p>{clean(item.analysis)}</p></li>' for item in verdict.behaviors
        )
        conclusion = (f'<p class="label">{clean(verdict.label)} · {clean(verdict.action)} · '
                      f'{verdict.confidence:.0%} tin cậy</p><p>{clean(verdict.description)}</p>'
                      f'<h3>Bằng chứng đã kiểm tra</h3><ul class="evidence">{evidence}</ul>')
    elif live and not error:
        conclusion = '<p class="label">Đang chờ model...</p>'
    else:
        conclusion = f'<p class="label">Chưa thể đánh giá gói</p><p>{clean(error or "Agent chưa hoàn tất.")}</p>'
    return f'''<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Quy trình agent · {clean(package)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#152c35; --muted:#4a6268; --paper:#f5f3ec; --line:#c7d0cb; --green:#176c58; --red:#a33d31; --amber:#805414; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--paper); color:var(--ink); font:16px/1.55 system-ui, sans-serif; }}
    ::selection {{ background:#b9d9c9; color:var(--ink); }}
    :focus-visible {{ outline:3px solid var(--green); outline-offset:4px; }}
    main {{ max-width:1120px; margin:auto; padding:clamp(24px,5vw,72px); }}
    header {{ border-bottom:2px solid var(--ink); padding-bottom:36px; }}
    h1 {{ font:700 clamp(2.5rem,6vw,5rem)/1.04 Georgia, serif; letter-spacing:-.025em; max-width:13ch; margin:0 0 22px; }}
    h2 {{ font:700 clamp(1.5rem,3vw,2rem)/1.2 Georgia, serif; margin:0 0 24px; }}
    h3 {{ font-size:1rem; margin:32px 0 8px; }}
    p {{ margin:0; max-width:70ch; }}
    .intro {{ color:var(--muted); max-width:62ch; }}
    .meta {{ display:flex; flex-wrap:wrap; gap:10px 28px; margin-top:30px; font-size:.91rem; }}
    .meta span {{ overflow-wrap:anywhere; }}
    .meta b {{ color:var(--ink); }}
    .layout {{ display:grid; grid-template-columns:minmax(0,1.35fr) minmax(280px,.85fr); gap:clamp(32px,6vw,88px); padding-top:48px; }}
    .section-head {{ display:flex; justify-content:space-between; gap:18px; align-items:baseline; }}
    .count {{ color:var(--muted); font-variant-numeric:tabular-nums; white-space:nowrap; }}
    .timeline {{ list-style:none; padding:0; margin:0; }}
    .event {{ display:grid; grid-template-columns:48px 1fr; gap:18px; border-top:1px solid var(--line); padding:17px 0 20px; }}
    .event:last-child {{ border-bottom:1px solid var(--line); }}
    .step {{ font:700 1rem/1.4 ui-monospace, monospace; font-variant-numeric:tabular-nums; color:var(--muted); }}
    .event-kind {{ font-weight:700; }}
    .event p {{ margin-top:3px; overflow-wrap:anywhere; }}
    .event.ok .event-kind {{ color:var(--green); }}
    .event.retry .event-kind {{ color:var(--amber); }}
    .event.error .event-kind {{ color:var(--red); }}
    .result {{ border-top:4px solid var(--green); padding-top:20px; align-self:start; }}
    .result.pending {{ border-color:var(--line); }}
    .result.bad {{ border-color:var(--red); }}
    .result h2 {{ margin-bottom:18px; }}
    .label {{ font-weight:700; font-size:1.15rem; margin-bottom:8px; }}
    .evidence {{ list-style:none; padding:0; margin:0; }}
    .evidence li {{ padding:14px 0; border-top:1px solid var(--line); }}
    .evidence span {{ display:block; color:var(--muted); font: .88rem ui-monospace, monospace; overflow-wrap:anywhere; }}
    .evidence p {{ margin-top:6px; }}
    footer {{ border-top:1px solid var(--line); margin-top:60px; padding-top:16px; color:var(--muted); font-size:.88rem; }}
    @media (max-width:760px) {{ .layout {{ grid-template-columns:1fr; }} .result {{ grid-row:1; }} }}
    @media print {{ body {{ background:white; }} main {{ max-width:none; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>Quy trình phân tích gói npm</h1>
    <p class="intro">Các bước dưới đây được ghi trong lúc agent chạy. Công cụ chỉ đọc file; không thực thi mã của gói.</p>
    <div class="meta"><span><b>Gói</b> <span id="package-name">{clean(package)}</span></span><span><b>Agent</b> {clean(variant)} / {clean(model)}</span><span><b>Trạng thái</b> <span id="run-status">{status}</span></span></div>
  </header>
  <div class="layout">
    <section aria-labelledby="flow-title"><div class="section-head"><h2 id="flow-title">Luồng hoạt động</h2><span id="step-count" class="count">{steps} bước</span></div><ol class="timeline">{timeline}</ol></section>
    <aside class="result {tone}" aria-labelledby="result-title"><h2 id="result-title">Kết quả</h2><div id="result-body">{conclusion}</div></aside>
  </div>
  <footer>Trace chỉ ghi lệnh đọc và trạng thái kiểm tra. Nội dung file, prompt và phản hồi thô của model không được lưu vào trang.</footer>
</main>
{LIVE_SCRIPT if live else ''}
</body>
</html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize a read-only npm agent run as HTML")
    parser.add_argument("package", help="path to an extracted package")
    parser.add_argument("variant", choices=("A-TLM", "A-SLM", "A-LLM"))
    parser.add_argument("--output", type=Path, default=Path("reports/agent-flow.html"))
    args = parser.parse_args()
    config = Path(__file__).resolve().parents[1] / "experiments" / "configs" / f"{args.variant}.yaml"
    values = dict(line.split(": ", 1) for line in config.read_text(encoding="utf-8").splitlines() if ": " in line)
    trace = []
    state = {"verdict": None, "error": "", "done": False}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                body = render(args.variant, values["model"], trace[:], state["verdict"], state["error"], live=True).encode("utf-8")
                mime = "text/html; charset=utf-8"
            elif self.path == "/state":
                body = json.dumps({"trace": trace[:], "verdict": state["verdict"].model_dump() if state["verdict"] else None,
                                   "error": state["error"], "running": not state["done"]}, ensure_ascii=False).encode("utf-8")
                mime = "application/json; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            pass

    def run_agent():
        try:
            state["verdict"], _ = analyze(args.package, values["model"], int(values["max_steps"]), trace=trace)
        except Exception as failure:
            state["error"] = f"{type(failure).__name__}: {failure}"
            trace.append({"step": max((event["step"] for event in trace), default=0),
                          "kind": "run", "status": "error", "detail": state["error"]})
        finally:
            try:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(render(args.variant, values["model"], trace, state["verdict"], state["error"]), encoding="utf-8")
                print(f"Báo cáo cuối: {args.output.resolve()}", flush=True)
            except OSError as failure:
                state["error"] = f"Không thể ghi báo cáo: {failure}"
            state["done"] = True

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        print(f"Theo dõi trực tiếp: http://127.0.0.1:{server.server_port}/", flush=True)
        print("Mở URL trên và nhấn Ctrl+C sau khi xem xong.", flush=True)
        Thread(target=run_agent, daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    if not state["done"]:
        raise SystemExit(130)
    if state["error"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
