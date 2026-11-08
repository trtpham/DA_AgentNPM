"""Show a real agent run as a self-contained, read-only dashboard."""

import argparse
import json
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from agent.run import analyze


EVENT_NAMES = {
    "manifest": "Đọc manifest", "model": "Gửi tới mô hình", "model_reply": "Mô hình phản hồi", "tool": "Gọi công cụ",
    "feedback": "Yêu cầu đọc thêm", "validation": "Kiểm tra đầu ra",
    "verdict": "Kết luận", "run": "Lỗi chạy",
}
STAGES = {"manifest": 0, "model": 1, "model_reply": 1, "tool": 1, "feedback": 1,
          "validation": 2, "verdict": 3, "run": 2}
STAGE_NAMES = ("Nhận diện gói", "Điều tra mã nguồn", "Kiểm chứng bằng chứng", "Ra quyết định")
LABELS = {"benign": "Lành tính", "suspicious": "Đáng ngờ", "malicious": "Độc hại"}
ACTIONS = {"approve": "Cho phép", "review": "Chuyển kiểm tra thủ công", "deny": "Từ chối"}


STYLE = """
:root{color-scheme:dark;--bg:#09111d;--surface:#111e2d;--surface-2:#172638;--ink:#f4f8f5;--muted:#b8cbd0;--line:#395165;--mint:#61e8c2;--amber:#ffd08a;--red:#ff8e83;font:17px/1.5 'Segoe UI',Arial,sans-serif}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;color:var(--ink);background:radial-gradient(1000px 500px at 100% -20%,#164451 0%,transparent 65%),var(--bg)}
::selection{background:var(--mint);color:var(--bg)}:focus-visible{outline:3px solid var(--amber);outline-offset:4px}button,select{font:inherit}button{cursor:pointer}button:disabled{cursor:not-allowed;opacity:.5}[hidden]{display:none!important}
.shell{max-width:1540px;margin:auto;padding:24px clamp(20px,4vw,64px) 40px}.masthead{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:0 0 24px;border-bottom:1px solid var(--line)}.brand{display:flex;align-items:center;gap:12px;font-weight:800;letter-spacing:.01em}.brand-mark{display:grid;grid-template-columns:repeat(3,4px);align-items:end;gap:4px;width:28px;height:27px;transform:skewX(-13deg)}.brand-mark i{display:block;background:var(--mint);height:55%}.brand-mark i:nth-child(2){height:100%}.brand-mark i:nth-child(3){height:72%}.brand small{font-weight:500;color:var(--muted)}.session-status{display:flex;align-items:center;gap:10px;font-weight:700}.status-dot{width:10px;height:10px;border-radius:50%;background:var(--mint);box-shadow:0 2px 10px #2bb99466}.live .status-dot{animation:beacon 1.7s ease-in-out infinite}.session-status.bad .status-dot{background:var(--red);animation:none}
.hero{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(260px,.6fr);gap:32px;align-items:end;padding:46px 0 40px}.hero h1{font:700 clamp(2.6rem,5.3vw,5.2rem)/1.04 Georgia,'Times New Roman',serif;letter-spacing:-.03em;max-width:16ch;margin:0 0 16px}.hero p{color:var(--muted);max-width:65ch;margin:0;font-size:1.05rem}.package-summary{padding:22px 0 0 24px;border-left:1px solid var(--line);min-width:0}.package-summary span{display:block;color:var(--muted);font-size:.85rem}.package-summary strong{display:block;overflow-wrap:anywhere;font:700 clamp(1.25rem,2vw,1.8rem)/1.2 ui-monospace,Consolas,monospace;margin:5px 0 22px}.package-summary p{font-size:.94rem}.package-summary b{color:var(--ink)}
.pipeline{padding:25px 28px 30px;background:var(--surface);border:1px solid var(--line);border-radius:16px}.pipeline-head,.section-head{display:flex;justify-content:space-between;align-items:baseline;gap:20px}.pipeline-head strong{font-size:1.1rem}.pipeline-head span,.count{color:var(--muted);font-variant-numeric:tabular-nums}.progress-track{height:3px;background:#355064;margin:24px 5px 16px;overflow:hidden}.progress-fill{display:block;width:100%;height:100%;background:var(--mint);transform:scaleX(0);transform-origin:left;transition:transform .55s cubic-bezier(.16,1,.3,1)}.stages{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;list-style:none;margin:0;padding:0}.stage{min-width:0;color:var(--muted)}.stage-index{display:block;width:34px;height:34px;border:1px solid var(--line);border-radius:50%;text-align:center;line-height:32px;font:700 .85rem/32px ui-monospace,Consolas,monospace;margin-bottom:10px}.stage strong{display:block;color:var(--muted);font-size:.98rem}.stage span:last-child{font-size:.83rem}.stage.is-done .stage-index{background:var(--mint);border-color:var(--mint);color:var(--bg)}.stage.is-current .stage-index{border-color:var(--mint);color:var(--mint);box-shadow:0 0 0 5px #61e8c218}.stage.is-current strong,.stage.is-done strong{color:var(--ink)}
.workbench{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(310px,.7fr);gap:clamp(24px,3vw,46px);margin-top:42px}.section-head h2,.result h2{font:700 clamp(1.55rem,2.5vw,2.15rem)/1.16 Georgia,serif;margin:0 0 20px}.section-head h2{margin-bottom:0}.section-head{margin-bottom:17px}.count{font-size:.88rem;white-space:nowrap}.activity{min-width:0}.current-action{position:relative;overflow:hidden;padding:20px 24px 21px;background:#173144;border:1px solid #3c6b73;border-radius:14px;margin-bottom:18px}.current-action:before{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--mint)}.current-action small{display:block;color:var(--mint);font-weight:800;letter-spacing:.11em;font-size:.72rem;margin-bottom:6px}.current-action strong{display:block;font-size:1.28rem}.current-action p{color:var(--muted);margin:3px 0 0;overflow-wrap:anywhere}.live .current-action:after{content:'';position:absolute;top:0;bottom:0;width:38%;left:-40%;background:linear-gradient(90deg,transparent,#83ffe616,transparent);animation:scan 3s linear infinite;pointer-events:none}.timeline{list-style:none;padding:0 7px 0 0;margin:0;max-height:570px;overflow:auto;scrollbar-color:#527485 var(--surface)}.event{position:relative;display:grid;grid-template-columns:46px 1fr;gap:14px;padding:0 0 21px;min-width:0}.event:before{content:'';position:absolute;left:20px;top:32px;bottom:0;width:1px;background:var(--line)}.event:last-child:before{display:none}.event-index{position:relative;z-index:1;width:42px;height:42px;border-radius:11px;background:var(--surface-2);border:1px solid var(--line);display:grid;place-items:center;font:700 .84rem ui-monospace,Consolas,monospace;color:var(--muted)}.event-body{border-bottom:1px solid var(--line);padding:4px 0 17px;min-width:0}.event-kind{display:inline-block;font-weight:800}.event p{color:var(--muted);margin:4px 0 0;overflow-wrap:anywhere}.event.ok .event-kind{color:var(--mint)}.event.retry .event-kind{color:var(--amber)}.event.error .event-kind{color:var(--red)}.event.is-active .event-index{color:var(--bg);background:var(--mint);border-color:var(--mint)}.event.new{animation:event-arrive .43s cubic-bezier(.16,1,.3,1) both}.empty{color:var(--muted);padding:25px 0}
.transport{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:0 0 16px}.transport button,.transport select{background:var(--surface-2);color:var(--ink);border:1px solid var(--line);border-radius:9px;min-height:38px;padding:6px 12px}.transport button:hover,.transport select:hover{border-color:var(--mint)}.transport .primary{background:var(--mint);border-color:var(--mint);color:var(--bg);font-weight:800}.transport .primary:hover{background:#a2ffdc}.transport .replay-position{margin-left:auto;color:var(--muted);font:700 .83rem ui-monospace,Consolas,monospace}
.result{align-self:start;position:sticky;top:22px;background:var(--surface);padding:27px;border:1px solid var(--line);border-radius:16px;min-width:0}.result:before{content:'';display:block;width:58px;height:4px;background:var(--mint);margin-bottom:22px}.result.pending:before{background:var(--amber)}.result.bad:before{background:var(--red)}.result h2{margin-bottom:18px}.result .result-note{color:var(--muted);font-size:.88rem;margin:0 0 18px}.outcome{font:700 clamp(1.55rem,2.4vw,2.15rem)/1.15 Georgia,serif;margin:0 0 10px;overflow-wrap:anywhere}.outcome.benign{color:var(--mint)}.outcome.suspicious{color:var(--amber)}.outcome.malicious{color:var(--red)}.outcome-meta{margin:0 0 20px;color:var(--muted)}.outcome-meta strong{color:var(--ink)}.result-description{margin:0 0 20px;overflow-wrap:anywhere}.result h3{font-size:1rem;margin:26px 0 11px}.evidence{list-style:none;margin:0;padding:0}.evidence li{padding:13px 0;border-top:1px solid var(--line)}.evidence strong{display:block}.evidence span{display:block;color:var(--mint);font:.87rem ui-monospace,Consolas,monospace;overflow-wrap:anywhere;margin-top:3px}.evidence p{color:var(--muted);margin:6px 0 0;overflow-wrap:anywhere}.pending-copy{font-size:1.12rem;margin:0 0 9px;font-weight:800}.error-copy{color:var(--red);overflow-wrap:anywhere}.footnote{border-top:1px solid var(--line);padding-top:18px;margin-top:56px;color:var(--muted);font-size:.87rem}
@keyframes beacon{50%{box-shadow:0 0 0 9px #61e8c222}}@keyframes scan{to{left:105%}}@keyframes event-arrive{from{opacity:.1;transform:translateY(13px);clip-path:inset(0 0 80% 0)}to{opacity:1;transform:none;clip-path:inset(0)}}
@keyframes step-reveal{from{opacity:.35;clip-path:inset(0 100% 0 0)}to{opacity:1;clip-path:inset(0)}}@keyframes stage-focus{from{box-shadow:0 0 0 0 #61e8c255}to{box-shadow:0 0 0 10px #61e8c200}}@keyframes decision-reveal{from{transform:scaleX(0)}to{transform:scaleX(1)}}
.replaying .event.is-active .event-body{animation:step-reveal .34s cubic-bezier(.16,1,.3,1) both}.stage.is-current .stage-index{animation:stage-focus .42s ease-out}.result.good:before,.result.bad:before{transform-origin:left;animation:decision-reveal .55s cubic-bezier(.16,1,.3,1) both}
.hero h1,.section-head h2,.result h2,.outcome{font-family:'Segoe UI',Arial,sans-serif;line-height:1.16}
.paused-motion .status-dot,.paused-motion .current-action:after{animation-play-state:paused}
.step-inspector{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:21px;margin:-2px 0 24px;min-width:0}.step-inspector h3{margin:0 0 15px;font-size:1.12rem}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 24px}.detail-row:first-child{grid-column:1/-1}.detail-row span{display:block;color:var(--mint);font-size:.8rem;font-weight:800;margin-bottom:4px}.detail-row p{margin:0;overflow-wrap:anywhere}.detail-empty{color:var(--muted);margin:0}.source-block{margin-top:20px;padding-top:17px;border-top:1px solid var(--line);min-width:0}.source-title{display:inline-block;font:700 .93rem ui-monospace,Consolas,monospace;overflow-wrap:anywhere;margin-right:12px}.untrusted-tag{display:inline-block;color:var(--amber);font-size:.78rem;font-weight:800}.source-block pre{max-height:320px;overflow:auto;margin:12px 0 0;padding:16px;background:#07131f;border:1px solid #355064;border-radius:10px;color:#e6f6f1;font:14px/1.6 ui-monospace,Consolas,monospace;white-space:pre;tab-size:2;scrollbar-color:#527485 #07131f}.source-note{color:var(--amber);font-size:.85rem;margin:9px 0 0}.more-code{margin-top:10px;padding:7px 12px;border:1px solid var(--mint);background:transparent;color:var(--mint);border-radius:8px;font-weight:700}.more-code:hover{background:#214448}
.model-claim{color:var(--muted);margin:11px 0 0;overflow-wrap:anywhere}
@media(max-width:980px){.hero,.workbench{grid-template-columns:1fr}.package-summary{border-left:0;border-top:1px solid var(--line);padding:20px 0 0}.package-summary strong{margin-bottom:9px}.result{position:static}.timeline{max-height:480px}}@media(max-width:620px){.shell{padding:16px 18px 30px}.brand small{display:none}.hero{padding:30px 0}.hero h1{font-size:2.6rem}.pipeline{padding:20px}.stages{grid-template-columns:repeat(2,1fr);gap:20px}.stage span:last-child{display:block}.progress-track{margin-top:17px}.workbench{margin-top:31px}.result{padding:22px}.transport .replay-position{width:100%;margin-left:0}}@media print{body{background:white;color:#10202c}.pipeline,.result,.current-action{background:white;color:#10202c}.event p,.result .result-note,.evidence p{color:#334b53}.timeline{max-height:none;overflow:visible}.transport{display:none!important}.stage strong,.event-kind{color:#10202c!important}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}.live .status-dot,.live .current-action:after,.event.new,.replaying .event.is-active .event-body,.stage.is-current .stage-index,.result.good:before,.result.bad:before{animation:none}.progress-fill{transition:transform .15s ease}}
@media(max-width:620px){.detail-grid{grid-template-columns:1fr}.detail-row:first-child{grid-column:auto}.step-inspector{padding:18px}.source-title,.untrusted-tag{display:block}.source-block pre{font-size:12px}}
"""


SCRIPT = """<script>
(() => {
  const timeline = document.querySelector('.timeline');
  const inspector = document.getElementById('step-inspector');
  const result = document.querySelector('.result');
  const resultBody = document.getElementById('result-body');
  const status = document.getElementById('run-status');
  const statusWrap = document.querySelector('.session-status');
  const stages = [...document.querySelectorAll('.stage')];
  const fill = document.querySelector('.progress-fill');
  const phase = document.getElementById('phase-label');
  const count = document.getElementById('step-count');
  const action = document.getElementById('current-action-text');
  const actionDetail = document.getElementById('current-action-detail');
  const transport = document.getElementById('transport');
  const playButton = document.getElementById('play');
  const position = document.getElementById('replay-position');
  const speed = document.getElementById('speed');
  const live = document.body.classList.contains('live');
  const stageNames = ['Nhận diện gói', 'Điều tra mã nguồn', 'Kiểm chứng bằng chứng', 'Ra quyết định'];
  const kindNames = {manifest:'Đọc manifest',model:'Gửi tới mô hình',model_reply:'Mô hình phản hồi',tool:'Gọi công cụ',feedback:'Yêu cầu đọc thêm',validation:'Kiểm tra đầu ra',verdict:'Kết luận',run:'Lỗi chạy'};
  const kindStage = {manifest:0,model:1,model_reply:1,tool:1,feedback:1,validation:2,verdict:3,run:2};
  const labels = {benign:'Lành tính',suspicious:'Đáng ngờ',malicious:'Độc hại'};
  const actions = {approve:'Cho phép',review:'Chuyển kiểm tra thủ công',deny:'Từ chối'};
  const events = [...timeline.querySelectorAll('.event')];
  let seen = events.length, running = live && status.textContent === 'Đang phân tích';
  let savedResult = resultBody.cloneNode(true), finalTone = result.className;
  let replaying = false, visible = events.length, timer = null, inspected = -1;

  function node(tag, value, parent, className) {
    const item = document.createElement(tag);
    item.textContent = value == null ? '' : String(value);
    if (className) item.className = className;
    parent.append(item);
    return item;
  }
  function addDetails(event, item) {
    const extra = node('div', '', item, 'event-extra');
    extra.hidden = true;
    const grid = node('div', '', extra, 'detail-grid');
    for (const [label, value] of [['Mục tiêu', event.what], ['Cách agent làm', event.how], ['Kết quả quan sát', event.found]]) {
      if (!value) continue;
      const row = node('div', '', grid, 'detail-row');
      node('span', label, row);
      node('p', value, row);
    }
    if (!grid.children.length) node('p', 'Trace này chỉ có tóm tắt bước.', extra, 'detail-empty');
    for (const source of event.sources || []) {
      const block = node('div', '', extra, 'source-block');
      const lines = String(source.content || '').split('\\n');
      const start = Number(source.start) || 1;
      node('strong', String(source.file) + ':' + start + '–' + (start + lines.length - 1), block, 'source-title');
      node('span', 'Dữ liệu mã gói không tin cậy', block, 'untrusted-tag');
      node('pre', lines.map((line, index) => String(start + index).padStart(4) + ' │ ' + line).join('\\n'), block);
      if (source.claim) node('p', 'Nhận định của mô hình: ' + (source.behavior ? source.behavior + '. ' : '') + source.claim, block, 'model-claim');
      if (source.truncated) node('p', 'Đoạn hiển thị dừng ở 8.000 ký tự; file có thể còn nội dung phía sau.', block, 'source-note');
    }
  }
  function wirePreview(pre) {
    const full = pre.textContent;
    if (full.length <= 2000) return;
    const boundary = full.lastIndexOf('\\n', 2000);
    const short = full.slice(0, boundary > 0 ? boundary : 2000) + '\\n…';
    pre.textContent = short;
    const button = node('button', 'Hiện thêm đoạn mã', pre.parentElement, 'more-code');
    button.type = 'button';
    button.addEventListener('click', () => {
      const expanded = pre.textContent === full;
      pre.textContent = expanded ? short : full;
      button.textContent = expanded ? 'Hiện thêm đoạn mã' : 'Thu gọn đoạn mã';
    });
  }
  function stageOf(item) {
    for (let index = 0; index < 4; index++) if (item.classList.contains('stage-' + index)) return index;
    return 0;
  }
  function showProgress(number) {
    const current = events[number - 1];
    const stage = current ? stageOf(current) : -1;
    stages.forEach((item, index) => {
      item.classList.toggle('is-done', index < stage);
      item.classList.toggle('is-current', index === stage);
    });
    fill.style.transform = 'scaleX(' + (stage < 0 ? 0 : (stage + 1) / 4) + ')';
    phase.textContent = stage < 0 ? 'Chờ bắt đầu' : 'Giai đoạn ' + (stage + 1) + '/4 · ' + stageNames[stage];
    count.textContent = current ? 'Lượt ' + current.querySelector('.event-index').textContent + ' · ' + number + ' sự kiện' : '0 sự kiện';
    events.forEach((item, index) => item.classList.toggle('is-active', index === number - 1));
    action.textContent = current ? current.querySelector('.event-kind').textContent : 'Chờ agent đọc manifest';
    actionDetail.textContent = current ? current.querySelector('p').textContent : 'Các bước sẽ xuất hiện ngay khi agent bắt đầu.';
    if (number !== inspected) {
      inspector.replaceChildren();
      const extra = current?.querySelector('.event-extra')?.cloneNode(true);
      if (extra) {
        extra.hidden = false;
        inspector.append(extra);
        inspector.querySelectorAll('pre').forEach(wirePreview);
      } else node('p', 'Chi tiết xuất hiện khi agent tạo bước đầu tiên.', inspector, 'detail-empty');
      inspected = number;
    }
    position.textContent = number + ' / ' + events.length + ' sự kiện';
  }
  function appendEvent(event) {
    timeline.querySelector('.empty')?.remove();
    const statusName = ['ok','retry','error','info'].includes(event.status) ? event.status : 'info';
    const stage = Object.hasOwn(kindStage, event.kind) ? kindStage[event.kind] : 1;
    const item = document.createElement('li');
    item.className = 'event ' + statusName + ' stage-' + stage + ' new';
    node('span', String(event.step).padStart(2, '0'), item, 'event-index');
    const body = node('div', '', item, 'event-body');
    node('span', kindNames[event.kind] || 'Sự kiện', body, 'event-kind');
    node('p', event.detail, body);
    addDetails(event, item);
    timeline.append(item);
    events.push(item);
  }
  function setResult(verdict, error, isRunning) {
    resultBody.replaceChildren();
    result.className = 'result ' + (verdict ? 'good' : isRunning ? 'pending' : 'bad');
    if (verdict) {
      node('p', (labels[verdict.label] || verdict.label) + ' · ' + verdict.label, resultBody, 'outcome ' + (['benign','suspicious','malicious'].includes(verdict.label) ? verdict.label : ''));
      const meta = node('p', '', resultBody, 'outcome-meta');
      node('strong', actions[verdict.action] || verdict.action, meta);
      node('span', ' · Mô hình tự đánh giá ' + Math.round(verdict.confidence * 100) + '% tin cậy', meta);
      node('p', verdict.description, resultBody, 'result-description');
      node('h3', 'Bằng chứng agent đã nêu', resultBody);
      const list = node('ul', '', resultBody, 'evidence');
      for (const behavior of verdict.behaviors || []) {
        const item = node('li', '', list);
        node('strong', behavior.behavior, item);
        node('span', behavior.evidence.file + ':' + behavior.evidence.lines, item);
        node('p', behavior.analysis, item);
      }
      if (!list.children.length) node('li', 'Model không liệt kê hành vi cụ thể.', list);
    } else {
      node('p', isRunning ? 'Đang chờ kết luận hợp lệ' : 'Chưa có kết luận hợp lệ', resultBody, 'pending-copy');
      node('p', isRunning ? 'Agent đang đọc dữ liệu và kiểm tra bằng chứng.' : error || 'Agent dừng trước khi tạo verdict.', resultBody, error ? 'error-copy' : 'result-description');
    }
    savedResult = resultBody.cloneNode(true);
    finalTone = result.className;
  }
  function paintReplay() {
    document.body.classList.add('replaying');
    events.forEach((item, index) => { item.hidden = index >= visible; });
    showProgress(visible);
    if (visible === events.length && !running) {
      resultBody.replaceChildren(...[...savedResult.childNodes].map(item => item.cloneNode(true)));
      result.className = finalTone;
    } else {
      resultBody.replaceChildren();
      node('p', 'Quyết định xuất hiện sau bước kiểm chứng.', resultBody, 'pending-copy');
      result.className = 'result pending';
    }
    if (visible) timeline.scrollTop = timeline.scrollHeight;
  }
  function pause() {
    clearInterval(timer); timer = null; playButton.textContent = 'Tiếp tục';
  }
  function play() {
    if (!replaying) { replaying = true; visible = 0; paintReplay(); }
    if (visible >= events.length) { visible = 0; paintReplay(); }
    if (timer) { pause(); return; }
    playButton.textContent = 'Tạm dừng';
    timer = setInterval(() => {
      visible = Math.min(events.length, visible + 1);
      paintReplay();
      if (visible === events.length) pause();
    }, 900 / Number(speed.value));
  }
  function seek(delta) {
    pause();
    if (!replaying) { replaying = true; visible = events.length; }
    visible = Math.max(0, Math.min(events.length, visible + delta));
    paintReplay();
  }
  playButton.addEventListener('click', play);
  document.getElementById('previous').addEventListener('click', () => seek(-1));
  document.getElementById('next').addEventListener('click', () => seek(1));
  speed.addEventListener('change', () => { if (timer) { pause(); play(); } });
  document.addEventListener('keydown', event => {
    if (transport.hidden || ['INPUT','SELECT','BUTTON'].includes(document.activeElement.tagName)) return;
    if (event.key === 'ArrowLeft') { event.preventDefault(); seek(-1); }
    if (event.key === 'ArrowRight') { event.preventDefault(); seek(1); }
  });
  document.addEventListener('visibilitychange', () => document.body.classList.toggle('paused-motion', document.hidden));
  showProgress(events.length);
  if (!live) {
    transport.hidden = false;
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches && events.length) play();
  }
  async function refresh() {
    try {
      const response = await fetch('/state', {cache:'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const state = await response.json();
      for (const event of state.trace.slice(seen)) appendEvent(event);
      seen = state.trace.length;
      const manifest = state.trace.find(event => event.kind === 'manifest');
      if (manifest) {
        document.getElementById('package-name').textContent = manifest.detail;
        document.title = 'Quy trình agent · ' + manifest.detail;
      }
      running = state.running;
      status.textContent = running ? 'Đang phân tích' : state.verdict ? 'Hoàn tất' : 'Dừng chưa có verdict';
      statusWrap.classList.toggle('bad', !running && !state.verdict);
      document.body.classList.toggle('live', running);
      if (!replaying) {
        showProgress(events.length);
        if (events.length > 0) timeline.scrollTop = timeline.scrollHeight;
        setResult(state.verdict, state.error, running);
      }
      if (running) setTimeout(refresh, 400);
      else transport.hidden = false;
    } catch (failure) {
      status.textContent = 'Mất kết nối';
      action.textContent = 'Không nhận được cập nhật từ agent';
      actionDetail.textContent = 'Kiểm tra terminal; trang sẽ tự thử kết nối lại.';
      setTimeout(refresh, 1500);
    }
  }
  if (live) refresh();
})();
</script>"""


def render(variant: str, model: str, trace: list[dict], verdict=None, error: str = "", live: bool = False) -> str:
    clean = lambda value: escape(str(value), quote=True)
    def details(event):
        rows = "".join(
            f'<div class="detail-row"><span>{label}</span><p>{clean(event[key])}</p></div>'
            for label, key in (("Mục tiêu", "what"), ("Cách agent làm", "how"), ("Kết quả quan sát", "found"))
            if event.get(key)
        )
        sources = ""
        for source in event.get("sources", []):
            content = source["content"]
            start = source["start"]
            numbered = "\n".join(f"{start + index:>4} │ {line}" for index, line in enumerate(content.split("\n")))
            end = start + len(content.split("\n")) - 1
            sources += (f'<div class="source-block"><strong class="source-title">{clean(source["file"])}:{start}–{end}</strong>'
                        '<span class="untrusted-tag">Dữ liệu mã gói không tin cậy</span>'
                        f'<pre>{clean(numbered)}</pre>'
                        + (f'<p class="model-claim">Nhận định của mô hình: {clean(source.get("behavior", ""))}. {clean(source["claim"])}</p>'
                           if source.get("claim") else '')
                        + ('<p class="source-note">Đoạn hiển thị dừng ở 8.000 ký tự; file có thể còn nội dung phía sau.</p>'
                           if source.get("truncated") else '') + '</div>')
        return ('<div class="event-extra" hidden><div class="detail-grid">'
                + (rows or '<p class="detail-empty">Trace này chỉ có tóm tắt bước.</p>')
                + '</div>' + sources + '</div>')
    package = next((event["detail"] for event in trace if event["kind"] == "manifest"), "Chưa đọc manifest")
    last = trace[-1] if trace else None
    stage = STAGES.get(last["kind"], 1) if last else -1
    status = "Đang phân tích" if live and not verdict and not error else "Hoàn tất" if verdict else "Dừng chưa có verdict"
    tone = "pending" if live and not verdict and not error else "good" if verdict else "bad"
    timeline = "\n".join(
        f'<li class="event {event["status"] if event["status"] in {"ok", "retry", "error", "info"} else "info"} stage-{STAGES.get(event["kind"], 1)}">'
        f'<span class="event-index">{event["step"]:02d}</span><div class="event-body">'
        f'<span class="event-kind">{clean(EVENT_NAMES.get(event["kind"], "Sự kiện"))}</span>'
        f'<p>{clean(event["detail"])}</p></div>{details(event)}</li>' for event in trace
    ) or '<li class="empty">Agent chưa tạo bước nào.</li>'
    if verdict:
        evidence = "\n".join(
            f'<li><strong>{clean(item.behavior)}</strong><span>{clean(item.evidence.file)}:{clean(item.evidence.lines)}</span>'
            f'<p>{clean(item.analysis)}</p></li>' for item in verdict.behaviors
        ) or '<li>Model không liệt kê hành vi cụ thể.</li>'
        result_content = (
            f'<p class="outcome {clean(verdict.label)}">{clean(LABELS.get(verdict.label, verdict.label))} · {clean(verdict.label)}</p>'
            f'<p class="outcome-meta"><strong>{clean(ACTIONS.get(verdict.action, verdict.action))}</strong> · '
            f'Mô hình tự đánh giá {verdict.confidence:.0%} tin cậy</p>'
            f'<p class="result-description">{clean(verdict.description)}</p>'
            f'<h3>Bằng chứng agent đã nêu</h3><ul class="evidence">{evidence}</ul>'
        )
    else:
        message = error or ("Agent đang đọc dữ liệu và kiểm tra bằng chứng." if live else "Agent dừng trước khi tạo verdict.")
        result_content = (
            f'<p class="pending-copy">{"Đang chờ kết luận hợp lệ" if live and not error else "Chưa có kết luận hợp lệ"}</p>'
            f'<p class="{"error-copy" if error else "result-description"}">'
            f'{clean(message)}</p>'
        )
    stages = "".join(
        f'<li class="stage {"is-done" if index < stage else "is-current" if index == stage else ""}">'
        f'<span class="stage-index">{index + 1}</span><strong>{name}</strong><span>{hint}</span></li>'
        for index, (name, hint) in enumerate(zip(STAGE_NAMES, (
            "Tên, phiên bản và script", "Model chọn file để đọc", "Schema và file:dòng", "Nhãn cùng hành động",
        )))
    )
    current_name = EVENT_NAMES.get(last["kind"], "Sự kiện") if last else "Chờ agent đọc manifest"
    current_detail = last["detail"] if last else "Các bước sẽ xuất hiện ngay khi agent bắt đầu."
    phase = f"Giai đoạn {stage + 1}/4 · {STAGE_NAMES[stage]}" if stage >= 0 else "Chờ bắt đầu"
    return f'''<!doctype html>
<html lang="vi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Quy trình agent · {clean(package)}</title><style>{STYLE}</style></head>
<body class="{'live' if live and not verdict and not error else ''}">
<main class="shell">
  <header class="masthead">
    <div class="brand"><span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span><span>NPM AGENT <small>/ phòng quan sát</small></span></div>
    <div class="session-status {'bad' if tone == 'bad' else ''}"><span class="status-dot" aria-hidden="true"></span><span id="run-status" aria-live="polite">{status}</span></div>
  </header>
  <section class="hero" aria-labelledby="page-title">
    <div><h1 id="page-title">Theo dấu một lượt kiểm tra gói npm.</h1><p>Agent đọc manifest, dùng mô hình để chọn file cần xem, kiểm chứng bằng chứng rồi mới đưa ra nhãn và hành động.</p></div>
    <div class="package-summary"><span>GÓI ĐANG KIỂM TRA</span><strong id="package-name">{clean(package)}</strong><p><b>Agent:</b> {clean(variant)} &nbsp; <b>Mô hình:</b> {clean(model)}</p></div>
  </section>
  <section class="pipeline" aria-label="Bốn giai đoạn kiểm tra">
    <div class="pipeline-head"><strong id="phase-label" aria-live="polite">{phase}</strong><span>Quy trình 4 giai đoạn</span></div>
    <div class="progress-track" aria-hidden="true"><span class="progress-fill"></span></div>
    <ol class="stages">{stages}</ol>
  </section>
  <div class="workbench">
    <section class="activity" aria-labelledby="flow-title">
      <div class="section-head"><h2 id="flow-title">Nhật ký điều tra</h2><span id="step-count" class="count">{len(trace)} sự kiện</span></div>
      <div class="transport" id="transport" {'hidden' if live and not verdict and not error else ''} aria-label="Điều khiển phát lại">
        <button type="button" id="previous">Bước trước</button><button type="button" class="primary" id="play">Phát lại</button><button type="button" id="next">Bước tiếp</button>
        <label for="speed">Tốc độ</label><select id="speed"><option value="1">1×</option><option value="2">2×</option><option value="4">4×</option></select><span id="replay-position" class="replay-position"></span>
      </div>
<div class="current-action" aria-live="polite"><small>BƯỚC ĐANG XEM</small><strong id="current-action-text">{clean(current_name)}</strong><p id="current-action-detail">{clean(current_detail)}</p></div>
<section class="step-inspector" id="step-inspector" aria-label="Chi tiết bước đang xem"><h3>Agent làm gì ở bước này?</h3><p class="detail-empty">Chi tiết xuất hiện khi agent tạo bước đầu tiên.</p></section>
      <ol class="timeline">{timeline}</ol>
    </section>
    <aside class="result {tone}" aria-labelledby="result-title"><h2 id="result-title">Quyết định</h2><p class="result-note">Kết luận của agent dựa trên các file đã đọc; chưa phải nhãn dữ liệu chuẩn.</p><div id="result-body">{result_content}</div></aside>
  </div>
<footer class="footnote">Dashboard chỉ đọc. Đoạn mã đã đọc được hiển thị cục bộ như dữ liệu không tin cậy; công cụ không thực thi mã npm. Kết luận vẫn cần người kiểm tra.</footer>
</main>{SCRIPT}</body></html>'''


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
