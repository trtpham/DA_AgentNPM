// 3D office page: picks a run/package, replays its trace and moves the worker between rooms.
// Every string from the trace is untrusted and goes into the page with textContent only.
import { createOffice } from "./scene.mjs";
import { ROOMS, roomFor } from "./events.mjs";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.hash.slice(1));
const office = createOffice($("office-canvas"), $("room-labels"));
office.stats.continuous = params.get("bench") === "1"; // O-0: continuous render to measure FPS
window.__office = office; // read-only handle for measurements in the browser console

let events = [];
let index = -1;
let timer = null;

async function getJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function option(value, text) {
  const item = document.createElement("option");
  item.value = value;
  item.textContent = text;
  return item;
}

function describe(event) {
  if (event.type === "tool_call") return `Gọi ${event.tool}`;
  if (event.type === "tool_result") return `${event.tool}: ${event.ok ? event.summary || "OK" : "lỗi"}`;
  if (event.type === "error") return `Lỗi ${event.kind}: ${event.message || ""}`;
  if (event.type === "verdict") return event.valid ? "Mô hình nộp kết luận" : "Kết luận chưa hợp lệ";
  if (event.type === "decision") return `${event.final_label} → ${event.final_action} (luật ${event.rule})`;
  if (event.type === "run_end") return `Kết thúc sau ${event.steps} bước, ${event.elapsed_s} giây`;
  if (event.type === "run_start") return `Bắt đầu với ${event.model}`;
  return event.type;
}

function show(position) {
  index = Math.max(-1, Math.min(position, events.length - 1));
  $("position").textContent = `${index + 1} / ${events.length}`;
  if (index < 0) return;
  const event = events[index];
  const room = roomFor(event);
  office.walkTo(room);
  $("room-name").textContent = ROOMS[room].name;
  $("room-step").textContent = ROOMS[room].step;
  $("event-text").textContent = describe(event);
  const decision = [...events.slice(0, index + 1)].reverse().find((item) => item.type === "decision");
  $("decision").textContent = decision ? describe(decision) : "Chưa có quyết định";
  $("decision").dataset.action = decision ? decision.final_action : "";
}

function stop() {
  clearTimeout(timer);
  timer = null;
  $("play").textContent = "Phát lại";
}

function tick() {
  if (index >= events.length - 1) return stop();
  show(index + 1);
  timer = setTimeout(tick, 1400 / office.speed.value);
}

async function loadPackage(run, pkg) {
  stop();
  const query = new URLSearchParams({ run, pkg, after: "-1" });
  events = (await getJson(`/api/trace?${query}`)).filter((event) => event.type !== "thought");
  show(-1);
  $("event-text").textContent = `${events.length} sự kiện. Nhấn Phát lại.`;
}

async function loadRun(run, preferred) {
  const packages = await getJson(`/api/runs/${encodeURIComponent(run)}/packages`);
  $("package-select").replaceChildren(...packages.map((item) => option(item.package, item.package)));
  const pkg = packages.some((item) => item.package === preferred) ? preferred : packages[0]?.package;
  if (pkg) {
    $("package-select").value = pkg;
    await loadPackage(run, pkg);
  }
}

async function start() {
  const runs = await getJson("/api/runs");
  $("run-select").replaceChildren(...runs.map((run) => option(run, run)));
  const run = runs.includes(params.get("run")) ? params.get("run") : runs[0];
  $("run-select").value = run;
  await loadRun(run, params.get("pkg"));
}

$("run-select").addEventListener("change", (event) => loadRun(event.target.value));
$("package-select").addEventListener("change", (event) => loadPackage($("run-select").value, event.target.value));
$("play").addEventListener("click", () => {
  if (timer) return stop();
  if (index >= events.length - 1) show(-1);
  $("play").textContent = "Tạm dừng";
  tick();
});
$("next").addEventListener("click", () => { stop(); show(index + 1); });
$("previous").addEventListener("click", () => { stop(); show(index - 1); });
$("speed").addEventListener("change", (event) => { office.speed.value = Number(event.target.value); });
start().catch((error) => { $("event-text").textContent = `Không tải được dữ liệu: ${error.message}`; });
