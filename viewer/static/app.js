// Read-only replay/live viewer. Trace content is untrusted: it only ever reaches the page through textContent.
// Shares the plain-language step text, the room/phase map and the rule ladder with the 3D office.
import {explainStep} from '/office/explain.mjs';
import {roomFor} from '/office/events.mjs';
import {ruleLadder, ruleSentence, TERMS} from '/office/rules.mjs';
import {initPrefs} from '/ui.mjs';

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
// Package filter by outcome; "error" is a run that ran out of steps.
const PACKAGE_FILTERS = [['all', 'Tất cả'], ['malicious', 'Độc hại'], ['suspicious', 'Đáng ngờ'], ['benign', 'Lành tính'], ['error', 'Hết bước']];
// Event filter: which kinds of step to list.
const EVENT_FILTERS = [['all', 'Tất cả'], ['key', '★ Bước quan trọng'], ['tool', 'Công cụ'], ['model', 'Mô hình'], ['problem', 'Lỗi']];
// Cases worth a human look, computed from the package list (and labels.csv for the reference label).
const ISSUE_FILTERS = [['disagree', 'Mô hình ≠ luật'], ['wrong', 'Sai nhãn chuẩn'], ['fake', 'Bằng chứng không có thật']];
const ISSUE_FLAGS = {disagree: 'mô hình ≠ luật', wrong: 'sai nhãn chuẩn', fake: 'bằng chứng giả'};
// Runs that differ only in the model size, e.g. w57-reg-a-llm / -a-slm / -a-tlm.
const VARIANT = /(^|[-_])a-(llm|slm|tlm)(?=$|[-_])/i;
const POLL_MS = 1000;
// The agent's four phases (AGENTS.md section 3); errors and retries stay in the phase they happened in.
const PHASES = [['Nhận diện', 'đọc manifest, script cài đặt'], ['Phân tích', 'đọc mã, tìm chỉ báo'],
  ['Kiểm chứng', 'bằng chứng file:dòng có thật?'], ['Quyết định', 'luật R1–R8, dry-run']];
const PHASE_OF_ROOM = {reception: 0, code: 1, intel: 1, lab: 1, evidence: 2, decision: 3};
const WHO = {model: 'Mô hình AI', tool: 'Công cụ', rules: 'Luật / kiểm tra', system: 'Hệ thống'};

const $ = (id) => document.getElementById(id);
const state = {
  run: null, pkg: null, events: [], cursor: -1, timer: null, poll: null, live: false,
  phases: [], runs: [], packages: [], packageFilter: 'all', reviewed: new Set(), eventFilter: 'all', issueFilter: null, truth: {},
};

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

function remember(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(`viewer.${key}`);
    localStorage.setItem(`viewer.${key}`, value);
  } catch { /* storage blocked: the setting just is not remembered */ }
  return null;
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

function issuesOf(item) {
  const truth = state.truth[item.package];
  return ISSUE_FILTERS.map(([key]) => key).filter((key) => {
    if (key === 'disagree') return Boolean(item.proposal_label && item.label && item.proposal_label !== item.label);
    if (key === 'wrong') return Boolean(truth && item.label && truth !== item.label);
    return item.evidence_total > 0 && item.evidence_ok < item.evidence_total;
  });
}

function packageTag(item) {
  if (item.status === 'error') return 'error';
  return ['benign', 'suspicious', 'malicious'].includes(item.label) ? item.label : '';
}

// One event -> {name, detail, tone, group, preview}
function describe(event) {
  switch (event.type) {
    case 'run_start':
      return {name: 'Bắt đầu phân tích', detail: `Mô hình ${event.model ?? '?'} · tối đa ${event.max_steps ?? '?'} bước`, tone: 'info', group: 'model'};
    case 'thought':
      return {name: 'Mô hình ghi chú', detail: '', tone: 'info', group: 'model', preview: event.text, previewLabel: 'Lời mô hình — không tin cậy'};
    case 'tool_call':
      return {name: `Gọi công cụ ${event.tool ?? ''}`, detail: short(event.args ?? {}), tone: 'info', group: 'tool'};
    case 'tool_result':
      return {name: `Kết quả ${event.tool ?? ''}`, tone: event.ok ? 'ok' : 'error', group: event.ok ? 'tool' : 'problem',
        detail: `${event.ok ? 'Thành công' : 'Lỗi'} · ${event.summary ?? ''}${event.duration_ms != null ? ` · ${event.duration_ms} ms` : ''}`,
        preview: event.untrusted ? event.data_preview : null, previewLabel: 'Dữ liệu mã gói — không tin cậy'};
    case 'verdict': {
      const verdict = event.verdict || {};
      return event.valid
        ? {name: 'Verdict hợp lệ', detail: `${LABELS[verdict.label] ?? verdict.label} · đề xuất ${ACTIONS[verdict.action] ?? verdict.action}`, tone: 'ok', group: 'model'}
        : {name: 'Verdict bị từ chối', detail: short((event.validation_errors || []).join(' | ')), tone: 'retry', group: 'problem'};
    }
    case 'decision':
      return {name: 'Quyết định cuối', tone: 'ok', group: 'decision',
        detail: `${LABELS[event.final_label] ?? event.final_label} · ${ACTIONS[event.final_action] ?? event.final_action}${ruleText(event)}`};
    case 'error':
      return {name: ERRORS[event.kind] ?? `Lỗi ${event.kind ?? ''}`, detail: short(event.message), tone: 'error', group: 'problem'};
    case 'limit':
      return {name: 'Hết giới hạn bước', detail: 'Agent dừng và chuyển sang kiểm tra thủ công.', tone: 'error', group: 'problem'};
    case 'run_end':
      return {name: 'Kết thúc', detail: `${event.steps ?? '?'} bước · ${event.elapsed_s ?? '?'} giây`, tone: 'ok', group: 'decision'};
    default:
      return {name: 'Sự kiện khác', detail: short(event.type), tone: 'info', group: 'other'};
  }
}

// Seconds since the first event, from the trace timestamps ("+3.2 s").
function elapsed(event) {
  const start = Date.parse(state.events[0]?.ts);
  const at = Date.parse(event.ts);
  if (Number.isNaN(start) || Number.isNaN(at)) return '';
  const seconds = (at - start) / 1000;
  return seconds < 60 ? `+${seconds.toFixed(1)} s` : `+${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, '0')}`;
}

function eventItem(event, index) {
  const info = describe(event);
  const item = el('li', `event ${['ok', 'retry', 'error'].includes(info.tone) ? info.tone : 'info'}`);
  item.dataset.group = info.group;
  item.dataset.index = String(index);
  item.append(el('span', 'event-index', String(index + 1).padStart(2, '0')));
  const body = el('div', 'event-body');
  const step = explainStep(state.events, index);
  const kind = el('span', 'event-kind');
  kind.append(el('span', 'dot'), el('span', `who ${step.actor}`, WHO[step.actor] ?? step.who), document.createTextNode(step.title || info.name));
  body.append(kind);
  const flow = el('div', 'flow');
  for (const [label, text, untrusted] of [['Vào', step.input], ['Xử lý', step.process], ['Ra', step.output, step.untrustedOutput]]) {
    const part = el('div', untrusted ? 'untrusted' : null);
    part.append(el('small', null, label), el('span', null, text || '—'));
    flow.append(part);
  }
  body.append(flow);
  if (info.preview) {
    const block = el('details', 'source-block');
    const lines = String(info.preview).split('\n').length;
    block.append(el('summary', null, `${info.previewLabel} · ${lines} dòng`), el('pre', null, info.preview));
    body.append(block);
  }
  item.append(body, el('span', 'event-time', elapsed(event)));
  item.addEventListener('click', (click) => {
    if (click.target.closest('summary, pre')) return; // reading a preview is not a jump
    jump(index);
  });
  return item;
}

// Steps that decide the outcome: the verdicts, the rule decision, errors, and the reads of every file
// the verdict or the evidence check points at.
function markKeySteps() {
  const decision = state.events.find((event) => event.type === 'decision');
  const verdict = [...state.events].reverse().find((event) => event.type === 'verdict' && event.valid);
  const files = new Set([...(decision?.evidence_checks || []).map((check) => check.file),
    ...(verdict?.verdict?.behaviors || []).map((behavior) => behavior.evidence?.file)].filter(Boolean));
  const items = $('timeline').children;
  state.events.forEach((event, index) => {
    const previous = state.events[index - 1];
    const readsCited = (event.type === 'tool_call' && files.has(event.args?.file)) ||
      (event.type === 'tool_result' && previous?.type === 'tool_call' && files.has(previous.args?.file));
    const key = ['verdict', 'decision', 'error', 'limit'].includes(event.type) || readsCited;
    items[index]?.classList.toggle('key', key);
  });
}

function applyEventFilter() {
  const filter = state.eventFilter;
  for (const item of $('timeline').children) {
    const group = item.dataset.group;
    const shown = filter === 'all' || group === filter || (filter === 'model' && group === 'decision') ||
      (filter === 'key' && item.classList.contains('key'));
    item.classList.toggle('is-filtered', !shown);
  }
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
    body.append(el('p', 'pending-copy', state.live ? 'Đang chờ quyết định…' : state.pkg ? 'Chưa tới bước quyết định' : 'Chưa có quyết định'));
    if (verdict) body.append(el('p', 'outcome-meta', 'Mô hình đã nộp verdict; luật cứng chưa chạy ở bước đang xem.'));
    return;
  }
  result.className = 'result';
  const label = ['benign', 'suspicious', 'malicious'].includes(decision.final_label) ? decision.final_label : '';
  const head = el('div', 'verdict-head');
  head.append(el('p', `outcome ${label}`, LABELS[decision.final_label] ?? decision.final_label),
    el('span', `badge ${decision.final_action ?? ''}`, ACTIONS[decision.final_action] ?? decision.final_action));
  body.append(head, whySummary(decision, verdict));

  const checks = decision.evidence_checks || [];
  if (checks.length) {
    body.append(el('h3', null, `Kiểm chứng bằng chứng (${checks.filter((check) => check.exists).length}/${checks.length} có thật)`));
    const list = el('ul', 'evidence');
    for (const check of checks) {
      const item = el('li', check.exists ? null : 'missing');
      const where = el('div', 'where');
      where.append(el('code', null, `${check.file ?? '?'}:${check.lines ?? '?'}`),
        el('span', `check ${check.exists ? 'yes' : 'no'}`, check.exists ? '✓ có trong gói' : '✗ không tìm thấy'));
      addJump(where, check.file);
      item.append(where);
      list.append(item);
    }
    body.append(list);
  }

  if (verdict && verdict.verdict) {
    const proposal = verdict.verdict;
    const confidence = Math.round((proposal.confidence ?? 0) * 100);
    body.append(el('h3', null, 'Mô hình đề xuất'));
    body.append(el('p', null, `${LABELS[proposal.label] ?? proposal.label} · ${ACTIONS[proposal.action] ?? proposal.action}`));
    const meter = el('div', 'confidence');
    const bar = el('meter');
    Object.assign(bar, {min: 0, max: 100, low: 50, high: 80, optimum: 100, value: confidence});
    bar.setAttribute('aria-label', 'Độ tin cậy mô hình tự nêu');
    meter.append(bar, el('span', null, `tin cậy ${confidence}%`));
    body.append(meter);
    if (proposal.description) body.append(el('p', 'outcome-meta', proposal.description));
    body.append(el('h3', null, 'Hành vi agent đã nêu'));
    const list = el('ul', 'evidence');
    for (const behavior of proposal.behaviors || []) {
      const item = el('li');
      const where = el('div', 'where');
      where.append(el('code', null, `${behavior.evidence?.file ?? '?'}:${behavior.evidence?.lines ?? '?'}`));
      if (behavior.severity) where.append(el('span', 'outcome-meta', `mức ${behavior.severity}`));
      addJump(where, behavior.evidence?.file);
      item.append(el('strong', null, behavior.behavior), where, el('p', null, behavior.analysis));
      list.append(item);
    }
    if (!list.childElementCount) list.append(el('li', 'empty', 'Không có hành vi nào được nêu.'));
    body.append(list);
  } else if (decision.rule === 'R2') {
    body.append(el('p', 'error-copy', 'Không có verdict hợp lệ; agent dùng phương án an toàn.'));
  }
}

// The answer to "why this outcome", in one sentence and four facts a reader can check.
function whySummary(decision, verdict) {
  const box = el('div', 'why');
  const proposal = verdict?.verdict;
  const checks = decision.evidence_checks || [];
  const real = checks.filter((check) => check.exists).length;
  const truth = state.truth[state.pkg];
  const action = ACTIONS[decision.final_action] ?? decision.final_action ?? 'không gọi lệnh';
  box.append(el('p', 'why-lead', `Kết luận: ${LABELS[decision.final_label] ?? decision.final_label} → ${action}.`),
    el('p', null, ruleSentence(decision.rule)));
  if ((decision.reasons || []).length) box.append(el('p', 'outcome-meta', `Chi tiết luật ghi lại: ${decision.reasons.join('; ')}`));
  const ladder = el('ol', 'ladder');
  ladder.setAttribute('aria-label', 'Các luật xét từ trên xuống, luật khớp đầu tiên quyết định');
  for (const rule of ruleLadder(decision.rule)) {
    const row = el('li', rule.state);
    const mark = rule.state === 'fired' ? 'KHỚP' : rule.state === 'skipped' ? 'không khớp' : 'không xét';
    row.append(el('b', null, rule.code), el('span', null, rule.variant ? `${rule.when}. Bị giữ vì: ${rule.variant}` : rule.when),
      el('em', null, rule.state === 'fired' ? `${mark} → ${rule.then}` : mark));
    ladder.append(row);
  }
  box.append(el('p', 'ladder-title', 'Luật xét lần lượt từ trên xuống; luật đầu tiên khớp quyết định:'), ladder);
  const facts = el('dl', 'why-facts');
  const fact = (term, text, tone) => facts.append(el('dt', null, term), el('dd', tone, text));
  if (proposal) {
    const same = proposal.label === decision.final_label;
    fact('Mô hình đề xuất', `${LABELS[proposal.label] ?? proposal.label}, tin cậy ${Math.round((proposal.confidence ?? 0) * 100)}% — ${same ? 'luật giữ nguyên' : 'luật đã sửa nhãn'}`, same ? 'ok' : 'warn');
  } else {
    fact('Mô hình đề xuất', 'không có verdict hợp lệ', 'bad');
  }
  if (checks.length) fact('Bằng chứng', `${real}/${checks.length} vị trí file:dòng có thật trong gói`, real === checks.length ? 'ok' : 'bad');
  else fact('Bằng chứng', 'mô hình không nêu vị trí nào', 'warn');
  if (truth) fact('Nhãn chuẩn', `${LABELS[truth] ?? truth} — ${truth === decision.final_label ? 'kết luận đúng' : 'kết luận lệch nhãn chuẩn'}`, truth === decision.final_label ? 'ok' : 'bad');
  else fact('Nhãn chuẩn', 'gói chưa có trong data/labels.csv', null);
  fact('Chế độ', decision.dry_run ? 'dry-run: chỉ in lệnh, không đổi package.json' : 'không ghi rõ dry-run', null);
  box.append(facts);
  return box;
}

// "Xem bước đọc": the first step where the agent opened that file, if the trace has one.
function addJump(container, file) {
  if (!file) return;
  const index = state.events.findIndex((event) => event.type === 'tool_call' && event.args && event.args.file === file);
  if (index < 0) return;
  const button = el('button', 'link-button', `xem bước đọc #${index + 1}`);
  button.type = 'button';
  button.addEventListener('click', () => jump(index + 1 < state.events.length ? index + 1 : index));
  container.append(button);
}

function render(scroll = false) {
  const items = $('timeline').children;
  for (let index = 0; index < items.length; index += 1) {
    items[index].classList.toggle('is-future', index > state.cursor);
    const active = index === state.cursor;
    items[index].classList.toggle('is-active', active);
    if (active) items[index].querySelector('details')?.setAttribute('open', '');
  }
  const current = state.events[state.cursor];
  const info = current ? describe(current) : null;
  $('current-index').textContent = current ? String(state.cursor + 1).padStart(2, '0') : '—';
  $('current-action-text').textContent = info ? info.name : (state.pkg ? 'Chưa có sự kiện' : 'Chưa chọn gói');
  $('current-action-detail').textContent = info ? (info.detail || '') : 'Chọn một run và một gói để xem lại từng bước của agent.';
  $('replay-position').textContent = `${state.cursor + 1} / ${state.events.length}`;
  renderPhaseTrack();
  const scrub = $('scrub');
  scrub.max = String(Math.max(0, state.events.length - 1));
  scrub.value = String(Math.max(0, state.cursor));
  scrub.disabled = state.events.length < 2;
  $('previous').disabled = state.cursor <= 0;
  $('next').disabled = state.cursor >= state.events.length - 1;
  $('play').disabled = state.events.length === 0;
  renderResult();
  if (items[state.cursor] && (scroll || state.timer || state.live)) items[state.cursor].scrollIntoView({block: 'nearest'});
}

function jump(index) {
  stopReplay();
  state.cursor = Math.max(0, Math.min(state.events.length - 1, index));
  render(true);
}

function append(events) {
  const follow = state.cursor === state.events.length - 1;
  for (const event of events) {
    state.events.push(event);
    const index = state.events.length - 1;
    const item = eventItem(event, index);
    const previous = index ? state.phases[index - 1] : -1;
    const phase = PHASE_OF_ROOM[roomFor(event)] ?? Math.max(0, previous);
    state.phases.push(phase);
    item.dataset.phase = String(phase);
    if (phase !== previous) {
      item.classList.add('phase-start');
      item.dataset.phaseName = `Giai đoạn ${phase + 1} · ${PHASES[phase][0]}`;
    }
    $('timeline').append(item);
  }
  if (follow) state.cursor = state.events.length - 1;
  markKeySteps();
  applyEventFilter();
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

function linkFor(pkg) {
  return `run=${encodeURIComponent(state.run)}&pkg=${encodeURIComponent(pkg)}`;
}

function selectPackage(pkg) {
  stopReplay();
  stopPolling();
  state.pkg = pkg;
  state.events = [];
  state.phases = [];
  state.cursor = -1;
  state.live = true;
  $('timeline').replaceChildren();
  for (const button of document.querySelectorAll('.package')) {
    button.setAttribute('aria-current', String(button.dataset.pkg === pkg));
  }
  $('package-name').textContent = pkg;
  $('reviewed-toggle').checked = state.reviewed.has(reviewKey(pkg));
  history.replaceState(null, '', `#${linkFor(pkg)}`);
  $('office-link').href = `/office#mode=single&${linkFor(pkg)}`;
  render();
  poll(pkg);
  renderCompare();
}

function chip(group, value, text, count, pressed, onPick) {
  const button = el('button', 'filter-chip');
  button.type = 'button';
  button.setAttribute('aria-pressed', String(pressed));
  if (value !== 'all' && group === 'label') button.append(el('span', `dot ${value}`));
  button.append(document.createTextNode(text));
  if (count != null) button.append(el('b', null, count));
  button.addEventListener('click', () => onPick(value));
  return button;
}

function renderPackageFilters() {
  const counts = {all: state.packages.length};
  for (const item of state.packages) counts[packageTag(item)] = (counts[packageTag(item)] || 0) + 1;
  $('label-filter').replaceChildren(...PACKAGE_FILTERS
    .filter(([value]) => value === 'all' || counts[value])
    .map(([value, text]) => chip('label', value, text, counts[value] || 0, state.packageFilter === value, (picked) => {
      state.packageFilter = picked;
      renderPackageFilters();
      applyPackageFilter();
    })));
}

// Four numbers that say what this run shows: how often it matched the reference labels, how often
// its evidence was real, how much was sent to a person, and what it cost.
function renderRunOverview() {
  const list = $('run-overview');
  list.replaceChildren();
  const items = state.packages;
  if (!items.length) return;
  const judged = items.filter((item) => state.truth[item.package] && item.label);
  const right = judged.filter((item) => state.truth[item.package] === item.label).length;
  const withEvidence = items.filter((item) => item.evidence_total > 0);
  const evidenceOk = withEvidence.reduce((sum, item) => sum + item.evidence_ok, 0);
  const evidenceAll = withEvidence.reduce((sum, item) => sum + item.evidence_total, 0);
  const review = items.filter((item) => item.action === 'review').length;
  const times = items.map((item) => Number(item.elapsed_s)).filter((value) => Number.isFinite(value));
  const average = times.length ? times.reduce((a, b) => a + b, 0) / times.length : null;
  const row = (term, value, hint) => {
    const dt = el('dt', null, term);
    if (hint) dt.title = hint;
    list.append(dt, el('dd', null, value));
  };
  row('Đúng nhãn chuẩn', judged.length ? `${right}/${judged.length} gói (${Math.round(right / judged.length * 100)}%)` : 'chưa có gói nào trong labels.csv',
    'So kết luận cuối với data/labels.csv, chỉ tính gói có nhãn chuẩn');
  row('Bằng chứng có thật', evidenceAll ? `${evidenceOk}/${evidenceAll} vị trí` : '—', 'Vị trí file:dòng mô hình trích có tồn tại trong gói');
  row('Chuyển người xem', `${review}/${items.length} gói`, 'Luật không đủ chắc để tự chặn hay cho phép');
  row('Thời gian trung bình', average == null ? '—' : `${average.toFixed(1)} s/gói`);
}

function renderPhaseTrack() {
  const track = $('phase-track');
  const current = state.cursor >= 0 ? state.phases[state.cursor] : -1;
  if (!track.childElementCount) {
    track.replaceChildren(...PHASES.map(([name, hint], phase) => {
      const button = el('button', 'phase');
      button.type = 'button';
      button.append(el('b', null, String(phase + 1)), el('span', null, name), el('small', null, hint));
      button.addEventListener('click', () => {
        const first = state.phases.indexOf(phase);
        if (first >= 0) jump(first);
      });
      return el('li', null).appendChild(button).parentNode;
    }));
  }
  [...track.children].forEach((li, phase) => {
    const button = li.firstChild;
    const count = state.phases.filter((value) => value === phase).length;
    button.disabled = count === 0;
    button.classList.toggle('done', current > phase);
    button.classList.toggle('current', current === phase);
    button.title = count ? `${count} bước — bấm để tua tới bước đầu` : 'Lượt chạy này không có bước nào ở giai đoạn này';
  });
}

// "Đã xem xong" marks: one set per browser, keyed by run and package.
function reviewKey(pkg) { return `${state.run}|${pkg}`; }

function setReviewed(on) {
  if (!state.pkg) return;
  if (on) state.reviewed.add(reviewKey(state.pkg)); else state.reviewed.delete(reviewKey(state.pkg));
  remember('reviewed', JSON.stringify([...state.reviewed].slice(-2000)));
  $('reviewed-toggle').checked = on;
  const pkg = state.pkg;
  loadPackages(false, null).then(() => {
    for (const button of document.querySelectorAll('.package')) button.setAttribute('aria-current', String(button.dataset.pkg === pkg));
  });
}

function setPresenting(on) {
  document.body.classList.toggle('present', on);
  $('present').setAttribute('aria-pressed', String(on));
  $('present').textContent = on ? 'Thoát trình chiếu' : 'Trình chiếu';
  if (on && !document.fullscreenElement) document.documentElement.requestFullscreen?.().catch(() => {});
  if (!on && document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
}

function renderIssueFilters() {
  const counts = {};
  for (const item of state.packages) for (const issue of issuesOf(item)) counts[issue] = (counts[issue] || 0) + 1;
  if (state.issueFilter && !counts[state.issueFilter]) state.issueFilter = null;
  counts.unreviewed = state.packages.filter((item) => !state.reviewed.has(reviewKey(item.package))).length;
  const chips = [...ISSUE_FILTERS, ['unreviewed', 'Chưa xem']].map(([value, text]) => {
    const button = chip('issue', value, text, counts[value] || 0, state.issueFilter === value, (picked) => {
      state.issueFilter = state.issueFilter === picked ? null : picked;
      renderIssueFilters();
      applyPackageFilter();
    });
    button.classList.add('issue');
    button.disabled = !counts[value];
    if (value === 'wrong' && !Object.keys(state.truth).length) button.title = 'Chưa đọc được data/labels.csv';
    return button;
  });
  $('issue-filter').replaceChildren(...chips);
}

function applyPackageFilter() {
  const text = $('package-filter').value.trim().toLowerCase();
  let shown = 0;
  for (const row of $('packages').children) {
    const pkg = row.dataset.pkg;
    if (!pkg) continue;
    const visible = (!text || pkg.toLowerCase().includes(text)) &&
      (state.packageFilter === 'all' || row.dataset.tag === state.packageFilter) &&
      (!state.issueFilter || (state.issueFilter === 'unreviewed' ? !state.reviewed.has(reviewKey(pkg))
        : (row.dataset.issues || '').split(' ').includes(state.issueFilter)));
    row.hidden = !visible;
    if (visible) shown += 1;
  }
  const total = state.packages.length;
  $('package-count').textContent = shown === total ? `${total}` : `${shown} / ${total}`;
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
  state.packages = packages;
  if (!packages.some((item) => packageTag(item) === state.packageFilter)) state.packageFilter = 'all';
  const list = $('packages');
  list.replaceChildren();
  if (!packages.length) list.append(el('li', 'empty', 'Run này chưa có trace hợp lệ.'));
  for (const item of packages) {
    const tag = packageTag(item);
    const button = el('button', 'package');
    button.type = 'button';
    button.dataset.pkg = item.package;
    button.setAttribute('aria-current', String(item.package === state.pkg));
    button.title = item.label ? (LABELS[item.label] ?? item.label) : 'Chưa có nhãn';
    const issues = issuesOf(item);
    button.append(el('span', `dot ${tag}`), el('strong', null, item.package),
      el('small', null, `${item.label ? (LABELS[item.label] ?? item.label) : 'Chưa có nhãn'} · ${STATUS[item.status] ?? item.status} · ${item.steps ?? '?'} bước · ${item.model ?? '?'}`));
    const seen = state.reviewed.has(reviewKey(item.package));
    if (issues.length || seen) {
      const flags = el('span', 'flags');
      if (seen) flags.append(el('span', 'flag seen', '✓ đã xem'));
      for (const issue of issues) flags.append(el('span', `flag${issue === 'disagree' ? '' : ' bad'}`, ISSUE_FLAGS[issue]));
      button.append(flags);
    }
    button.addEventListener('click', () => selectPackage(item.package));
    const row = el('li');
    row.dataset.pkg = item.package;
    row.dataset.tag = tag;
    row.dataset.issues = issues.join(' ');
    row.append(button);
    list.append(row);
  }
  renderPackageFilters();
  renderIssueFilters();
  renderRunOverview();
  applyPackageFilter();
  const target = wanted && packages.some((item) => item.package === wanted) ? wanted
    : selectFirst && packages.length ? packages[0].package : null;
  if (target) selectPackage(target);
}

function switchRun(run) {
  if (!run || run === state.run) return;
  stopReplay();
  stopPolling();
  state.run = run;
  state.pkg = null;
  $('run-select').value = run;
  loadPackages(true);
}

function renderRunOptions() {
  const text = $('run-filter').value.trim().toLowerCase();
  const select = $('run-select');
  const matches = state.runs.filter((run) => !text || run.toLowerCase().includes(text) || run === state.run);
  select.replaceChildren(...matches.map((run) => new Option(run, run)));
  select.value = state.run;
  $('run-count').textContent = matches.length === state.runs.length ? `${state.runs.length}` : `${matches.length - (text && !state.run.toLowerCase().includes(text) ? 1 : 0)} / ${state.runs.length}`;
}

// Same package in the sibling runs (A-LLM / A-SLM / A-TLM): who said what, side by side.
async function renderCompare() {
  const panel = $('compare');
  if (panel.hidden || !state.pkg) return;
  const body = $('compare-body');
  body.replaceChildren();
  const siblings = VARIANT.test(state.run)
    ? state.runs.filter((run) => run.replace(VARIANT, '$1a-*') === state.run.replace(VARIANT, '$1a-*'))
    : [state.run];
  const group = state.run.replace(VARIANT, '$1a-*');
  $('compare-note').textContent = siblings.length > 1
    ? `Cùng gói ${state.pkg} trong ${siblings.length} run chỉ khác cỡ mô hình. Ô màu vàng: khác với run đang xem.`
    : VARIANT.test(state.run)
      ? 'Không có run nào khác chỉ khác cỡ mô hình với run này, nên chưa có gì để so.'
      : 'Run này không thuộc bộ a-llm / a-slm / a-tlm. Chọn một run có hậu tố đó để so 3 cỡ mô hình.';
  const rows = await Promise.all(siblings.map(async (run) => {
    try {
      const list = await getJson(`/api/runs/${encodeURIComponent(run)}/packages`);
      return {run, item: list.find((entry) => entry.package === state.pkg)};
    } catch { return {run, item: null}; }
  }));
  if (!panel.hidden) {
    const mine = rows.find((row) => row.run === state.run)?.item;
    for (const {run, item} of rows) {
      const tr = el('tr', run === state.run ? 'current' : null);
      const cell = (text, differs = false) => tr.append(el('td', differs ? 'differs' : null, text));
      const code = el('td');
      code.append(el('code', null, run));
      tr.append(code);
      if (!item) { cell(''); cell('không có gói này'); cell(''); cell(''); cell(''); tr.append(el('td')); body.append(tr); continue; }
      cell(item.model ?? '?');
      cell(item.proposal_label ? `${LABELS[item.proposal_label] ?? item.proposal_label}${item.confidence != null ? ` · ${Math.round(item.confidence * 100)}%` : ''}` : 'không hợp lệ',
        mine && item.proposal_label !== mine.proposal_label);
      cell(`${LABELS[item.label] ?? item.label ?? '?'} · ${ACTIONS[item.action] ?? item.action ?? '—'}${item.rule ? ` (${item.rule})` : ''}`,
        mine && (item.label !== mine.label || item.action !== mine.action));
      cell(item.evidence_total ? `${item.evidence_ok}/${item.evidence_total} có thật` : '—', mine && item.evidence_ok !== mine.evidence_ok);
      cell(`${item.steps ?? '?'} · ${item.elapsed_s ?? '?'} s`);
      const open = el('td');
      if (run !== state.run) {
        const link = el('a', null, 'Xem');
        link.href = `#run=${encodeURIComponent(run)}&pkg=${encodeURIComponent(state.pkg)}`;
        open.append(link);
      }
      tr.append(open);
      body.append(tr);
    }
    if (siblings.length > 1) {
      const row = el('tr');
      const td = el('td');
      td.colSpan = 7;
      const race = el('a', null, 'Xem 3 model đua trên cùng gói trong văn phòng 3D →');
      race.href = `/office#mode=compare&run=${encodeURIComponent(group)}&pkg=${encodeURIComponent(state.pkg)}`;
      td.append(race);
      row.append(td);
      body.append(row);
    }
  }
}

// A Markdown report of the package being viewed: outcome, why, evidence and every step (as text only).
function exportReport() {
  if (!state.pkg || !state.events.length) return;
  const decision = state.events.find((event) => event.type === 'decision');
  const verdict = [...state.events].reverse().find((event) => event.type === 'verdict' && event.valid)?.verdict;
  const truth = state.truth[state.pkg];
  const lines = [`# Báo cáo kiểm tra ${state.pkg}`, '', `- Run: \`${state.run}\``,
    `- Mô hình: ${state.events[0]?.model ?? '?'}`,
    `- Kết luận (luật cứng): **${LABELS[decision?.final_label] ?? decision?.final_label ?? 'chưa có'}** → ${ACTIONS[decision?.final_action] ?? decision?.final_action ?? '—'}${decision ? ruleText(decision) : ''}`,
    `- Mô hình đề xuất: ${verdict ? `${LABELS[verdict.label] ?? verdict.label}, tin cậy ${Math.round((verdict.confidence ?? 0) * 100)}%` : 'không có verdict hợp lệ'}`,
    `- Nhãn chuẩn: ${truth ? (LABELS[truth] ?? truth) : 'chưa có'}`, ''];
  if ((decision?.reasons || []).length) lines.push('## Lý do của luật', '', ...decision.reasons.map((reason) => `- ${reason}`), '');
  if ((decision?.evidence_checks || []).length) {
    lines.push('## Kiểm chứng bằng chứng', '', ...decision.evidence_checks.map((check) => `- \`${check.file}:${check.lines}\` — ${check.exists ? 'có thật' : 'KHÔNG tìm thấy'}`), '');
  }
  if ((verdict?.behaviors || []).length) {
    lines.push('## Hành vi mô hình nêu (dữ liệu không tin cậy)', '');
    for (const behavior of verdict.behaviors) lines.push(`- **${behavior.behavior}** (\`${behavior.evidence?.file}:${behavior.evidence?.lines}\`, mức ${behavior.severity ?? '?'}): ${behavior.analysis ?? ''}`);
    lines.push('');
  }
  lines.push('## Các bước', '');
  state.events.forEach((event, index) => {
    const info = describe(event);
    lines.push(`${index + 1}. ${info.name}${info.detail ? ` — ${info.detail.replace(/\s+/g, ' ')}` : ''}`);
  });
  lines.push('', '_Xuất từ trình xem trace. Nội dung lấy từ gói và lời mô hình là dữ liệu không tin cậy._', '');
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([lines.join('\n')], {type: 'text/markdown;charset=utf-8'}));
  link.download = `bao-cao-${state.pkg.replace(/[^a-z0-9.@-]+/gi, '_')}-${state.run}.md`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 4000);
}

function onKey(event) {
  const target = event.target instanceof Element ? event.target : document.body;
  if (event.ctrlKey || event.metaKey || event.altKey || target.closest('input, select, textarea')) return;
  // On a focused button or summary, Space keeps its own meaning (press / open); arrows still step.
  if (event.key === ' ' && target.closest('button, summary')) return;
  const keys = {
    ArrowLeft: () => jump(state.cursor - 1), ArrowRight: () => jump(state.cursor + 1),
    Home: () => jump(0), End: () => jump(state.events.length - 1),
    p: () => setPresenting(!document.body.classList.contains('present')),
    m: () => setReviewed(!state.reviewed.has(reviewKey(state.pkg))),
    ' ': () => { if (state.timer) stopReplay(); else if (state.events.length) startReplay(); },
  };
  const action = keys[event.key.length === 1 ? event.key.toLowerCase() : event.key];
  if (!action || !state.events.length) return;
  event.preventDefault();
  action();
}

async function init() {
  const params = new URLSearchParams(location.hash.slice(1));
  $('kind-filter').replaceChildren(...EVENT_FILTERS.map(([value, text]) => chip('kind', value, text, null, value === 'all', (picked) => {
    state.eventFilter = picked;
    for (const button of $('kind-filter').children) button.setAttribute('aria-pressed', String(button.textContent === text && picked === value));
    applyEventFilter();
  })));
  const showAll = $('show-all');
  showAll.checked = remember('showAll') !== '0';
  const applyShowAll = () => { $('timeline').classList.toggle('hide-future', !showAll.checked); remember('showAll', showAll.checked ? '1' : '0'); };
  showAll.addEventListener('change', applyShowAll);
  applyShowAll();

  initPrefs(document.querySelector('.masthead'), [['← →', 'Bước trước / bước tiếp'], ['Space', 'Phát / tạm dừng'],
    ['Home End', 'Về bước đầu / bước cuối'], ['P', 'Bật / tắt trình chiếu'], ['M', 'Đánh dấu gói đang xem là đã xem xong']]);
  try { state.reviewed = new Set(JSON.parse(remember('reviewed') || '[]')); } catch { state.reviewed = new Set(); }
  $('reviewed-toggle').addEventListener('change', (event) => setReviewed(event.target.checked));
  $('present').addEventListener('click', () => setPresenting(!document.body.classList.contains('present')));
  document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement) setPresenting(false); });
  $('terms-list').replaceChildren(...Object.entries(TERMS).flatMap(([term, text]) => [el('dt', null, term), el('dd', null, text)]));
  const about = $('about');
  if (remember('about') === '0') about.open = false;
  about.addEventListener('toggle', () => remember('about', about.open ? '1' : '0'));
  try { state.truth = await getJson('/api/labels'); } catch { state.truth = {}; }
  let runs;
  try {
    runs = await getJson('/api/runs');
  } catch (error) {
    setStatus('Không kết nối được server', true);
    return;
  }
  state.runs = runs;
  if (!runs.length) {
    setStatus('Chưa có run nào');
    return;
  }
  state.run = runs.includes(params.get('run')) ? params.get('run') : runs[0];
  renderRunOptions();
  setStatus('Sẵn sàng');
  $('run-select').addEventListener('change', (event) => switchRun(event.target.value));
  $('run-filter').addEventListener('input', renderRunOptions);
  $('run-filter').addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') return;
    const first = [...$('run-select').options].find((option) => option.value !== state.run) || $('run-select').options[0];
    if (first) switchRun(first.value);
  });
  $('package-filter').addEventListener('input', applyPackageFilter);
  $('previous').addEventListener('click', () => jump(state.cursor - 1));
  $('next').addEventListener('click', () => jump(state.cursor + 1));
  $('scrub').addEventListener('input', (event) => jump(Number(event.target.value)));
  $('play').addEventListener('click', () => { if (state.timer) stopReplay(); else startReplay(); });
  $('speed').addEventListener('change', () => { if (state.timer) { stopReplay(); startReplay(); } });
  $('copy-link').addEventListener('click', async () => {
    const button = $('copy-link');
    try { await navigator.clipboard.writeText(location.href); button.textContent = 'Đã chép'; } catch { button.textContent = 'Không chép được'; }
    setTimeout(() => { button.textContent = 'Chép liên kết'; }, 1500);
  });
  document.addEventListener('keydown', onKey);
  $('compare-toggle').addEventListener('click', () => {
    const panel = $('compare');
    panel.hidden = !panel.hidden;
    $('compare-toggle').setAttribute('aria-expanded', String(!panel.hidden));
    renderCompare();
  });
  $('export-md').addEventListener('click', exportReport);
  // A link pasted into the address bar of an open page changes only the hash: follow it.
  window.addEventListener('hashchange', () => {
    const next = new URLSearchParams(location.hash.slice(1));
    const run = next.get('run');
    const pkg = next.get('pkg');
    if (run && run !== state.run && state.runs.includes(run)) {
      stopReplay();
      stopPolling();
      state.run = run;
      state.pkg = null;
      renderRunOptions();
      loadPackages(true, pkg);
    } else if (pkg && pkg !== state.pkg && state.packages.some((item) => item.package === pkg)) {
      selectPackage(pkg);
    }
  });
  loadPackages(true, params.get('pkg'));
}

init();
