// Read-only replay/live viewer. Trace content is untrusted: it only ever reaches the page through textContent.
// Shares the plain-language step text, the room/phase map and the rule ladder with the 3D office.
import {explainStep, previewOf} from '/office/explain.mjs';
import {roomFor} from '/office/events.mjs';
import {ruleLadder, ruleSentence, TERMS} from '/office/rules.mjs';
import {behaviorTriplet, extractSnippet, filterSummaryCases, fmtMetric, partitionRuns, pickDefaultRun, sandboxFromEvents} from '/summary.mjs';
import {icon, iconLabel, initPrefs} from '/ui.mjs';

const LABELS = {benign: 'Lành tính', suspicious: 'Đáng ngờ', malicious: 'Độc hại'};
const ACTIONS = {approve: 'Cho phép', review: 'Chuyển kiểm tra thủ công', deny: 'Từ chối'};
const SEVERITY = {high: 'Cao', medium: 'Trung bình', low: 'Thấp'};
const STATUS = {running: 'Đang chạy', done: 'Hoàn tất', error: 'Hết bước'};
const ERRORS = {
  json_invalid: 'JSON verdict không hợp schema', invalid_verdict: 'Verdict bị từ chối',
  truncated_output: 'Đầu ra mô hình bị cắt', repeated_invalid: 'Mô hình lặp cùng một verdict sai',
  bad_tool_call: 'Gọi công cụ không hợp lệ', model_error: 'Lỗi gọi mô hình', timeout: 'Hết thời gian chờ mô hình',
  manifest_error: 'Không đọc được manifest', invalid_script: 'Script cài đặt không phân tích được',
  decision_log: 'Không ghi được nhật ký quyết định', normalized_output: 'Đã chuẩn hóa định dạng đầu ra',
  evidence_mismatch: 'Bằng chứng không khớp nội dung dòng',
};
const PACKAGE_FILTERS = [['all', 'Tất cả'], ['malicious', 'Độc hại'], ['suspicious', 'Đáng ngờ'], ['benign', 'Lành tính'], ['error', 'Hết bước']];
const EVENT_FILTERS = [['all', 'Tất cả'], ['key', 'Bước quan trọng'], ['tool', 'Công cụ'], ['model', 'Mô hình'], ['problem', 'Lỗi']];
const ISSUE_FILTERS = [['disagree', 'Mô hình ≠ luật'], ['wrong', 'Sai nhãn chuẩn'], ['fake', 'Bằng chứng không có thật']];
const ISSUE_FLAGS = {disagree: 'mô hình ≠ luật', wrong: 'sai nhãn chuẩn', fake: 'bằng chứng giả'};
const CASE_FILTERS = [
  ['all_errors', 'Tất cả ca sai'],
  ['malicious_approved', 'Độc bị cho phép'],
  ['miss', 'Bỏ sót'],
  ['false_positive', 'Báo nhầm'],
  ['disagree', 'Mô hình ≠ luật'],
  ['error', 'Lỗi chạy'],
  ['all', 'Tất cả gói'],
];
const CASE_BADGES = {
  malicious_approved: ['Độc bị cho phép', 'bad'],
  miss: ['Bỏ sót', 'bad'],
  false_positive: ['Báo nhầm', 'warn'],
  disagree: ['Mô hình ≠ luật', 'warn'],
  error: ['Lỗi chạy', 'bad'],
};
const VARIANT = /(^|[-_])a-(llm|slm|tlm)(?=$|[-_])/i;
const POLL_MS = 1000;
const PHASES = [['Nhận diện', 'đọc manifest, script cài đặt'], ['Phân tích', 'đọc mã, tìm chỉ báo'],
  ['Kiểm chứng', 'bằng chứng file:dòng có thật?'], ['Quyết định', 'luật R1–R8, dry-run']];
const PHASE_OF_ROOM = {reception: 0, code: 1, intel: 1, lab: 1, evidence: 2, decision: 3};
const WHO = {model: 'Mô hình AI', tool: 'Công cụ', rules: 'Luật / kiểm tra', system: 'Hệ thống'};

const $ = (id) => document.getElementById(id);
const state = {
  run: null, pkg: null, events: [], extra: null, cursor: -1, timer: null, poll: null, live: false,
  phases: [], runs: [], packages: [], packageFilter: 'all', reviewed: new Set(), view: 'single',
  models: new Set(), eventFilter: 'all', issueFilter: null, truth: {},
  summarySplit: 'auto', summaryCache: new Map(), caseFilter: 'all_errors', caseQuery: '',
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
        preview: event.untrusted ? previewOf(event) || null : null, previewLabel: 'Dữ liệu mã gói — không tin cậy'};
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
  const keyTag = el('span', 'key-tag');
  keyTag.append(icon('flag'), document.createTextNode('quan trọng'));
  kind.append(keyTag);
  body.append(kind, el('p', `event-out${step.untrustedOutput ? ' untrusted' : ''}`, step.output || info.detail || ''));
  const flowWrap = el('div', 'flow-wrap');
  const flow = el('div', 'flow');
  for (const [label, text, untrusted] of [['Vào', step.input], ['Xử lý', step.process], ['Ra', step.output, step.untrustedOutput]]) {
    const part = el('div', untrusted ? 'untrusted' : null);
    part.append(el('small', null, label), el('span', null, text || '—'));
    flow.append(part);
  }
  flowWrap.append(flow);
  body.append(flowWrap);
  if (info.preview) {
    const block = el('details', 'source-block');
    const lines = String(info.preview).split('\n').length;
    block.append(el('summary', null, `${info.previewLabel} · ${lines} dòng`), el('pre', null, info.preview));
    body.append(block);
  }
  item.append(body, el('span', 'event-time', elapsed(event)));
  item.addEventListener('click', (click) => {
    if (click.target.closest('summary, pre')) return;
    jump(index);
  });
  return item;
}

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

function markLine(ok) {
  const span = el('span', `check ${ok ? 'yes' : 'no'}`);
  span.append(icon(ok ? 'check' : 'x'), document.createTextNode(ok ? 'có trong gói' : 'không tìm thấy'));
  return span;
}

function addJump(container, file) {
  if (!file) return;
  const index = state.events.findIndex((event) => event.type === 'tool_call' && event.args && event.args.file === file);
  if (index < 0) return;
  const button = el('button', 'link-button', `Xem bước đọc #${index + 1}`);
  button.type = 'button';
  button.addEventListener('click', () => {
    $('trace-collapse').open = true;
    jump(index + 1 < state.events.length ? index + 1 : index);
  });
  container.append(button);
}

// Render highlighted code lines extracted from trace read_file results (textContent only).
function renderSnippet(snippet) {
  const wrap = el('div', 'snippet-box');
  const caption = el('div', 'snippet-head');
  const rangeText = snippet.citedStart != null
    ? (snippet.citedEnd && snippet.citedEnd !== snippet.citedStart ? `dòng ${snippet.citedStart}–${snippet.citedEnd}` : `dòng ${snippet.citedStart}`)
    : 'trích đoạn';
  caption.append(el('span', null, `${snippet.file} (${rangeText})`),
    el('span', 'count', snippet.covers ? 'dữ liệu gói — không tin cậy' : 'không khớp dòng trích'));
  wrap.append(caption);
  const list = el('ol', 'code-lines');
  for (const row of snippet.lines) {
    const li = el('li', row.cited ? 'is-cited' : null);
    li.append(el('span', 'ln', String(row.num)), el('code', 'lc', row.text));
    list.append(li);
  }
  wrap.append(list);
  return wrap;
}

function renderSinglePackage() {
  const shown = state.events.slice(0, Math.max(0, state.cursor + 1));
  const start = state.events.find((event) => event.type === 'run_start') || {};
  const end = state.events.find((event) => event.type === 'run_end') || {};
  const decision = [...shown].reverse().find((event) => event.type === 'decision');
  const verdict = [...shown].reverse().find((event) => event.type === 'verdict' && event.valid);
  const extraResult = state.extra?.result;
  const truth = state.pkg ? state.truth[state.pkg] : null;

  // Subtitle: model, steps, elapsed, truth status
  const subParts = [];
  if (start.model || extraResult?.steps != null) {
    const steps = end.steps ?? extraResult?.steps;
    const secs = end.elapsed_s ?? extraResult?.elapsed_s;
    if (start.model) subParts.push(`Mô hình ${start.model}`);
    if (steps != null) subParts.push(`${steps} bước`);
    if (secs != null) subParts.push(`${secs} s`);
  }
  if (truth) {
    const finalLabel = decision?.final_label || extraResult?.decision?.label;
    const matchText = finalLabel ? (truth === finalLabel ? 'khớp nhãn chuẩn' : 'lệch nhãn chuẩn') : 'có nhãn chuẩn';
    subParts.push(`Nhãn chuẩn: ${LABELS[truth] ?? truth} (${matchText})`);
  }
  $('package-subtitle').textContent = subParts.join(' · ');

  const hero = $('verdict-hero');
  const grid = $('decision-grid');
  const behaviorsSec = $('behaviors-section');
  const signalsSec = $('signals-section');
  hero.replaceChildren();
  behaviorsSec.replaceChildren();
  signalsSec.replaceChildren();

  // Case 1: Package has no trace (e.g., extraction limit error from run_isolated)
  if (!state.events.length && extraResult) {
    hero.className = 'verdict-hero';
    hero.dataset.action = extraResult.decision?.action || 'review';
    const top = el('div', 'hero-top');
    const left = el('div', 'hero-main');
    const badgeRow = el('div', 'verdict-head');
    const lbl = extraResult.decision?.label || 'suspicious';
    const act = extraResult.decision?.action || 'review';
    badgeRow.append(el('span', `outcome ${lbl}`, LABELS[lbl] ?? lbl),
      el('span', `badge ${act}`, ACTIONS[act] ?? act),
      el('span', 'review-pill need', 'Cần người duyệt'));
    left.append(badgeRow, el('p', 'hero-desc', extraResult.error || 'Gói lỗi trước khi agent chạy (không có trace).'));
    top.append(left);
    hero.append(top, el('p', 'dry-note', 'Luật R2: lượt lỗi không bao giờ tự động cho phép.'));
    grid.hidden = true;
    behaviorsSec.hidden = true;
    renderSignalsSection(signalsSec, null);
    return;
  }

  if (!decision) {
    hero.className = 'verdict-hero pending';
    delete hero.dataset.action;
    hero.append(el('p', 'pending-copy', state.live ? 'Đang chờ quyết định…' : state.pkg ? 'Chưa tới bước quyết định ở mốc tua hiện tại' : 'Chọn một lượt chạy và một gói ở cột trái để xem kết luận, bằng chứng và luật quyết định.'));
    if (verdict) hero.append(el('p', 'outcome-meta', 'Mô hình đã nộp verdict; luật cứng chưa chạy ở bước đang xem.'));
    grid.hidden = true;
    behaviorsSec.hidden = true;
    signalsSec.hidden = true;
    return;
  }

  // Hero Verdict Card (10-second answer: kết luận gì, vì sao, cần người duyệt không)
  const proposal = verdict?.verdict;
  const label = ['benign', 'suspicious', 'malicious'].includes(decision.final_label) ? decision.final_label : '';
  const action = decision.final_action || '';
  const checks = decision.evidence_checks || [];
  const realChecks = checks.filter((c) => c.exists).length;
  const needHuman = action === 'review';
  const key = `${state.run}|${state.pkg}|${decision.seq}`;
  const fresh = key !== state.shownDecision;
  state.shownDecision = key;

  hero.className = `verdict-hero${fresh ? ' reveal' : ''}`;
  hero.dataset.action = action;

  const heroTop = el('div', 'hero-top');
  const heroMain = el('div', 'hero-main');
  const verdictHead = el('div', 'verdict-head');
  verdictHead.append(
    el('span', `outcome ${label}`, LABELS[decision.final_label] ?? decision.final_label ?? '?'),
    el('span', `badge ${action}`, ACTIONS[action] ?? action ?? 'không gọi lệnh'),
    el('span', `review-pill ${needHuman ? 'need' : 'auto'}`, needHuman ? 'Cần người duyệt' : 'Không cần duyệt (dry-run)')
  );
  heroMain.append(verdictHead);
  heroMain.append(el('p', 'hero-why', ruleSentence(decision.rule)));
  if (proposal?.description) {
    heroMain.append(el('p', 'hero-desc', `Mô tả của mô hình: ${proposal.description}`));
  }

  const heroStats = el('div', 'hero-stats');
  if (proposal) {
    const conf = Math.round((proposal.confidence ?? 0) * 100);
    const thr = decision.threshold ? Math.round(((decision.final_label === 'malicious' ? decision.threshold.deny : decision.threshold.approve) ?? 0.8) * 100) : null;
    const meterWrap = el('div', 'hero-stat');
    meterWrap.append(el('small', null, `Độ tin cậy mô hình${thr != null ? ` (ngưỡng ${thr}%)` : ''}`));
    const meter = el('div', 'confidence');
    const bar = el('meter');
    Object.assign(bar, {min: 0, max: 100, low: 50, high: 80, optimum: 100, value: conf});
    bar.setAttribute('aria-label', 'Độ tin cậy mô hình tự nêu');
    meter.append(bar, el('strong', null, `${conf}%`));
    meterWrap.append(meter);
    heroStats.append(meterWrap);
  }
  const evStat = el('div', 'hero-stat');
  evStat.append(el('small', null, 'Bằng chứng file:dòng'),
    el('strong', checks.length && realChecks === checks.length ? 'ok' : checks.length ? 'bad' : 'warn',
      checks.length ? `${realChecks}/${checks.length} có thật trong gói` : 'Không nêu vị trí'));
  heroStats.append(evStat);

  if (truth) {
    const truthStat = el('div', 'hero-stat');
    const ok = truth === decision.final_label;
    truthStat.append(el('small', null, 'Đối chiếu nhãn chuẩn'),
      el('strong', ok ? 'ok' : 'bad', `${LABELS[truth] ?? truth} (${ok ? 'Đúng' : 'Lệch'})`));
    heroStats.append(truthStat);
  }

  heroTop.append(heroMain, heroStats);
  hero.append(heroTop);

  const cmdText = action === 'approve' ? `npm approve-scripts ${state.pkg} (dry-run — không ghi package.json)`
    : action === 'deny' ? `npm deny-scripts ${state.pkg} (dry-run — không ghi package.json)`
    : 'Không chạy lệnh npm tự động — chuyển người xem đối chiếu bằng chứng bên dưới.';
  hero.append(el('p', 'dry-note', cmdText));

  // Decision grid: Rule card + Model vs Rule diff card
  grid.hidden = false;
  const ruleCard = $('rule-card');
  const diffCard = $('diff-card');
  ruleCard.replaceChildren();
  diffCard.replaceChildren();

  ruleCard.append(el('h2', 'card-title', 'Luật quyết định cuối cùng'));
  const ruleHeader = el('div', 'rule-header');
  ruleHeader.append(el('span', 'rule-pill', decision.rule || 'Không ghi'), el('span', 'rule-sentence-inline', ruleSentence(decision.rule)));
  ruleCard.append(ruleHeader);
  const rules = ruleLadder(decision.rule);
  const row = el('ol', 'rule-row');
  row.setAttribute('aria-label', 'Tám luật xét từ trái sang phải; luật khớp đầu tiên quyết định');
  for (const rule of rules) {
    const pill = el('li', rule.state, rule.code);
    pill.title = `${rule.code}: ${rule.when} — ${rule.state === 'fired' ? `KHỚP → ${rule.then}` : rule.state === 'skipped' ? 'không khớp' : 'không xét tới'}`;
    row.append(pill);
  }
  ruleCard.append(row);
  const more = el('details', 'ladder-more');
  more.open = Boolean(state.ladderOpen);
  more.addEventListener('toggle', () => { state.ladderOpen = more.open; });
  const ladder = el('ol', 'ladder');
  for (const rule of rules) {
    const item = el('li', rule.state);
    const mark = rule.state === 'fired' ? 'KHỚP' : rule.state === 'skipped' ? 'không khớp' : 'không xét';
    item.append(el('b', null, rule.code), el('span', null, rule.variant ? `${rule.when}. Bị giữ vì: ${rule.variant}` : rule.when),
      el('em', null, rule.state === 'fired' ? `${mark} → ${rule.then}` : mark));
    ladder.append(item);
  }
  more.append(el('summary', null, 'Xem 8 luật bằng lời'));
  more.append(ladder);
  if ((decision.reasons || []).length) {
    more.append(el('p', 'outcome-meta', `Chi tiết code ghi lại: ${decision.reasons.join('; ')}`));
  }
  ruleCard.append(more);

  diffCard.append(el('h2', 'card-title', 'Đề xuất mô hình vs Luật chốt'));
  const cmpGrid = el('div', 'diff-compare');
  const mBox = el('div', 'diff-box');
  mBox.append(el('small', null, 'Mô hình đề xuất'),
    el('strong', null, proposal ? `${LABELS[proposal.label] ?? proposal.label} · ${ACTIONS[proposal.action] ?? proposal.action}` : 'Không có verdict hợp lệ'),
    el('span', 'count', proposal ? `Tin cậy ${Math.round((proposal.confidence ?? 0) * 100)}%` : 'Lỗi định dạng / hết bước'));
  const rBox = el('div', 'diff-box');
  rBox.append(el('small', null, 'Luật cứng chốt'),
    el('strong', null, `${LABELS[decision.final_label] ?? decision.final_label} · ${ACTIONS[decision.final_action] ?? decision.final_action}`),
    el('span', 'count', decision.rule ? `Luật ${decision.rule}` : 'Luật mặc định'));
  cmpGrid.append(mBox, rBox);
  diffCard.append(cmpGrid);

  const sameLabel = proposal && proposal.label === decision.final_label;
  const sameAction = proposal && proposal.action === decision.final_action;
  if (!proposal) {
    diffCard.append(el('p', 'diff-banner bad', 'Mô hình không nộp được kết luận hợp lệ → Luật R2 chuyển người xem.'));
  } else if (sameLabel && sameAction) {
    diffCard.append(el('p', 'diff-banner ok', 'Luật giữ nguyên nhãn và hành động mô hình đề xuất.'));
  } else {
    diffCard.append(el('p', 'diff-banner warn',
      `Luật đã ghi đè đề xuất của mô hình (${LABELS[proposal.label] ?? proposal.label}/${ACTIONS[proposal.action] ?? proposal.action} → ${LABELS[decision.final_label] ?? decision.final_label}/${ACTIONS[decision.final_action] ?? decision.final_action}) theo ${decision.rule || 'luật an toàn'}.`));
  }

  // Behaviors section (Nguồn -> Hành động -> Đích + severity + file:dòng + code snippet highlighted)
  behaviorsSec.hidden = false;
  const behHead = el('div', 'section-head');
  behHead.append(el('h2', 'card-title', 'Hành vi và bằng chứng trong mã nguồn'));
  if (checks.length) behHead.append(el('span', 'count', `${realChecks}/${checks.length} vị trí đã xác minh`));
  behaviorsSec.append(behHead);

  if (proposal && (proposal.behaviors || []).length) {
    const list = el('div', 'behavior-cards');
    proposal.behaviors.forEach((behavior, idx) => {
      const check = checks[idx] || checks.find((c) => c.file === behavior.evidence?.file && c.lines === behavior.evidence?.lines);
      const card = el('article', `behavior-card${check && check.exists === false ? ' missing' : ''}`);
      const top = el('div', 'behavior-top');
      const sev = behavior.severity || 'low';
      top.append(el('span', `sev sev-${sev}`, `Mức ${SEVERITY[sev] ?? sev}`),
        el('strong', 'behavior-name', behavior.behavior || behavior.technique || 'Hành vi'),
        el('code', 'where-code', `${behavior.evidence?.file ?? '?'}:${behavior.evidence?.lines ?? '?'}`));
      if (check) top.append(markLine(Boolean(check.exists)));
      addJump(top, behavior.evidence?.file);
      card.append(top);

      // Triplet: Nguồn -> Hành động -> Đích
      const triplet = behaviorTriplet(behavior);
      const trip = el('div', 'triplet');
      for (const [k, v] of [['Nguồn', triplet.source], ['Hành động', triplet.action], ['Đích', triplet.target]]) {
        const cell = el('div', 'triplet-cell');
        cell.append(el('small', null, k), el('span', null, v));
        trip.append(cell);
      }
      card.append(trip);

      if (behavior.analysis) card.append(el('p', 'behavior-text', behavior.analysis));
      if (behavior.impact) card.append(el('p', 'behavior-impact', `Tác động: ${behavior.impact}`));
      if (check && check.exists === false && check.mismatch) {
        card.append(el('p', 'mismatch-note', `Kiểm chứng ngữ nghĩa từ chối: ${check.mismatch}`));
      }

      const snippet = extractSnippet(state.events, behavior.evidence?.file, behavior.evidence?.lines);
      if (snippet) card.append(renderSnippet(snippet));
      else card.append(el('p', 'outcome-meta', 'Không có trích đoạn read_file cho vị trí này trong trace.'));

      list.append(card);
    });
    behaviorsSec.append(list);

    if ((proposal.remediation || []).length) {
      const rem = el('div', 'remediation-box');
      rem.append(el('h3', null, 'Khuyến nghị xử lý'));
      const ul = el('ul');
      for (const r of proposal.remediation) ul.append(el('li', null, r));
      rem.append(ul);
      behaviorsSec.append(rem);
    }
  } else if (decision.rule === 'R2') {
    behaviorsSec.append(el('p', 'error-copy', 'Agent không nộp được verdict hợp lệ trong giới hạn bước; hệ thống dùng phương án an toàn (R2: chuyển người xem).'));
  } else {
    behaviorsSec.append(el('p', 'outcome-meta', 'Không có hành vi nào được mô hình nêu.'));
  }

  // Sandbox & OSV section
  renderSignalsSection(signalsSec, decision);
}

function renderSignalsSection(container, decision) {
  const traceSandbox = sandboxFromEvents(state.events);
  const extraSandbox = state.extra?.sandbox;
  const sandbox = traceSandbox || extraSandbox;
  const osv = state.extra?.osv;
  const inputs = decision?.inputs || null;
  const hasAny = Boolean(sandbox || osv || inputs?.osv_malicious || (inputs?.flow_risks || []).length || (inputs?.review_reasons || []).length);

  if (!hasAny) {
    container.hidden = true;
    return;
  }
  container.hidden = false;
  container.append(el('h2', 'card-title', 'Tín hiệu bổ trợ: Sandbox & OSV'));
  const grid = el('div', 'signals-grid');

  // OSV & Registry card
  const osvCard = el('div', 'signal-card');
  const osvTitle = el('div', 'signal-head');
  osvTitle.append(el('strong', null, 'OSV & npm Registry'));
  if (osv) {
    osvTitle.append(el('span', `signal-tag ${osv.used_in_run ? 'used' : 'ref'}`,
      osv.used_in_run ? 'Đã dùng khi chạy (R5)' : 'Đối chiếu sau (không cấp cho agent)'));
  }
  osvCard.append(osvTitle);
  if (osv) {
    osvCard.append(el('p', osv.malicious ? 'signal-bad' : 'signal-ok',
      osv.malicious ? `OSV gắn cờ MÃ ĐỘC (${(osv.vulns || []).length} cảnh báo)` : `OSV không báo MAL (${(osv.vulns || []).length} lỗ hổng/advisory khác)`));
    if ((osv.vulns || []).length) {
      const ul = el('ul', 'signal-list');
      for (const v of osv.vulns.slice(0, 4)) ul.append(el('li', null, `${v.id || '?'}: ${v.summary || ''}`));
      osvCard.append(ul);
    }
    if (osv.registry?.ok) {
      const reg = osv.registry;
      osvCard.append(el('p', 'outcome-meta',
        `Registry: ${reg.versions ?? '?'} phiên bản · ${reg.maintainers ?? '?'} maintainer · hook đổi so với bản trước (${reg.previous_version ?? '—'}): ${reg.hooks_changed_since_previous ? 'CÓ' : 'Không'}${reg.deprecated ? ' · ĐÃ DEPRECATED' : ''}`));
    }
  } else {
    osvCard.append(el('p', 'outcome-meta', inputs?.osv_malicious ? 'R5 ghi nhận tín hiệu OSV MAL.' : 'Không có dữ liệu OSV cho gói này.'));
  }
  grid.append(osvCard);

  // Sandbox card
  const sbxCard = el('div', 'signal-card');
  const sbxTitle = el('div', 'signal-head');
  sbxTitle.append(el('strong', null, 'Sandbox (VM / Container tắt mạng)'));
  if (sandbox) {
    sbxTitle.append(el('span', `signal-tag ${sandbox.used_in_run ? 'used' : 'ref'}`,
      sandbox.used_in_run ? 'Đã dùng khi chạy (R1/R7_sandbox)' : `Kết quả đối chiếu (${sandbox.source_dir || 'VM'})`));
  }
  sbxCard.append(sbxTitle);
  if (sandbox) {
    const touched = sandbox.canary_touched || [];
    sbxCard.append(el('p', touched.length ? 'signal-bad' : sandbox.ok ? 'signal-ok' : 'signal-warn',
      `Trạng thái: ${sandbox.outcome || (sandbox.ok ? 'ok' : 'lỗi')}${sandbox.fail_reason ? ` (${sandbox.fail_reason})` : ''} · Canary bị chạm: ${touched.length ? touched.join(', ') : 'Không'}`));
    const connects = sandbox.connects || [];
    const writes = sandbox.persistence_writes || [];
    const procs = (sandbox.process_tree || []).filter((p) => p.actor === 'package');
    sbxCard.append(el('p', 'outcome-meta',
      `Kết nối bị chặn: ${connects.length} · Ghi file khởi động: ${writes.length} · Tiến trình của gói: ${procs.length}`));
    if (procs.length) {
      const ul = el('ul', 'signal-list');
      for (const p of procs.slice(0, 4)) ul.append(el('li', null, (p.argv || []).join(' ')));
      sbxCard.append(ul);
    }
    if (sandbox.error) sbxCard.append(el('p', 'outcome-meta', `Lỗi sandbox: ${sandbox.error}`));
  } else {
    sbxCard.append(el('p', 'outcome-meta', 'Không có kết quả sandbox cho gói này.'));
  }
  grid.append(sbxCard);

  container.append(grid);

  // Extra static rule inputs if present (flow_risks, review_reasons)
  if (inputs && ((inputs.flow_risks || []).length || (inputs.review_reasons || []).length || (inputs.unexplained_risks || []).length)) {
    const notes = el('div', 'inputs-notes');
    for (const [title, arr] of [['Luồng dữ liệu nhạy cảm (R7_flow)', inputs.flow_risks],
      ['Lý do chưa xem hết (R7_review)', inputs.review_reasons],
      ['Dòng rủi ro chưa giải thích (R7_risk)', inputs.unexplained_risks]]) {
      if ((arr || []).length) notes.append(el('p', 'outcome-meta', `${title}: ${arr.join('; ')}`));
    }
    container.append(notes);
  }
}

function render(scroll = false) {
  const items = $('timeline').children;
  const forward = state.cursor > (state.lastCursor ?? -1);
  if (forward && items[state.cursor]) {
    items[state.cursor].classList.remove('arrive');
    void items[state.cursor].offsetWidth;
    items[state.cursor].classList.add('arrive');
  }
  if (state.lastCursor !== state.cursor) {
    const card = document.querySelector('.current-action');
    card.classList.remove('swap');
    void card.offsetWidth;
    card.classList.add('swap');
  }
  state.lastCursor = state.cursor;
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
  $('timeline').dataset.empty = !state.pkg ? 'Chọn một gói ở cột trái để xem từng bước agent đã làm.'
    : state.live ? 'Đang tải các bước của gói này…' : 'Trace của gói này chưa có bước nào.';

  const end = state.events.find((e) => e.type === 'run_end');
  $('trace-collapse-summary').textContent = state.events.length
    ? `Nhật ký điều tra từng bước · ${end?.steps ?? '?'} bước · ${state.events.length} sự kiện (bấm để mở/thu gọn)`
    : 'Nhật ký điều tra từng bước (không có trace)';

  renderPhaseTrack();
  const scrub = $('scrub');
  scrub.max = String(Math.max(0, state.events.length - 1));
  scrub.value = String(Math.max(0, state.cursor));
  scrub.disabled = state.events.length < 2;
  $('previous').disabled = state.cursor <= 0;
  $('next').disabled = state.cursor >= state.events.length - 1;
  $('play').disabled = state.events.length === 0;
  renderSinglePackage();
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
  $('trace-collapse').open = true;
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

async function fetchExtra(run, pkg) {
  try {
    const data = await getJson(`/api/package-extra?run=${encodeURIComponent(run)}&pkg=${encodeURIComponent(pkg)}`);
    if (run !== state.run || pkg !== state.pkg) return;
    state.extra = data;
    renderSinglePackage();
  } catch { /* optional extra metadata */ }
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
    // Package might be trace-less (e.g. extraction error recorded only in JSON result)
    if (!state.events.length && state.extra?.result) {
      state.live = false;
      setStatus('Hoàn tất (lỗi trước trace)');
      render();
      return;
    }
    setStatus('Mất kết nối', true);
    state.poll = setTimeout(() => poll(token), POLL_MS * 3);
  }
}

function linkFor(pkg) {
  return `run=${encodeURIComponent(state.run)}${pkg ? `&pkg=${encodeURIComponent(pkg)}` : ''}`;
}

function resetSingleView() {
  state.pkg = null;
  state.events = [];
  state.extra = null;
  state.phases = [];
  state.cursor = -1;
  state.live = false;
  $('package-name').textContent = 'Chưa chọn gói';
  $('package-subtitle').textContent = '';
  $('reviewed-toggle').checked = false;
  $('timeline').replaceChildren();
  render();
  renderModelPick(siblingsOf(state.run));
}

function selectPackage(pkg, keepView = false) {
  stopReplay();
  stopPolling();
  state.pkg = pkg;
  state.events = [];
  state.extra = null;
  state.phases = [];
  state.cursor = -1;
  state.live = true;
  $('timeline').replaceChildren();
  for (const button of document.querySelectorAll('.package')) {
    button.setAttribute('aria-current', String(button.dataset.pkg === pkg));
  }
  $('package-name').textContent = pkg;
  $('reviewed-toggle').checked = state.reviewed.has(reviewKey(pkg));
  if (!keepView && state.view === 'summary') setView('single');
  syncViewHash();
  $('office-link').href = `/office#mode=single&${linkFor(pkg)}`;
  render();
  fetchExtra(state.run, pkg);
  poll(pkg);
  if (state.view === 'single') renderModelPick(siblingsOf(state.run));
  renderCompare();
}

function chip(group, value, text, count, pressed, onPick) {
  const button = el('button', 'filter-chip');
  button.type = 'button';
  button.setAttribute('aria-pressed', String(pressed));
  if (value !== 'all' && group === 'label') button.append(el('span', `dot ${value}`));
  if (value === 'key') button.append(icon('flag'));
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
  const cell = (term, value, hint) => {
    const box = el('div', 'overview-cell');
    if (hint) box.title = hint;
    box.append(el('dt', null, term), el('dd', null, value));
    list.append(box);
  };
  cell('Đúng nhãn', judged.length ? `${Math.round(right / judged.length * 100)}% (${right}/${judged.length})` : '—',
    'So kết luận cuối với bộ nhãn chuẩn');
  cell('Bằng chứng thật', evidenceAll ? `${evidenceOk}/${evidenceAll}` : '—', 'Vị trí file:dòng mô hình trích có tồn tại trong gói');
  cell('Chuyển duyệt', `${review}/${items.length}`, 'Luật không đủ chắc để tự chặn hay cho phép');
  cell('TB tốc độ', average == null ? '—' : `${average.toFixed(1)} s/gói`);
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
        if (first >= 0) { $('trace-collapse').open = true; jump(first); }
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
  const select = $('issue-select');
  const opts = [new Option('Mọi trạng thái', '')];
  for (const [value, text] of [...ISSUE_FILTERS, ['unreviewed', 'Chưa xem']]) {
    const n = counts[value] || 0;
    const opt = new Option(`${text} (${n})`, value);
    opt.disabled = n === 0;
    opts.push(opt);
  }
  select.replaceChildren(...opts);
  select.value = state.issueFilter || '';
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
      if (seen) { const flag = el('span', 'flag seen'); flag.append(icon('check'), document.createTextNode('đã xem')); flags.append(flag); }
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
  if (state.view === 'summary') renderSummary();
  const target = wanted && packages.some((item) => item.package === wanted) ? wanted
    : selectFirst && packages.length ? packages[0].package : null;
  if (target) selectPackage(target, state.view === 'summary');
  else if (wanted && !packages.some((item) => item.package === wanted)) {
    // Deep-linked package without trace (e.g. extraction error)
    selectPackage(wanted, state.view === 'summary');
  } else if (!packages.length && selectFirst) {
    resetSingleView();
  }
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
  const {featured, other} = partitionRuns(matches);
  select.replaceChildren();
  const appendGroup = (label, names) => {
    if (!names.length) return;
    const group = document.createElement('optgroup');
    group.label = label;
    for (const run of names) group.append(new Option(run, run));
    select.append(group);
  };
  if (featured.length && other.length) {
    appendGroup('Lượt chính trình bày', featured);
    appendGroup('Thử nghiệm khác', other);
  } else {
    for (const run of [...featured, ...other]) select.append(new Option(run, run));
  }
  select.value = state.run;
  $('run-count').textContent = matches.length === state.runs.length ? `${state.runs.length}` : `${matches.length - (text && !state.run.toLowerCase().includes(text) ? 1 : 0)} / ${state.runs.length}`;
}

// --- Run Summary View (uses /api/runs/<run>/summary backed by experiments/metrics.py) ---------------
async function renderSummary() {
  const view = $('summary-view');
  if (view.hidden || !state.run) return;
  const run = state.run;
  const split = state.summarySplit || 'auto';
  const cacheKey = `${run}|${split}`;
  $('summary-title').textContent = `Tổng hợp: ${run}`;
  $('summary-meta').textContent = 'Đang tính số liệu từ experiments/metrics.py…';
  const body = $('summary-body');

  let data = state.summaryCache.get(cacheKey);
  if (!data) {
    body.replaceChildren(el('p', 'pending-copy', 'Đang nạp tổng hợp lượt chạy…'));
    try {
      data = await getJson(`/api/runs/${encodeURIComponent(run)}/summary?split=${encodeURIComponent(split)}`);
      state.summaryCache.set(cacheKey, data);
    } catch (error) {
      body.replaceChildren(el('p', 'error-copy', `Không nạp được tổng hợp: ${error.message}`));
      return;
    }
  }
  if (run !== state.run || $('summary-view').hidden) return;

  const meta = data.meta || {};
  const metaParts = [];
  if (meta.config_name) metaParts.push(`Cấu hình ${meta.config_name}`);
  if (meta.model) metaParts.push(meta.model);
  if (meta.deny_threshold != null) metaParts.push(`ngưỡng ${meta.deny_threshold}`);
  metaParts.push(`tập nhãn: ${data.split}`);
  metaParts.push(`OSV: ${meta.contexts_used ? 'có' : 'không'}`);
  metaParts.push(`Sandbox: ${meta.sandbox_used ? 'có' : 'không'}`);
  if (meta.resources?.container_peak_mb != null) metaParts.push(`RAM container đỉnh: ${meta.resources.container_peak_mb} MB`);
  $('summary-meta').textContent = metaParts.join(' · ');

  body.replaceChildren();
  const m = data.metrics || {};

  if ((m.scored ?? 0) > 0) {
    const malApp = data.malicious_approved ?? 0;
    const gdNote = data.guarddog ? ` · So GuardDog Recall ${fmtMetric(data.guarddog.recall)} (Agent ${fmtMetric(m.recall)})` : '';
    const proof = el('p', `summary-proof ${malApp === 0 ? 'ok' : 'bad'}`,
      malApp === 0
        ? `Chứng minh an toàn: 0 gói độc hại được tự động cho phép trên ${m.scored} gói chấm điểm · Recall ${fmtMetric(m.recall)} · F1 ${fmtMetric(m.f1)}${gdNote} · Luật R1–R8 (dry-run)`
        : `Cảnh báo: có ${malApp} gói độc hại bị cho phép trên ${m.scored} gói chấm điểm · Recall ${fmtMetric(m.recall)} · F1 ${fmtMetric(m.f1)}${gdNote}`);
    body.append(proof);
  }

  // 1. KPI cards
  const kpis = el('div', 'kpi-grid');
  const kpi = (label, value, tone, hint) => {
    const card = el('div', `kpi-card${tone ? ` ${tone}` : ''}`);
    if (hint) card.title = hint;
    card.append(el('small', null, label), el('strong', null, value));
    kpis.append(card);
  };
  kpi('Precision', fmtMetric(m.precision), null, 'TP / (TP + FP)');
  kpi('Recall', fmtMetric(m.recall), null, 'TP / (TP + FN)');
  kpi('F1', fmtMetric(m.f1), 'accent', 'Trung bình điều hòa P và R (dương = độc hoặc đáng ngờ)');
  kpi('FPR', fmtMetric(m.fpr), null, 'FP / (FP + TN)');
  kpi('Độc hại bị cho phép',
    data.suspicious_approved ? `${data.malicious_approved ?? 0} (đáng ngờ: ${data.suspicious_approved})` : String(data.malicious_approved ?? 0),
    (data.malicious_approved ?? 0) === 0 ? 'ok' : 'bad',
    'Số gói nhãn malicious có quyết định approve (phải bằng 0); trong ngoặc là gói suspicious được approve');
  kpi('Chuyển người xem', m.review_rate != null ? `${Math.round(m.review_rate * 100)}%` : '—');
  kpi('Lỗi chạy', m.error_rate != null ? `${Math.round(m.error_rate * 100)}%` : '—');
  kpi('Thời gian / bước TB', m.mean_seconds != null ? `${m.mean_seconds} s (${m.mean_steps ?? '?'} bước)` : '—',
    null, data.median_seconds != null ? `Trung vị: ${data.median_seconds} s/gói` : '');
  body.append(kpis);

  if (!data.has_results && !data.total_packages) {
    body.append(el('p', 'outcome-meta', 'Lượt chạy này chưa có file kết quả JSON để chấm điểm.'));
    return;
  }

  // 2. Two-column grid: Confusion Matrix + GuardDog Comparison
  const twoCol = el('div', 'summary-two');

  // Confusion Matrix
  const cmCard = el('section', 'panel-card');
  cmCard.append(el('h2', 'card-title', `Ma trận nhầm lẫn (${m.scored ?? 0} gói chấm điểm)`));
  if ((m.scored ?? 0) > 0) {
    const table = el('table', 'matrix-table');
    const thead = el('thead');
    const hr = el('tr');
    for (const h of ['Thực tế \\ Dự đoán', 'Lành tính', 'Đáng ngờ', 'Độc hại', 'Lỗi']) hr.append(el('th', null, h));
    thead.append(hr);
    table.append(thead);
    const tbody = el('tbody');
    for (const actual of ['benign', 'suspicious', 'malicious']) {
      const tr = el('tr');
      tr.append(el('th', null, `${LABELS[actual]} (${m.per_class?.[actual] ?? 0})`));
      for (const pred of ['benign', 'suspicious', 'malicious', 'error']) {
        const count = m.confusion?.[actual]?.[pred] ?? 0;
        const diag = actual === pred;
        const dangerous = actual !== 'benign' && pred === 'benign';
        const td = el('td', diag ? 'cell-diag' : dangerous && count ? 'cell-danger' : count ? 'cell-off' : null, String(count));
        tr.append(td);
      }
      tbody.append(tr);
    }
    table.append(tbody);
    cmCard.append(table);
    const b = m.binary || {};
    cmCard.append(el('p', 'outcome-meta',
      `Nhị phân (dương = độc hại hoặc đáng ngờ): TP = ${b.tp ?? 0} · FP = ${b.fp ?? 0} · TN = ${b.tn ?? 0} · FN = ${b.fn ?? 0}`));
  } else {
    cmCard.append(el('p', 'outcome-meta', 'Các gói trong lượt chạy này chưa khớp tập nhãn chuẩn hiện tại.'));
  }
  twoCol.append(cmCard);

  // GuardDog Comparison
  const gdCard = el('section', 'panel-card');
  gdCard.append(el('h2', 'card-title', 'So sánh với GuardDog 2.6.0'));
  if (data.guarddog) {
    const g = data.guarddog;
    const table = el('table', 'compare-table');
    const thead = el('thead');
    const hr = el('tr');
    for (const h of ['Chỉ số', meta.config_name || run, 'GuardDog', 'Chênh lệch']) hr.append(el('th', null, h));
    thead.append(hr);
    table.append(thead);
    const tbody = el('tbody');
    for (const [label, key, higherBetter] of [['Precision', 'precision', true], ['Recall', 'recall', true],
      ['F1', 'f1', true], ['FPR', 'fpr', false], ['Lỗi chạy', 'error_rate', false]]) {
      const tr = el('tr');
      const av = m[key];
      const gv = g[key];
      const diff = (av != null && gv != null) ? av - gv : null;
      const diffText = diff == null ? '—' : `${diff >= 0 ? '+' : ''}${diff.toFixed(3).replace('.', ',')}`;
      const good = diff != null && (higherBetter ? diff > 0 : diff < 0);
      tr.append(el('td', null, label), el('td', null, fmtMetric(av)), el('td', null, fmtMetric(gv)),
        el('td', good ? 'ok' : diff != null && diff !== 0 ? 'warn' : null, diffText));
      tbody.append(tr);
    }
    table.append(tbody);
    gdCard.append(table);
    gdCard.append(el('p', 'outcome-meta', `Nguồn GuardDog: reports/${data.guarddog_source} (${g.scored} gói cùng tập ${data.split}).`));
  } else {
    gdCard.append(el('p', 'outcome-meta', 'Không tìm thấy kết quả GuardDog tương ứng cho tập gói này.'));
  }
  twoCol.append(gdCard);
  body.append(twoCol);

  // 3. Rule Distribution
  const rulesCard = el('section', 'panel-card');
  rulesCard.append(el('h2', 'card-title', 'Phân bố luật quyết định (R1–R8)'));
  const totalRules = (data.rules || []).reduce((s, r) => s + r.total, 0) || 1;
  const ruleList = el('ul', 'rule-dist');
  for (const r of data.rules || []) {
    const li = el('li');
    const pct = Math.round(r.total / totalRules * 100);
    li.append(el('code', 'rule-pill', r.rule));
    const barWrap = el('div', 'rule-bar-wrap');
    const bar = el('div', 'rule-bar');
    bar.style.width = `${Math.max(2, pct)}%`;
    barWrap.append(bar);
    li.append(barWrap, el('span', 'rule-stat', `${r.total} gói (${pct}%)`),
      el('small', 'count', `chặn ${r.deny} · xem ${r.review} · duyệt ${r.approve}`));
    ruleList.append(li);
  }
  rulesCard.append(ruleList);
  body.append(rulesCard);

  // 4. Filterable Error Cases
  const casesCard = el('section', 'panel-card');
  const casesHead = el('div', 'section-head');
  casesHead.append(el('h2', 'card-title', 'Danh sách ca sai & cần chú ý'));
  const search = el('input', 'case-search');
  search.type = 'search';
  search.placeholder = 'Tìm gói, luật, lý do…';
  search.value = state.caseQuery;
  search.setAttribute('aria-label', 'Lọc danh sách ca sai');
  casesHead.append(search);
  casesCard.append(casesHead);

  const chipRow = el('div', 'chips');
  const counts = {};
  for (const c of data.cases || []) for (const k of c.kinds || []) counts[k] = (counts[k] || 0) + 1;
  counts.all_errors = (data.cases || []).filter((c) => (c.kinds || []).some((k) => ['malicious_approved', 'miss', 'false_positive', 'error'].includes(k))).length;
  counts.all = (data.cases || []).length;

  const tbody = el('tbody');
  const countLabel = el('p', 'outcome-meta');
  const renderCases = () => {
    const rows = filterSummaryCases(data.cases, state.caseFilter, state.caseQuery);
    countLabel.textContent = `Hiển thị ${rows.length} / ${(data.cases || []).length} gói`;
    tbody.replaceChildren(...rows.slice(0, 300).map((c) => {
      const tr = el('tr');
      tr.append(el('td', 'mono-cell', c.package));
      const tagsCell = el('td');
      for (const k of c.kinds || []) {
        const [labelText, cls] = CASE_BADGES[k] || [k, ''];
        tagsCell.append(el('span', `case-tag ${cls}`, labelText));
      }
      if (!(c.kinds || []).length) tagsCell.append(el('span', 'count', 'đúng'));
      tr.append(tagsCell);
      tr.append(el('td', null, c.expected ? (LABELS[c.expected] ?? c.expected) : '—'));
      tr.append(el('td', null, c.proposal_label ? `${LABELS[c.proposal_label] ?? c.proposal_label}${c.confidence != null ? ` (${Math.round(c.confidence * 100)}%)` : ''}` : '—'));
      tr.append(el('td', null, `${LABELS[c.label] ?? c.label ?? '—'} · ${ACTIONS[c.action] ?? c.action ?? '—'}${c.rule ? ` (${c.rule})` : ''}`));
      tr.append(el('td', 'count', `${c.steps ?? '—'} · ${c.elapsed_s ?? '—'} s`));
      const actCell = el('td');
      const openBtn = el('button', 'link-button', c.has_trace ? 'Xem chi tiết' : 'Xem lỗi');
      openBtn.type = 'button';
      openBtn.addEventListener('click', () => {
        setView('single');
        selectPackage(c.package);
      });
      actCell.append(openBtn);
      tr.append(actCell);
      return tr;
    }));
  };

  for (const [val, labelText] of CASE_FILTERS) {
    const b = chip('case', val, labelText, counts[val] || 0, state.caseFilter === val, (picked) => {
      state.caseFilter = picked;
      for (const child of chipRow.children) child.setAttribute('aria-pressed', String(child.dataset.val === picked));
      renderCases();
    });
    b.dataset.val = val;
    chipRow.append(b);
  }
  search.addEventListener('input', () => { state.caseQuery = search.value; renderCases(); });

  casesCard.append(chipRow, countLabel);
  const tableWrap = el('div', 'table-scroll');
  const table = el('table', 'compare-table');
  const thead = el('thead');
  const hr = el('tr');
  for (const h of ['Gói', 'Phân loại', 'Nhãn chuẩn', 'Mô hình đề xuất', 'Luật chốt', 'Bước · giây', '']) hr.append(el('th', null, h));
  thead.append(hr);
  table.append(thead, tbody);
  tableWrap.append(table);
  casesCard.append(tableWrap);
  renderCases();
  body.append(casesCard);
}

// --- Compare View ---------------------------------------------------------------------------------
async function renderCompare() {
  const panel = $('compare');
  const pkg = state.pkg;
  if (panel.hidden || !pkg) return;
  const body = $('compare-body');
  body.replaceChildren();
  const allSiblings = siblingsOf(state.run);
  renderModelPick(allSiblings);
  const siblings = allSiblings.filter((run) => !state.models.size || state.models.has(variantOf(run)));
  renderSide(siblings);
  const group = state.run.replace(VARIANT, '$1a-*');
  $('compare-note').textContent = siblings.length > 1
    ? `Cùng gói ${pkg} trong ${siblings.length} run chỉ khác cỡ mô hình. Ô màu vàng: khác với run đang xem.`
    : VARIANT.test(state.run)
      ? 'Không có run nào khác chỉ khác cỡ mô hình với run này, nên chưa có gì để so.'
      : 'Run này không thuộc bộ a-llm / a-slm / a-tlm. Chọn một run có hậu tố đó để so 3 cỡ mô hình.';
  const rows = await Promise.all(siblings.map(async (run) => {
    try {
      const list = await getJson(`/api/runs/${encodeURIComponent(run)}/packages`);
      return {run, item: list.find((entry) => entry.package === pkg)};
    } catch { return {run, item: null}; }
  }));
  if (!panel.hidden && pkg === state.pkg) {
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
        link.href = `#run=${encodeURIComponent(run)}&pkg=${encodeURIComponent(pkg)}`;
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
      race.href = `/office#mode=compare&run=${encodeURIComponent(group)}&pkg=${encodeURIComponent(pkg)}`;
      td.append(race);
      row.append(td);
      body.append(row);
    }
  }
}

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

function variantOf(run) {
  const match = VARIANT.exec(run);
  return match ? match[2].toUpperCase() : run;
}

function siblingsOf(run) {
  const order = {LLM: 0, SLM: 1, TLM: 2};
  return (VARIANT.test(run) ? state.runs.filter((other) => other.replace(VARIANT, '$1a-*') === run.replace(VARIANT, '$1a-*')) : [run])
    .sort((a, b) => (order[variantOf(a)] ?? 9) - (order[variantOf(b)] ?? 9));
}

function switchModel(run) {
  if (run === state.run) return;
  stopReplay();
  stopPolling();
  const pkg = state.pkg;
  state.run = run;
  renderRunOptions();
  loadPackages(true, pkg);
}

function renderModelPick(siblings) {
  const box = $('model-pick');
  box.hidden = siblings.length < 2 || state.view === 'summary';
  if (box.hidden) return;
  if (state.view === 'single') {
    box.replaceChildren(el('span', 'field-label', 'Model cần xem:'), ...siblings.map((run) => {
      const variant = variantOf(run);
      const label = el('label', 'toggle model-toggle');
      label.dataset.variant = variant;
      const input = el('input');
      input.type = 'radio';
      input.name = 'one-model';
      input.checked = run === state.run;
      input.title = run;
      input.addEventListener('change', () => switchModel(run));
      label.append(input, el('span', null, `A-${variant}`));
      return label;
    }), el('small', 'count', 'cùng gói, đổi cỡ mô hình'));
    return;
  }
  const active = siblings.filter((run) => !state.models.size || state.models.has(variantOf(run))).map(variantOf);
  box.replaceChildren(el('span', 'field-label', 'Model:'), ...siblings.map((run) => {
    const variant = variantOf(run);
    const label = el('label', 'toggle model-toggle');
    label.dataset.variant = variant;
    const input = el('input');
    input.type = 'checkbox';
    input.checked = active.includes(variant);
    input.title = run;
    input.addEventListener('change', () => {
      const next = [...box.querySelectorAll('input')].filter((item) => item.checked);
      if (!next.length) { input.checked = true; return; }
      state.models = new Set(next.map((item) => item.parentElement.dataset.variant));
      syncViewHash();
      renderCompare();
    });
    label.append(input, el('span', null, `A-${variant}`));
    return label;
  }), el('small', 'count', '1 model: xem riêng · 2–3 model: chạy cùng lúc, cạnh nhau'));
}

async function renderSide(runs) {
  const side = $('side');
  const pkg = state.pkg;
  const traces = await Promise.all(runs.map(async (run) => {
    try { return {run, events: await getJson(`/api/trace?run=${encodeURIComponent(run)}&pkg=${encodeURIComponent(pkg)}&after=-1`)}; }
    catch { return {run, events: []}; }
  }));
  if (pkg !== state.pkg) return;
  stopSide();
  sidePlay.columns = [];
  side.style.setProperty('--columns', String(Math.max(1, traces.length)));
  side.replaceChildren(...traces.map(({run, events}) => {
    const t0 = Date.parse(events[0]?.ts);
    const at = (event) => { const t = Date.parse(event?.ts); return Number.isNaN(t) || Number.isNaN(t0) ? 0 : (t - t0) / 1000; };
    const column = el('article', 'side-col');
    column.dataset.variant = variantOf(run);
    const start = events.find((event) => event.type === 'run_start');
    const decision = events.find((event) => event.type === 'decision');
    const end = events.find((event) => event.type === 'run_end');
    const head = el('header');
    const status = el('span', 'side-status', '');
    head.append(el('strong', null, `A-${variantOf(run)}`), el('span', 'count', `${start?.model ?? '?'} · ${end ? `${end.steps} bước · ${end.elapsed_s} s` : 'chưa xong'}`), status);
    column.append(head);
    if (!events.length) { column.append(el('p', 'empty', 'Run này không có gói đang xem.')); return column; }
    const result = el('div', 'side-result');
    const waiting = el('p', 'side-waiting', 'Đang điều tra… kết luận hiện khi tới bước quyết định.');
    column.append(result, waiting);
    if (decision) {
      const label = ['benign', 'suspicious', 'malicious'].includes(decision.final_label) ? decision.final_label : '';
      const verdictHead = el('div', 'verdict-head');
      verdictHead.append(el('p', `outcome ${label}`, LABELS[decision.final_label] ?? decision.final_label),
        el('span', `badge ${decision.final_action ?? ''}`, ACTIONS[decision.final_action] ?? decision.final_action));
      const checks = decision.evidence_checks || [];
      result.append(verdictHead, el('p', 'side-rule', ruleSentence(decision.rule)),
        el('p', 'count', checks.length ? `Bằng chứng: ${checks.filter((check) => check.exists).length}/${checks.length} vị trí có thật` : 'Không nêu bằng chứng'));
    } else {
      result.append(el('p', 'pending-copy', 'Chưa có quyết định'));
    }
    const steps = el('ol', 'side-steps');
    const items = [];
    events.forEach((event, index) => {
      const step = explainStep(events, index);
      const key = ['verdict', 'decision', 'error', 'limit'].includes(event.type);
      const item = el('li', key ? 'key' : null);
      items.push({item, t: at(event)});
      const title = el('b', null, step.title);
      if (key) title.append(icon('flag', 'bước quan trọng'));
      item.append(title, el('span', step.untrustedOutput ? 'untrusted' : null, step.output));
      steps.append(item);
    });
    column.append(steps);
    sidePlay.columns.push({items, list: steps, result, waiting, status, decisionAt: decision ? at(decision) : Infinity,
      endAt: end ? at(end) : (items.at(-1)?.t ?? 0)});
    if (run !== state.run) {
      const open = el('a', 'link-button', 'Mở model này ở chế độ Chi tiết một gói');
      open.href = `#run=${encodeURIComponent(run)}&pkg=${encodeURIComponent(pkg)}`;
      open.addEventListener('click', () => setView('single'));
      column.append(open);
    }
    return column;
  }));
  sidePlay.duration = Math.max(0.1, ...sidePlay.columns.map((column) => column.endAt));
  $('side-scrub').max = String(sidePlay.duration);
  setSideClock(sidePlay.duration);
}

const sidePlay = {columns: [], duration: 0, clock: 0, timer: null};

function setSideClock(clock) {
  sidePlay.clock = Math.min(clock, sidePlay.duration);
  for (const column of sidePlay.columns) {
    let now = null;
    for (const {item, t} of column.items) {
      const shown = t <= sidePlay.clock + 1e-6;
      item.classList.toggle('later', !shown);
      item.classList.remove('now');
      if (shown) now = item;
    }
    now?.classList.add('now');
    if (now && sidePlay.timer) column.list.scrollTop = now.offsetTop - column.list.offsetTop - column.list.clientHeight / 2;
    const decided = sidePlay.clock >= column.decisionAt;
    column.result.hidden = !decided;
    column.waiting.hidden = decided;
    const done = sidePlay.clock >= column.endAt;
    column.status.textContent = done ? `xong lúc ${column.endAt.toFixed(1)} s` : `đang chạy · bước ${column.items.filter(({t}) => t <= sidePlay.clock).length}`;
    column.status.classList.toggle('running', !done);
  }
  $('side-scrub').value = String(sidePlay.clock);
  $('side-clock').textContent = `${sidePlay.clock.toFixed(1)} / ${sidePlay.duration.toFixed(1)} s`;
}

function stopSide() {
  clearInterval(state.timer);
  clearInterval(sidePlay.timer);
  sidePlay.timer = null;
  iconLabel($('side-play'), 'play', 'Phát cùng lúc');
}

function playSide() {
  if (sidePlay.timer) { stopSide(); return; }
  if (sidePlay.clock >= sidePlay.duration) setSideClock(0);
  iconLabel($('side-play'), 'pause', 'Tạm dừng');
  let last = performance.now();
  sidePlay.timer = setInterval(() => {
    const now = performance.now();
    setSideClock(sidePlay.clock + (now - last) / 1000 * Number($('side-speed').value));
    last = now;
    if (sidePlay.clock >= sidePlay.duration) stopSide();
  }, 100);
}

function setView(view) {
  state.view = view;
  document.body.dataset.view = view;
  for (const button of document.querySelectorAll('.view-mode button')) button.setAttribute('aria-checked', String(button.dataset.view === view));
  $('single-view').hidden = view !== 'single';
  $('summary-view').hidden = view !== 'summary';
  $('compare').hidden = view !== 'compare';
  if (view !== 'compare') stopSide();
  syncViewHash();
  if (state.run) renderModelPick(siblingsOf(state.run));
  if (view === 'summary') renderSummary();
  if (view === 'compare') renderCompare();
}

function syncViewHash() {
  if (!state.run) return;
  const extra = state.view === 'compare'
    ? `&view=compare${state.models.size ? `&models=${[...state.models].join(',')}` : ''}`
    : state.view === 'summary' ? '&view=summary' : '';
  history.replaceState(null, '', `#${linkFor(state.pkg)}${extra}`);
}

function onKey(event) {
  const target = event.target instanceof Element ? event.target : document.body;
  if (event.ctrlKey || event.metaKey || event.altKey || target.closest('input, select, textarea')) return;
  if (event.key === ' ' && target.closest('button, summary')) return;
  const keys = {
    ArrowLeft: () => { $('trace-collapse').open = true; jump(state.cursor - 1); },
    ArrowRight: () => { $('trace-collapse').open = true; jump(state.cursor + 1); },
    Home: () => { $('trace-collapse').open = true; jump(0); },
    End: () => { $('trace-collapse').open = true; jump(state.events.length - 1); },
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
  about.open = remember('about') === '1';
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
  state.run = runs.includes(params.get('run')) ? params.get('run') : pickDefaultRun(runs);
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
  $('issue-select').addEventListener('change', (event) => {
    state.issueFilter = event.target.value || null;
    applyPackageFilter();
  });
  $('previous').addEventListener('click', () => jump(state.cursor - 1));
  $('next').addEventListener('click', () => jump(state.cursor + 1));
  $('scrub').addEventListener('input', (event) => jump(Number(event.target.value)));
  $('play').addEventListener('click', () => { if (state.timer) stopReplay(); else startReplay(); });
  $('speed').addEventListener('change', () => { if (state.timer) { stopReplay(); startReplay(); } });
  $('summary-split').addEventListener('change', (event) => { state.summarySplit = event.target.value; renderSummary(); });
  $('copy-link').addEventListener('click', async () => {
    const button = $('copy-link');
    try { await navigator.clipboard.writeText(location.href); button.textContent = 'Đã chép'; } catch { button.textContent = 'Không chép được'; }
    setTimeout(() => { button.textContent = 'Chép liên kết'; }, 1500);
  });
  document.addEventListener('keydown', onKey);
  for (const button of document.querySelectorAll('.view-mode button')) button.addEventListener('click', () => setView(button.dataset.view));
  state.models = new Set((params.get('models') || '').split(',').filter((name) => ['LLM', 'SLM', 'TLM'].includes(name)));
  const askedView = params.get('view');
  setView(askedView === 'compare' ? 'compare' : askedView === 'summary' ? 'summary' : 'single');
  $('side-play').addEventListener('click', playSide);
  $('side-scrub').addEventListener('input', (event) => { stopSide(); setSideClock(Number(event.target.value)); });
  $('export-md').addEventListener('click', () => { exportReport(); document.querySelector('.share-menu').open = false; });
  document.addEventListener('click', (event) => {
    for (const menu of document.querySelectorAll('details.menu[open]')) if (!menu.contains(event.target)) menu.open = false;
  });
  window.addEventListener('hashchange', () => {
    const next = new URLSearchParams(location.hash.slice(1));
    const run = next.get('run');
    const pkg = next.get('pkg');
    const v = next.get('view');
    if (v && ['single', 'summary', 'compare'].includes(v) && v !== state.view) setView(v);
    if (run && run !== state.run && state.runs.includes(run)) {
      stopReplay();
      stopPolling();
      state.run = run;
      state.pkg = null;
      renderRunOptions();
      loadPackages(true, pkg);
    } else if (pkg && pkg !== state.pkg) {
      selectPackage(pkg);
    }
  });
  loadPackages(true, params.get('pkg'));
}

init();
