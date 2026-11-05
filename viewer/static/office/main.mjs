// 3D office page: picks a run/package, replays its trace and moves the worker between rooms.
// Every string from the trace is untrusted and goes into the page with textContent only.
import { createOffice } from "./scene.mjs";
import { ROOMS, roomFor } from "./events.mjs";

const $ = (id) => document.getElementById(id);
const PHASE = { reception: 0, code: 1, intel: 1, lab: 1, evidence: 2, decision: 3 };
const ACTIONS = { approve: "Cho phép", review: "Chuyển người xem", deny: "Từ chối" };
const LABELS = { benign: "Lành tính", suspicious: "Nghi vấn", malicious: "Độc hại" };
const ROOM_COLORS = {
  reception: "#61e8c2", code: "#7cc4ff", intel: "#b79cff", lab: "#8a98a8",
  evidence: "#ffd08a", decision: "#ff8e83", hallway: "#6f8597",
};

const params = new URLSearchParams(location.hash.slice(1));
const office = createOffice($("office-canvas"), $("room-labels"), $("worker-layer"));
office.stats.continuous = params.get("bench") === "1"; // O-0: continuous render to measure FPS
window.__office = office; // read-only handle for measurements in the browser console

let events = [];
let rooms = [];
let index = -1;
let timer = null;
let model = "agent";

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

function argsText(args) {
  if (!args || typeof args !== "object") return "";
  if (args.file) return `${args.file}${args.start ? `:${args.start}-${args.end ?? ""}` : ""}`;
  return "";
}

function describe(event) {
  switch (event.type) {
    case "run_start": return `Bắt đầu phân tích với ${event.model}`;
    case "tool_call": return `Gọi ${event.tool} ${argsText(event.args)}`.trim();
    case "tool_result": return `${event.tool}: ${event.ok ? event.summary || "OK" : `lỗi — ${event.summary || ""}`}`;
    case "error": return `Sự cố ${event.kind}: ${event.message || ""}`;
    case "verdict": return event.valid ? "Mô hình nộp kết luận hợp lệ" : "Kết luận chưa hợp lệ, phải sửa";
    case "decision": return `${LABELS[event.final_label] || event.final_label} → ${ACTIONS[event.final_action] || "chưa có hành động"} (luật ${event.rule})`;
    case "run_end": return `Kết thúc: ${event.steps} bước, ${event.elapsed_s} giây`;
    case "limit": return "Hết giới hạn bước, chuyển người xem";
    default: return event.type;
  }
}

function bubbleText(event) {
  if (event.type === "tool_call") return clip(`${event.tool} ${argsText(event.args)}`.trim(), 34);
  if (event.type === "verdict") return event.valid ? "Nộp kết luận" : "Sửa kết luận";
  if (event.type === "decision") return ACTIONS[event.final_action] || "Quyết định";
  if (event.type === "error") return clip(`Sự cố: ${event.kind}`, 34);
  if (event.type === "run_end") return "Xong";
  return "";
}

function renderLog() {
  const log = $("event-log");
  log.replaceChildren(...events.map((event, position) => {
    const item = element("li");
    const button = element("button", undefined, "log-item");
    button.type = "button";
    button.style.setProperty("--room", ROOM_COLORS[rooms[position]]);
    button.append(element("span", String(position + 1).padStart(2, "0"), "log-index"),
                  element("span", clip(describe(event), 90), "log-text"));
    button.addEventListener("click", () => { stop(); show(position, true); });
    item.append(button);
    return item;
  }));
}

function renderDecision() {
  const seen = events.slice(0, index + 1);
  const decision = [...seen].reverse().find((event) => event.type === "decision");
  const verdict = [...seen].reverse().find((event) => event.type === "verdict" && event.valid)
               || [...seen].reverse().find((event) => event.type === "verdict");
  const proposal = verdict?.verdict;

  $("decision").textContent = decision
    ? `${LABELS[decision.final_label] || decision.final_label} · ${ACTIONS[decision.final_action] || "—"} · luật ${decision.rule}`
    : "Chưa có quyết định";
  $("decision").dataset.action = decision?.final_action || "";
  $("reasons").replaceChildren(...(decision?.reasons || []).map((reason) => element("li", reason)));

  $("proposal").textContent = proposal
    ? `${LABELS[proposal.label] || proposal.label} · tin cậy ${Math.round((proposal.confidence ?? 0) * 100)}% — ${proposal.description || ""}`
    : "Chưa có đề xuất";
  $("behaviors").replaceChildren(...(proposal?.behaviors || []).slice(0, 4).map((behavior) => {
    const item = element("li");
    item.append(element("span", behavior.severity || "", `sev sev-${behavior.severity}`),
                element("span", `${behavior.behavior} `),
                element("code", `${behavior.evidence?.file}:${behavior.evidence?.lines}`));
    return item;
  }));

  const checks = decision?.evidence_checks || [];
  $("checks").replaceChildren(...(checks.length ? checks.map((check) => {
    const item = element("li", undefined, check.exists ? "ok" : "bad");
    item.append(element("span", check.exists ? "✔ " : "✘ "), element("code", `${check.file}:${check.lines}`));
    return item;
  }) : [element("li", decision ? "Không có bằng chứng để kiểm" : "Chưa kiểm", "count")]));

  office.setEvidence(decision ? checks : []);
  office.setDecision(decision?.final_action || null);
}

function show(position, instant = false) {
  index = Math.max(-1, Math.min(position, events.length - 1));
  $("position").textContent = `${index + 1} / ${events.length}`;
  $("progress").value = String(Math.max(index, 0));
  document.querySelectorAll(".log-item").forEach((button, at) => {
    button.classList.toggle("current", at === index);
    button.classList.toggle("past", at < index);
    if (at === index) button.scrollIntoView({ block: "nearest" });
  });
  if (index < 0) {
    office.setWorker(model, "");
    renderDecision();
    return;
  }
  const event = events[index];
  const room = rooms[index];
  office.walkTo(room, instant);
  office.setWorker(model, bubbleText(event));
  $("room-name").textContent = `${ROOMS[room].name} — ${ROOMS[room].step}`;
  $("room-dot").style.background = ROOM_COLORS[room];
  $("event-text").textContent = describe(event);
  const phase = rooms.slice(0, index + 1).reverse().map((id) => PHASE[id]).find((value) => value !== undefined) ?? 0;
  document.querySelectorAll(".phase-bar li").forEach((item) => {
    const value = Number(item.dataset.phase);
    item.classList.toggle("done", value < phase);
    item.classList.toggle("current", value === phase);
  });
  renderDecision();
}

function stop() {
  clearTimeout(timer);
  timer = null;
  $("play").textContent = "Phát lại";
}

function tick() {
  if (index >= events.length - 1) return stop();
  show(index + 1);
  timer = setTimeout(tick, 1500 / office.speed.value);
}

function play() {
  if (timer) return stop();
  if (index >= events.length - 1) show(-1);
  $("play").textContent = "Tạm dừng";
  tick();
}

function syncHash(run, pkg) {
  const next = new URLSearchParams({ run, pkg });
  if (params.get("bench") === "1") next.set("bench", "1");
  history.replaceState(null, "", `#${next}`);
  $("timeline-link").href = `/#run=${encodeURIComponent(run)}&pkg=${encodeURIComponent(pkg)}`;
}

async function loadPackage(run, pkg, summary) {
  stop();
  const query = new URLSearchParams({ run, pkg, after: "-1" });
  events = (await getJson(`/api/trace?${query}`)).filter((event) => event.type !== "thought");
  rooms = events.map(roomFor);
  const start = events.find((event) => event.type === "run_start");
  const end = [...events].reverse().find((event) => event.type === "run_end");
  model = start?.model || "agent";
  $("package-name").textContent = pkg;
  const meta = [model, end ? `${end.steps} bước` : summary?.status, end ? `${end.elapsed_s} giây` : null,
                end?.tokens_per_s ? `${end.tokens_per_s} token/s` : null].filter(Boolean);
  $("package-meta").textContent = meta.join(" · ");
  $("progress").max = String(Math.max(events.length - 1, 0));
  renderLog();
  syncHash(run, pkg);
  show(-1);
  $("room-name").textContent = "Sẵn sàng";
  $("event-text").textContent = `${events.length} sự kiện. Nhấn Phát lại hoặc phím cách.`;
}

let packages = [];
async function loadRun(run, preferred) {
  packages = await getJson(`/api/runs/${encodeURIComponent(run)}/packages`);
  $("package-select").replaceChildren(...packages.map((item) => {
    const option = element("option", `${item.package}${item.label ? ` — ${LABELS[item.label] || item.label}` : ""}`);
    option.value = item.package;
    return option;
  }));
  const pkg = packages.some((item) => item.package === preferred) ? preferred : packages[0]?.package;
  if (pkg) {
    $("package-select").value = pkg;
    await loadPackage(run, pkg, packages.find((item) => item.package === pkg));
  }
}

async function start() {
  const runs = await getJson("/api/runs");
  $("run-select").replaceChildren(...runs.map((run) => { const option = element("option", run); option.value = run; return option; }));
  const run = runs.includes(params.get("run")) ? params.get("run") : runs[0];
  $("run-select").value = run;
  await loadRun(run, params.get("pkg"));
}

$("run-select").addEventListener("change", (event) => loadRun(event.target.value));
$("package-select").addEventListener("change", (event) =>
  loadPackage($("run-select").value, event.target.value, packages.find((item) => item.package === event.target.value)));
$("play").addEventListener("click", play);
$("next").addEventListener("click", () => { stop(); show(index + 1); });
$("previous").addEventListener("click", () => { stop(); show(index - 1); });
$("progress").addEventListener("input", (event) => { stop(); show(Number(event.target.value), true); });
$("speed").addEventListener("change", (event) => { office.speed.value = Number(event.target.value); });
$("reset-view").addEventListener("click", () => office.resetView());
addEventListener("keydown", (event) => {
  if (event.target.closest("select, input, button, a")) return; // keep native keys on controls
  if (event.key === " ") { event.preventDefault(); play(); }
  else if (event.key === "ArrowRight") { stop(); show(index + 1); }
  else if (event.key === "ArrowLeft") { stop(); show(index - 1); }
});
start().catch((error) => { $("event-text").textContent = `Không tải được dữ liệu: ${error.message}`; });
