// 3D office page: replays one run, or races A-LLM/A-SLM/A-TLM on the same package, on the real
// clock of each trace (timestamps). Every string from a trace is untrusted and reaches the page
// with textContent only.
import { createOffice } from "./scene.mjs";
import { ROOMS, roomFor } from "./events.mjs";

const $ = (id) => document.getElementById(id);
const PHASE = { reception: 0, code: 1, intel: 1, lab: 1, evidence: 2, decision: 3 };
const ACTIONS = { approve: "Cho phép", review: "Chuyển người xem", deny: "Từ chối" };
const STAMPS = { approve: "CHO PHÉP", review: "NGƯỜI XEM", deny: "TỪ CHỐI" };
const STAMP_ICONS = { approve: "✔", review: "👁", deny: "✘" }; // race mode: three stamps must fit side by side
const LABELS = { benign: "Lành tính", suspicious: "Nghi vấn", malicious: "Độc hại" };
const VARIANT = /(^|[-_])a-(llm|slm|tlm)(?=$|[-_])/i;
const VARIANT_COLORS = { LLM: "#61e8c2", SLM: "#7cc4ff", TLM: "#ffb86b" };
const ROOM_COLORS = { reception: "#61e8c2", code: "#7cc4ff", intel: "#b79cff", lab: "#8a98a8",
                      evidence: "#ffd08a", decision: "#ff8e83", hallway: "#6f8597" };
const MIN_DWELL = 0.6;      // wall seconds a worker stays on one event, so instant tool bursts stay visible
const THINKING_AFTER = 0.8; // trace seconds of silence before a worker is shown "thinking"

const params = new URLSearchParams(location.hash.slice(1));
const office = createOffice($("office-canvas"), $("room-labels"), $("worker-layer"));
office.stats.continuous = params.get("bench") === "1"; // O-0: continuous render to measure FPS
window.__office = office; // read-only handle for measurements in the browser console

let lanes = [];
let closeUp = null;
const clock = { t: 0, duration: 0, rate: 4, playing: false, last: 0 };

async function getJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function element(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}

const clip = (text, length) => (text.length > length ? `${text.slice(0, length - 1)}…` : text);
const seconds = (value) => `${value.toFixed(1)} s`;

function argsText(args) {
  if (!args || typeof args !== "object" || !args.file) return "";
  return `${args.file}${args.start ? `:${args.start}${args.end && args.end !== args.start ? `-${args.end}` : ""}` : ""}`;
}

function describe(event) {
  switch (event.type) {
    case "run_start": return `Bắt đầu phân tích với ${event.model}`;
    case "tool_call": return `Gọi ${event.tool} ${argsText(event.args)}`.trim();
    case "tool_result": return `${event.tool}: ${event.ok ? event.summary || "OK" : `lỗi — ${event.summary || ""}`}`;
    case "error": return `Sự cố ${event.kind}: ${event.message || ""}`;
    case "verdict": return event.valid ? "Mô hình nộp kết luận hợp lệ" : "Kết luận chưa hợp lệ, phải sửa";
    case "decision": return `${LABELS[event.final_label] || event.final_label} → ${ACTIONS[event.final_action] || "—"} (luật ${event.rule})`;
    case "run_end": return `Kết thúc: ${event.steps} bước, ${event.elapsed_s} giây`;
    case "limit": return "Hết giới hạn bước, chuyển người xem";
    default: return event.type;
  }
}

function bubbleText(event) {
  if (event.type === "tool_call") return clip(`${event.tool} ${argsText(event.args)}`.trim(), 32);
  if (event.type === "tool_result") return clip(`${event.tool}: ${event.ok ? "xong" : "lỗi"}`, 32);
  if (event.type === "verdict") return event.valid ? "Nộp kết luận" : "Sửa kết luận";
  if (event.type === "decision") return ACTIONS[event.final_action] || "Quyết định";
  if (event.type === "error") return clip(`Vấp: ${event.kind}`, 32);
  if (event.type === "run_end") return "Xong";
  if (event.type === "run_start") return "Nhận gói";
  return "";
}

// --- lanes: one worker replaying one trace -------------------------------------------------------
function variantOf(run) {
  const match = run.match(VARIANT);
  return match ? match[2].toUpperCase() : null;
}

async function makeLane(run, pkg, index) {
  const query = new URLSearchParams({ run, pkg, after: "-1" });
  const events = (await getJson(`/api/trace?${query}`)).filter((event) => event.type !== "thought");
  const times = events.map((event) => Date.parse(event.ts));
  const start = Number.isFinite(times[0]) ? times[0] : 0;
  const offsets = times.map((time, at) => (Number.isFinite(time) ? (time - start) / 1000 : at));
  const variant = variantOf(run);
  const model = events.find((event) => event.type === "run_start")?.model || "agent";
  const name = variant ? `A-${variant}` : model;
  const color = VARIANT_COLORS[variant] || "#61e8c2";
  return { run, pkg, events, offsets, rooms: events.map(roomFor), variant, model, name, color, index: -1,
           shownAt: 0, finishedAt: null, actor: office.addWorker({ id: run, name, color, lane: index }) };
}

function decisionOf(lane, upTo = lane.index) {
  return lane.events.slice(0, upTo + 1).reverse().find((event) => event.type === "decision");
}

// Advance a lane to the clock; scrubbing jumps, playing steps one event at a time with a short dwell.
function advance(lane, now, scrubbing) {
  let target = -1;
  while (target + 1 < lane.events.length && lane.offsets[target + 1] <= clock.t) target += 1;
  if (target === lane.index) return false;
  const jump = scrubbing || target < lane.index;
  const next = jump ? target : lane.index + 1;
  if (!jump && now - lane.shownAt < MIN_DWELL * 1000) return false;
  lane.index = next;
  lane.shownAt = now;
  const event = lane.events[next];
  lane.actor.walkTo(lane.rooms[next], jump);
  lane.actor.say(bubbleText(event));
  const decision = decisionOf(lane);
  const stampText = !decision ? "" : lanes.length > 1
    ? `${STAMP_ICONS[decision.final_action] || "?"} ${decision.rule}` : `${STAMPS[decision.final_action] || "?"} · ${decision.rule}`;
  lane.actor.stamp(decision?.final_action, stampText,
                   event.type === "decision" && !jump);
  if (event.type === "decision" && !jump) {
    office.celebrate(event.final_action);
    // Director: a short close-up on the verdict, then back to the whole floor (others may still work).
    office.focus("decision", 0.62);
    clearTimeout(closeUp);
    closeUp = setTimeout(() => office.focus(lanes.length > 1 ? null : lane.rooms[lane.index], 0.78), 2600);
  } else if (!jump && lanes.length === 1) {
    office.focus(lane.rooms[next], 0.72);
  }
  lane.finishedAt = event.type === "run_end" ? lane.offsets[next] : null;
  return true;
}

function thinking(lane) {
  const next = lane.events[lane.index + 1];
  if (!next || !["tool_call", "verdict"].includes(next.type)) return false;
  return clock.t - (lane.offsets[lane.index] ?? 0) > THINKING_AFTER;
}

// --- rendering of the side panel ---------------------------------------------------------------
function renderBoard() {
  const finished = lanes.filter((lane) => lane.finishedAt !== null).sort((a, b) => a.finishedAt - b.finishedAt);
  $("board").replaceChildren(...lanes.map((lane) => {
    const card = element("li", undefined, "lane-card");
    card.style.setProperty("--worker", lane.color);
    const decision = decisionOf(lane);
    const event = lane.events[lane.index];
    const clockText = seconds(Math.min(clock.t, lane.offsets.at(-1) ?? 0));
    const rank = finished.indexOf(lane);
    const head = element("div", undefined, "lane-head");
    head.append(element("strong", lane.name), element("span", lane.model, "count"),
                element("span", rank >= 0 ? `#${rank + 1} · ${seconds(lane.finishedAt)}` : clockText, rank >= 0 ? "rank" : "lane-clock"));
    const steps = lane.events.slice(0, lane.index + 1).filter((item) => item.type === "tool_call").length;
    const status = thinking(lane) ? "đang suy nghĩ…" : event ? clip(describe(event), 70) : "chờ bắt đầu";
    const verdict = element("p", decision ? `${LABELS[decision.final_label] || decision.final_label} · ${ACTIONS[decision.final_action] || "—"} · ${decision.rule}` : "Chưa quyết định", "lane-decision");
    verdict.dataset.action = decision?.final_action || "";
    card.append(head, element("p", `${steps} lần gọi công cụ · ${status}`, "count"), verdict);
    return card;
  }));
}

function renderDetail(lane) {
  const decision = decisionOf(lane);
  const verdicts = lane.events.slice(0, lane.index + 1).filter((event) => event.type === "verdict");
  const proposal = (verdicts.reverse().find((event) => event.valid) || verdicts[0])?.verdict;
  $("decision").textContent = decision ? `${LABELS[decision.final_label] || decision.final_label} · ${ACTIONS[decision.final_action] || "—"} · luật ${decision.rule}` : "Chưa có quyết định";
  $("decision").dataset.action = decision?.final_action || "";
  $("reasons").replaceChildren(...(decision?.reasons || []).map((reason) => element("li", reason)));
  $("proposal").textContent = proposal
    ? `${LABELS[proposal.label] || proposal.label} · tin cậy ${Math.round((proposal.confidence ?? 0) * 100)}% — ${proposal.description || ""}`
    : "Chưa có đề xuất";
  $("behaviors").replaceChildren(...(proposal?.behaviors || []).slice(0, 4).map((behavior) => {
    const item = element("li");
    item.append(element("span", behavior.severity || "", `sev sev-${behavior.severity}`), element("span", `${behavior.behavior} `),
                element("code", `${behavior.evidence?.file}:${behavior.evidence?.lines}`));
    return item;
  }));
  const checks = decision?.evidence_checks || [];
  $("checks").replaceChildren(...(checks.length ? checks.map((check) => {
    const item = element("li", undefined, check.exists ? "ok" : "bad");
    item.append(element("span", check.exists ? "✔ " : "✘ "), element("code", `${check.file}:${check.lines}`));
    return item;
  }) : [element("li", decision ? "Không có bằng chứng để kiểm" : "Chưa kiểm", "count")]));
  document.querySelectorAll(".log-item").forEach((button, at) => {
    button.classList.toggle("current", at === lane.index);
    button.classList.toggle("past", at < lane.index);
    if (at === lane.index && clock.playing) {
      // Scroll the log box only; scrollIntoView would move the whole page away from the 3D view.
      const log = $("event-log");
      const top = button.offsetTop - log.offsetTop;
      if (top < log.scrollTop || top + button.offsetHeight > log.scrollTop + log.clientHeight) {
        log.scrollTop = top - log.clientHeight / 2;
      }
    }
  });
}

function renderScene() {
  const decisions = lanes.map((lane) => decisionOf(lane));
  office.setLamps(decisions.map((decision) => decision?.final_action));
  const lead = lanes[0];
  office.setEvidence(decisionOf(lead)?.evidence_checks || []);
  const reading = lanes.map((lane) => lane.events[lane.index]).find((event) => event?.tool === "read_file" && event.type === "tool_call");
  office.setScreen("code", reading ? `📄 ${argsText(reading.args)}` : "");
  const checks = decisions.flatMap((decision) => decision?.evidence_checks || []);
  office.setScreen("evidence", checks.length ? `✔ ${checks.filter((check) => check.exists).length}  ✘ ${checks.filter((check) => !check.exists).length}` : "");
  office.setScreen("reception", lead ? `📦 ${lead.pkg}` : "");
}

function render() {
  if (!lanes.length) return;
  $("clock").textContent = `${seconds(clock.t)} / ${seconds(clock.duration)} thời gian thật`;
  $("progress").value = String(Math.round(clock.t * 10));
  for (const lane of lanes) {
    if (thinking(lane)) lane.actor.say(`đang suy nghĩ ${seconds(clock.t - lane.offsets[lane.index])}`, true);
  }
  const lead = lanes[0];
  const room = lead.rooms[lead.index] || "reception";
  $("room-name").textContent = lanes.length > 1 ? `${lanes.length} model cùng xử lý một gói` : `${ROOMS[room].name} — ${ROOMS[room].step}`;
  $("room-dot").style.background = ROOM_COLORS[room];
  $("event-text").textContent = lead.index < 0 ? "Nhấn Phát lại hoặc phím cách." : thinking(lead) ? "Mô hình đang sinh câu trả lời…" : describe(lead.events[lead.index]);
  const phase = Math.max(...lanes.map((lane) => {
    const seen = lane.rooms.slice(0, lane.index + 1).reverse().map((id) => PHASE[id]).find((value) => value !== undefined);
    return seen ?? -1;
  }));
  document.querySelectorAll(".phase-bar li").forEach((item) => {
    const value = Number(item.dataset.phase);
    item.classList.toggle("done", value < phase);
    item.classList.toggle("current", value === phase);
  });
  renderBoard();
  renderDetail(lead);
}

// --- clock ----------------------------------------------------------------------------------------
function update(scrubbing = false) {
  const now = performance.now();
  let changed = false;
  for (const lane of lanes) changed = advance(lane, now, scrubbing) || changed;
  const done = lanes.every((lane) => lane.index === lane.events.length - 1);
  if (clock.playing && done && clock.t >= clock.duration) stop();
  if (changed || scrubbing) renderScene(); // the 3D props change only on a new event: keep the GPU idle
  render();
  return changed;
}

function loop() {
  const now = performance.now();
  if (clock.playing) {
    clock.t = Math.min(clock.duration, clock.t + (now - clock.last) / 1000 * clock.rate);
    update();
  }
  clock.last = now;
}
setInterval(loop, 100);

function stop() {
  clock.playing = false;
  $("play").textContent = "Phát lại";
}

function play() {
  if (clock.playing) return stop();
  if (lanes.every((lane) => lane.index === lane.events.length - 1)) seek(0);
  clock.playing = true;
  clock.last = performance.now();
  $("play").textContent = "Tạm dừng";
}

function seek(time) {
  clock.t = Math.max(0, Math.min(time, clock.duration));
  for (const lane of lanes) lane.index = -1;
  update(true);
}

// --- loading --------------------------------------------------------------------------------------
let runs = [];
const groups = new Map(); // "w57-reg-a-*" -> [runs] for runs that differ only in the model variant

function syncHash() {
  const next = new URLSearchParams();
  next.set("mode", $("mode").value);
  next.set("run", $("run-select").value);
  next.set("pkg", $("package-select").value);
  if (params.get("bench") === "1") next.set("bench", "1");
  history.replaceState(null, "", `#${next}`);
  const first = lanes[0];
  if (first) $("timeline-link").href = `/#run=${encodeURIComponent(first.run)}&pkg=${encodeURIComponent(first.pkg)}`;
}

function runsForMode() {
  return $("mode").value === "compare" ? [...groups.keys()] : runs;
}

async function packagesFor(choice) {
  if ($("mode").value !== "compare") return (await getJson(`/api/runs/${encodeURIComponent(choice)}/packages`)).map((item) => item.package);
  const lists = await Promise.all(groups.get(choice).map((run) => getJson(`/api/runs/${encodeURIComponent(run)}/packages`)));
  const [first, ...rest] = lists.map((list) => list.map((item) => item.package));
  return (first || []).filter((name) => rest.every((list) => list.includes(name)));
}

async function loadLanes() {
  stop();
  const choice = $("run-select").value;
  const pkg = $("package-select").value;
  const order = { LLM: 0, SLM: 1, TLM: 2 };
  const chosen = $("mode").value === "compare"
    ? [...groups.get(choice)].sort((a, b) => (order[variantOf(a)] ?? 9) - (order[variantOf(b)] ?? 9))
    : [choice];
  office.clearWorkers(chosen.length);
  lanes = await Promise.all(chosen.map((run, index) => makeLane(run, pkg, index)));
  clock.duration = Math.max(...lanes.map((lane) => lane.offsets.at(-1) ?? 0), 0.1);
  $("progress").max = String(Math.round(clock.duration * 10));
  const single = lanes.length === 1;
  $("detail-title").textContent = single ? "QUYẾT ĐỊNH CUỐI (LUẬT CỨNG)" : `CHI TIẾT ${lanes[0].name}: QUYẾT ĐỊNH CUỐI (LUẬT CỨNG)`;
  $("log-block").hidden = !single;
  if (single) {
    const lane = lanes[0];
    $("event-log").replaceChildren(...lane.events.map((event, at) => {
      const item = element("li");
      const button = element("button", undefined, "log-item");
      button.type = "button";
      button.style.setProperty("--room", ROOM_COLORS[lane.rooms[at]]);
      button.append(element("span", String(at + 1).padStart(2, "0"), "log-index"), element("span", clip(describe(event), 90), "log-text"));
      button.addEventListener("click", () => { stop(); seek(lane.offsets[at]); });
      item.append(button);
      return item;
    }));
  }
  $("package-name").textContent = pkg;
  const ends = lanes.map((lane) => lane.events.findLast((event) => event.type === "run_end"));
  $("package-meta").textContent = lanes.map((lane, at) => `${lane.name}: ${ends[at] ? `${ends[at].elapsed_s} s, ${ends[at].steps} bước` : "đang chạy"}`).join(" · ");
  syncHash();
  office.focus(null, 0.8);
  seek(0);
}

async function loadChoice(preferredPackage) {
  const names = await packagesFor($("run-select").value);
  $("package-select").replaceChildren(...names.map((name) => { const option = element("option", name); option.value = name; return option; }));
  $("package-select").value = names.includes(preferredPackage) ? preferredPackage : names[0] || "";
  if (names.length) await loadLanes();
}

async function loadMode(preferredRun, preferredPackage) {
  const choices = runsForMode();
  $("run-select").replaceChildren(...choices.map((value) => {
    const option = element("option", $("mode").value === "compare" ? value.replace("*", "{LLM,SLM,TLM}") : value);
    option.value = value;
    return option;
  }));
  $("run-label").textContent = $("mode").value === "compare" ? "Bộ run" : "Run";
  $("run-select").value = choices.includes(preferredRun) ? preferredRun : choices[0];
  await loadChoice(preferredPackage);
}

async function start() {
  runs = await getJson("/api/runs");
  for (const run of runs) {
    if (!variantOf(run)) continue;
    const key = run.replace(VARIANT, (_, lead) => `${lead}a-*`);
    groups.set(key, [...(groups.get(key) || []), run]);
  }
  for (const [key, members] of groups) if (members.length < 2) groups.delete(key);
  const compareOption = $("mode").querySelector('option[value="compare"]');
  compareOption.disabled = groups.size === 0;
  $("mode").value = params.get("mode") === "compare" && groups.size ? "compare" : "single";
  await loadMode(params.get("run"), params.get("pkg"));
}

$("mode").addEventListener("change", () => loadMode(null, $("package-select").value));
$("run-select").addEventListener("change", () => loadChoice($("package-select").value));
$("package-select").addEventListener("change", loadLanes);
$("play").addEventListener("click", play);
$("progress").addEventListener("input", (event) => { stop(); seek(Number(event.target.value) / 10); });
$("rate").addEventListener("change", (event) => { clock.rate = Number(event.target.value); office.speed.value = Math.min(2, Math.max(1, clock.rate / 4)); });
$("director").addEventListener("change", (event) => { office.setDirector(event.target.checked); office.focus(null, 0.8); });
$("reset-view").addEventListener("click", () => { $("director").checked = false; office.setDirector(false); });
$("previous").addEventListener("click", () => {
  stop();
  const lead = lanes[0];
  if (lead) seek(lead.offsets[Math.max(0, lead.index - 1)] ?? 0);
});
$("next").addEventListener("click", () => {
  stop();
  const lead = lanes[0];
  if (lead) seek(lead.offsets[Math.min(lead.events.length - 1, lead.index + 1)] ?? clock.duration);
});
addEventListener("keydown", (event) => {
  if (event.target.closest("select, input, button, a")) return; // keep native keys on controls
  if (event.key === " ") { event.preventDefault(); play(); }
  else if (event.key === "ArrowRight") $("next").click();
  else if (event.key === "ArrowLeft") $("previous").click();
});
start().catch((error) => { $("event-text").textContent = `Không tải được dữ liệu: ${error.message}`; });
