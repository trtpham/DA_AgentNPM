// Read-only replay/live viewer. Trace content is untrusted: it only ever reaches the page through textContent.
'use strict';

const LABELS = {benign: 'Lành tính', suspicious: 'Đáng ngờ', malicious: 'Độc hại'};
const ACTIONS = {approve: 'Cho phép', review: 'Chuyển kiểm tra thủ công', deny: 'Từ chối'};
const STATUS = {running: 'Đang chạy', done: 'Hoàn tất', error: 'Hết bước'};
const ERRORS = {
  json_invalid: 'JSON verdict không hợp schema', invalid_verdict: 'Verdict bị từ chối',
  truncated_output: 'Đầu ra mô hình bị cắt', repeated_invalid: 'Mô hình lặp cùng một verdict sai',
  bad_tool_call: 'Gọi công cụ không hợp lệ', model_error: 'Lỗi gọi mô hình', timeout: 'Hết thời gian chờ mô hình',
  manifest_error: 'Không đọc được manifest', invalid_script: 'Script cài đặt không phân tích được',
  decision_log: 'Không ghi được nhật ký quyết định', normalized_output: 'Đã chuẩn hóa định dạng đầu ra',
};
const POLL_MS = 1000;

const $ = (id) => document.getElementById(id);
const state = {run: null, pkg: null, events: [], cursor: -1, timer: null, poll: null, live: false};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = String(text);
  return node;
}

function short(value, limit = 400) {
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  return text && text.length > limit ? text.slice(0, limit) + '…' : (text || '');
}

async function getJson(url) {
  const response = await fetch(url, {cache: 'no-store'});
  if (!response.ok) throw new Error('HTTP ' + response.status);
  return response.json();
}

function setStatus(text, bad = false) {
  $('run-status').textContent = text;
  $('session-status').classList.toggle('bad', bad);
  document.body.classList.toggle('live', state.live && !bad);
}

// Older traces have no rule field.
function ruleText(decision) {
  return `${decision.rule ? ` · luật ${decision.rule}` : ''}${decision.dry_run ? ' · dry-run' : ''}`;
}

// One event -> {name, detail, tone, preview}
function describe(event) {
  switch (event.type) {
    case 'run_start':
      return {name: 'Bắt đầu phân tích', detail: `Mô hình ${event.model ?? '?'} · tối đa ${event.max_steps ?? '?'} bước`, tone: 'info'};
    case 'thought':
      return {name: 'Mô hình ghi chú', detail: '', tone: 'info', preview: event.text, previewLabel: 'Lời mô hình — không tin cậy'};
    case 'tool_call':
      return {name: `Gọi công cụ ${event.tool ?? ''}`, detail: short(event.args ?? {}), tone: 'info'};
    case 'tool_result':
      return {name: `Kết quả ${event.tool ?? ''}`, tone: event.ok ? 'ok' : 'error',
        detail: `${event.ok ? 'Thành công' : 'Lỗi'} · ${event.summary ?? ''}${event.duration_ms != null ? ` · ${event.duration_ms} ms` : ''}`,
        preview: event.untrusted ? event.data_preview : null, previewLabel: 'Dữ liệu mã gói không tin cậy'};
    case 'verdict': {
      const verdict = event.verdict || {};
      return event.valid
        ? {name: 'Verdict hợp lệ', detail: `${LABELS[verdict.label] ?? verdict.label} · đề xuất ${ACTIONS[verdict.action] ?? verdict.action}`, tone: 'ok'}
        : {name: 'Verdict bị từ chối', detail: short((event.validation_errors || []).join(' | ')), tone: 'retry'};
    }
    case 'decision':
      return {name: 'Quyết định cuối', tone: 'ok',
        detail: `${LABELS[event.final_label] ?? event.final_label} · ${ACTIONS[event.final_action] ?? event.final_action}${ruleText(event)}`};
    case 'error':
      return {name: ERRORS[event.kind] ?? `Lỗi ${event.kind ?? ''}`, detail: short(event.message), tone: 'error'};
    case 'limit':
      return {name: 'Hết giới hạn bước', detail: 'Agent dừng và chuyển sang kiểm tra thủ công.', tone: 'error'};
    case 'run_end':
      return {name: 'Kết thúc', detail: `${event.steps ?? '?'} bước · ${event.elapsed_s ?? '?'} giây`, tone: 'ok'};
    default:
      return {name: 'Sự kiện khác', detail: short(event.type), tone: 'info'};
  }
}

function eventItem(event, index) {
  const info = describe(event);
  const item = el('li', `event ${['ok', 'retry', 'error'].includes(info.tone) ? info.tone : 'info'}`);
  item.append(el('span', 'event-index', String(index + 1).padStart(2, '0')));
  const body = el('div', 'event-body');
  body.append(el('span', 'event-kind', info.name));
  if (info.detail) body.append(el('p', null, info.detail));
  if (info.preview) {
    const block = el('div', 'source-block');
    block.append(el('span', 'untrusted-tag', info.previewLabel), el('pre', null, info.preview));
    body.append(block);
  }
  item.append(body);
  return item;
}

function renderResult() {
  const shown = state.events.slice(0, state.cursor + 1);
  const decision = [...shown].reverse().find((event) => event.type === 'decision');
  const verdict = [...shown].reverse().find((event) => event.type === 'verdict' && event.valid);
  const result = $('result');
  const body = $('result-body');
  body.replaceChildren();
  if (!decision) {
    result.className = 'result pending';
    body.append(el('p', 'pending-copy', state.live ? 'Đang chờ quyết định' : 'Chưa có quyết định'));
    return;
  }
  result.className = `result ${decision.final_action === 'approve' ? 'good' : decision.final_label === 'benign' ? 'pending' : 'bad'}`;
  const label = ['benign', 'suspicious', 'malicious'].includes(decision.final_label) ? decision.final_label : '';
  body.append(el('p', `outcome ${label}`, `${LABELS[decision.final_label] ?? decision.final_label} · ${decision.final_label}`));
  const meta = el('p', 'outcome-meta');
  meta.append(el('strong', null, ACTIONS[decision.final_action] ?? decision.final_action),
    document.createTextNode(ruleText(decision)));
  body.append(meta);
  for (const reason of decision.reasons || []) body.append(el('p', 'result-description', reason));
  if (verdict && verdict.verdict) {
    const proposal = verdict.verdict;
    body.append(el('h3', null, 'Mô hình đề xuất'));
    body.append(el('p', 'result-description',
      `${LABELS[proposal.label] ?? proposal.label} · ${ACTIONS[proposal.action] ?? proposal.action} · tin cậy ${Math.round((proposal.confidence ?? 0) * 100)}%`));
    if (proposal.description) body.append(el('p', 'result-description', proposal.description));
    body.append(el('h3', null, 'Bằng chứng agent đã nêu'));
    const list = el('ul', 'evidence');
    for (const behavior of proposal.behaviors || []) {
      const item = el('li');
      item.append(el('strong', null, behavior.behavior),
        el('span', null, `${behavior.evidence?.file ?? '?'}:${behavior.evidence?.lines ?? '?'}`),
        el('p', null, behavior.analysis));
      list.append(item);
    }
    if (!list.childElementCount) list.append(el('li', 'empty', 'Không có hành vi nào được nêu.'));
    body.append(list);
  } else if (decision.rule === 'R2') {
    body.append(el('p', 'error-copy', 'Không có verdict hợp lệ; agent dùng phương án an toàn.'));
  }
}

function render() {
  const items = $('timeline').children;
  for (let index = 0; index < items.length; index += 1) {
    items[index].classList.toggle('is-future', index > state.cursor);
    items[index].classList.toggle('is-active', index === state.cursor);
  }
  const current = state.events[state.cursor];
  const info = current ? describe(current) : null;
  $('current-action-text').textContent = info ? info.name : (state.pkg ? 'Chưa có sự kiện' : 'Chưa chọn gói');
  $('current-action-detail').textContent = info ? (info.detail || '') : 'Chọn một run và một gói để xem lại từng bước của agent.';
  $('step-count').textContent = `${state.events.length} sự kiện`;
  $('replay-position').textContent = `${state.cursor + 1} / ${state.events.length}`;
  $('previous').disabled = state.cursor <= 0;
  $('next').disabled = state.cursor >= state.events.length - 1;
  $('play').disabled = state.events.length === 0;
  renderResult();
  if (items[state.cursor] && (state.timer || state.live)) items[state.cursor].scrollIntoView({block: 'nearest'});
}

function append(events) {
  const follow = state.cursor === state.events.length - 1;
  for (const event of events) {
    $('timeline').append(eventItem(event, state.events.length));
    state.events.push(event);
  }
  if (follow) state.cursor = state.events.length - 1;
}

function stopReplay() {
  clearInterval(state.timer);
  state.timer = null;
  $('play').textContent = 'Phát lại';
}

function startReplay() {
  if (state.cursor >= state.events.length - 1) state.cursor = -1;
  $('play').textContent = 'Tạm dừng';
  state.timer = setInterval(() => {
    if (state.cursor >= state.events.length - 1) { stopReplay(); render(); return; }
    state.cursor += 1;
    render();
  }, 900 / Number($('speed').value));
  state.cursor += 1;
  render();
}

function stopPolling() {
  clearTimeout(state.poll);
  state.poll = null;
}

async function poll(token) {
  try {
    const after = state.events.length ? state.events[state.events.length - 1].seq : -1;
    const fresh = await getJson(`/api/trace?run=${encodeURIComponent(state.run)}&pkg=${encodeURIComponent(state.pkg)}&after=${after}`);
    if (token !== state.pkg) return;
    append(fresh);
    state.live = !state.events.some((event) => event.type === 'run_end');
    setStatus(state.live ? 'Đang phân tích' : 'Hoàn tất');
    render();
    if (state.live) state.poll = setTimeout(() => poll(token), POLL_MS);
    else loadPackages(false);
  } catch (error) {
    if (token !== state.pkg) return;
    setStatus('Mất kết nối', true);
    state.poll = setTimeout(() => poll(token), POLL_MS * 3);
  }
}

function selectPackage(pkg) {
  stopReplay();
  stopPolling();
  state.pkg = pkg;
  state.events = [];
  state.cursor = -1;
  state.live = true;
  $('timeline').replaceChildren();
  for (const button of document.querySelectorAll('.package')) {
    button.setAttribute('aria-current', String(button.dataset.pkg === pkg));
  }
  history.replaceState(null, '', `#run=${encodeURIComponent(state.run)}&pkg=${encodeURIComponent(pkg)}`);
  render();
  poll(pkg);
}

async function loadPackages(selectFirst, wanted) {
  const run = state.run;
  let packages;
  try {
    packages = await getJson(`/api/runs/${encodeURIComponent(run)}/packages`);
  } catch (error) {
    setStatus('Không đọc được run', true);
    return;
  }
  if (run !== state.run) return;
  const list = $('packages');
  list.replaceChildren();
  $('package-count').textContent = `${packages.length} gói`;
  if (!packages.length) list.append(el('li', 'empty', 'Run này chưa có trace hợp lệ.'));
  for (const item of packages) {
    const button = el('button', 'package');
    button.type = 'button';
    button.dataset.pkg = item.package;
    button.setAttribute('aria-current', String(item.package === state.pkg));
    const tag = item.status === 'error' ? 'error' : (['benign', 'suspicious', 'malicious'].includes(item.label) ? item.label : '');
    button.append(el('strong', null, item.package),
      el('span', null, `${item.model ?? '?'} · ${STATUS[item.status] ?? item.status} · ${item.steps ?? '?'} bước`),
      el('span', tag ? `tag-${tag}` : null, item.label ? `${LABELS[item.label] ?? item.label}` : 'Chưa có nhãn'));
    button.addEventListener('click', () => selectPackage(item.package));
    const row = el('li');
    row.append(button);
    list.append(row);
  }
  const target = wanted && packages.some((item) => item.package === wanted) ? wanted
    : selectFirst && packages.length ? packages[0].package : null;
  if (target) selectPackage(target);
}

async function init() {
  const params = new URLSearchParams(location.hash.slice(1));
  let runs;
  try {
    runs = await getJson('/api/runs');
  } catch (error) {
    setStatus('Không kết nối được server', true);
    return;
  }
  const select = $('run-select');
  for (const run of runs) select.append(new Option(run, run));
  if (!runs.length) {
    setStatus('Chưa có run nào');
    return;
  }
  state.run = runs.includes(params.get('run')) ? params.get('run') : runs[0];
  select.value = state.run;
  setStatus('Sẵn sàng');
  select.addEventListener('change', () => {
    stopReplay();
    stopPolling();
    state.run = select.value;
    state.pkg = null;
    loadPackages(true);
  });
  $('previous').addEventListener('click', () => { stopReplay(); state.cursor = Math.max(0, state.cursor - 1); render(); });
  $('next').addEventListener('click', () => { stopReplay(); state.cursor = Math.min(state.events.length - 1, state.cursor + 1); render(); });
  $('play').addEventListener('click', () => { if (state.timer) stopReplay(); else startReplay(); });
  $('speed').addEventListener('change', () => { if (state.timer) { stopReplay(); startReplay(); } });
  loadPackages(true, params.get('pkg'));
}

init();
