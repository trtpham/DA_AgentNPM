// 3D office page. Three modes on the real clock of each trace:
//  - truck (default): one install request = a truck carrying every package of a run; each parcel is
//    analysed in turn, then the whole truck is delivered, held for review, or held with a report;
//  - compare: A-LLM/A-SLM/A-TLM race on the same package;
//  - single: one run, one package.
// People are the AI models, robots are deterministic code (tools, checks, rules), and glowing orbs
// carry each step's input to a robot and its output back.
// Every string from a trace is untrusted and reaches the page with textContent only.
import { createOffice } from "./scene.mjs";
import { ROOMS, roomFor } from "./events.mjs";
import { argsText, explainStep, thinkingStep } from "./explain.mjs";
import { buildTruck, currentParcel, parcelZone, tally, truckPhase } from "./truck.mjs";

const $ = (id) => document.getElementById(id);
const PHASE = { reception: 0, code: 1, intel: 1, lab: 1, evidence: 2, decision: 3 };
const ACTIONS = { approve: "Cho phép", review: "Chuyển người xem", deny: "Từ chối" };
const STAMPS = { approve: "CHO PHÉP", review: "NGƯỜI XEM", deny: "TỪ CHỐI" };
const STAMP_ICONS = { approve: "✔", review: "👁", deny: "✘" }; // race mode: three stamps must fit side by side
const LABELS = { benign: "Lành tính", suspicious: "Nghi vấn", malicious: "Độc hại" };
const ACTOR_ICONS = { model: "🧑", tool: "🤖", rules: "⚖️", system: "⚙️" };
const VARIANT = /(^|[-_])a-(llm|slm|tlm)(?=$|[-_])/i;
const VARIANT_COLORS = { LLM: "#61e8c2", SLM: "#7cc4ff", TLM: "#ffb86b" };
const ROOM_COLORS = { reception: "#61e8c2", code: "#7cc4ff", intel: "#b79cff", lab: "#8a98a8",
                      evidence: "#ffd08a", decision: "#ff8e83", hallway: "#6f8597" };
const MIN_DWELL = 1.1;      // wall seconds per event, so each input/output exchange can be followed
const THINKING_AFTER = 0.8; // trace seconds of silence before a worker is shown "thinking"

const params = new URLSearchParams(location.hash.slice(1));
const office = createOffice($("office-canvas"), $("room-labels"), $("worker-layer"));
office.stats.continuous = params.get("bench") === "1"; // O-0: continuous render to measure FPS
window.__office = office; // read-only handle for measurements in the browser console

let lanes = [];
let focusLane = 0;
let closeUp = null;
let generation = 0;         // bumps on every seek, so delayed animations of an old timeline are dropped
let truck = null;           // truck mode timeline (truck.mjs), null in the other modes
const beats = { intro: false, outro: false }; // one-off truck moments already played
const FINAL_TEXT = {
  approve: "✅ Cả xe an toàn — giao hàng, npm install tiếp tục",
  review: "👁 Xe bị giữ — có gói chờ người xem duyệt",
  deny: "⛔ Xe bị chặn — có gói độc, đã gửi phiếu báo cáo",
};
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

const clip = (text, length) => {
  const value = String(text ?? "");
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
};
const seconds = (value) => `${value.toFixed(1)} s`;

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
  return { run, pkg, events, offsets, rooms: events.map(roomFor), variant, model, name, color, index: -1, lane: index,
           shownAt: 0, finishedAt: null, actor: office.addWorker({ id: run, name, color, lane: index }) };
}

function decisionOf(lane, upTo = lane.index) {
  return lane.events.slice(0, upTo + 1).reverse().find((event) => event.type === "decision");
}

function thinking(lane) {
  const next = lane.events[lane.index + 1];
  if (lane.index < 0 || !next || !["tool_call", "verdict"].includes(next.type)) return false;
  return clock.t - lane.offsets[lane.index] > THINKING_AFTER;
}

function stampFor(lane, decision, animate) {
  const text = !decision ? "" : lanes.length > 1
    ? `${STAMP_ICONS[decision.final_action] || "?"} ${decision.rule}` : `${STAMPS[decision.final_action] || "?"} · ${decision.rule}`;
  lane.actor.stamp(decision?.final_action, text, animate);
}

// --- choreography: what the people and robots do for one event ----------------------------------
function short(text, length = 26) { return clip(text, length); }

function animate(lane, event) {
  const mine = generation;
  const alive = () => mine === generation;
  const room = lane.rooms[lane.index];
  const worker = () => lane.actor.head();
  switch (event.type) {
    case "run_start":
      if (truck) {
        // Truck mode: the guard scans the parcel at the gate (OSV), then reception opens it.
        office.staffReact("guard", "raise");
        office.staffReact("courier", "handover");
        office.sendPacket(office.staffHead("guard"), office.robotHead("reception"), "#c99a5b", () => {
          if (!alive()) return;
          office.robotReact("reception", "receive");
          office.sendPacket(office.robotHead("reception"), worker(), "#c99a5b", null, `📦 ${short(lane.pkg, 22)}`);
        }, `🛡️ quét OSV · ${short(lane.pkg, 20)}`);
        break;
      }
      // The courier hands the tarball from npm pack to reception; reception gives it to the model.
      office.staffReact("courier", "handover");
      office.sendPacket(office.staffHead("courier"), office.robotHead("reception"), "#c99a5b", () => {
        if (!alive()) return;
        office.robotReact("reception", "receive");
        office.sendPacket(office.robotHead("reception"), worker(), "#c99a5b", null, `📦 ${short(lane.pkg, 22)}`);
      }, "📦 npm pack — chưa chạy script");
      break;
    case "tool_call":
      office.sendPacket(worker(), office.robotHead(room), lane.color,
                        () => alive() && office.robotReact(room, "work"), `VÀO: ${short(argsText(event.args) || event.tool)}`);
      break;
    case "tool_result":
      office.robotReact(room, "work");
      office.sendPacket(office.robotHead(room), worker(), event.ok ? "#e8f4ff" : "#ff8e83", null,
                        `RA: ${event.ok ? short(event.summary || "OK", 22) : "lỗi"}`);
      break;
    case "verdict":
      office.sendPacket(worker(), office.robotHead("evidence"), lane.color,
                        () => alive() && office.robotReact("evidence", event.valid ? "ok" : "bad"),
                        `Kết luận: ${LABELS[event.verdict?.label] || "?"} ${Math.round((event.verdict?.confidence ?? 0) * 100)}%`);
      break;
    case "error":
      office.robotReact("evidence", event.kind === "normalized_output" ? "work" : "bad");
      if (event.kind !== "normalized_output") {
        office.sendPacket(office.robotHead("evidence"), worker(), "#ff8e83", null, "TRẢ LẠI: sửa kết luận");
      }
      break;
    case "decision": {
      const checks = event.evidence_checks || [];
      const good = checks.filter((check) => check.exists).length;
      office.robotReact("evidence", good === checks.length ? "ok" : "bad");
      office.sendPacket(office.robotHead("evidence"), office.robotHead("decision"), "#ffd08a", () => {
        if (!alive()) return;
        office.robotReact("decision", "gavel");
        setTimeout(() => {
          if (!alive()) return;
          stampFor(lane, event, true);
          office.celebrate(event.final_action);
          if (truck && event.final_action === "deny") {
            // A malicious parcel: it goes to quarantine and a report flies to the user and the AI assistant.
            office.sendPacket(office.robotHead("decision"), office.housePoint(), "#ff4a3d", () => {
              if (!alive()) return;
              office.robotReact("assistant", "bad");
              office.staffReact("dev", "raise");
            }, `📄 Phiếu: ${short(lane.pkg, 20)} — TỪ CHỐI`);
          }
          if (event.final_action === "review") {
            // A case for a human: the file goes to the reviewer's desk.
            office.sendPacket(office.robotHead("decision"), office.staffHead("reviewer"), "#ffd08a",
                              () => alive() && office.staffReact("reviewer", "raise"), `👁 ${lane.name}: cần duyệt tay`);
          } else {
            office.staffReact("guard", "salute");
            office.staffReact("po", "thumbs");
          }
        }, 450);
      }, `✔ ${good}  ✘ ${checks.length - good}`);
      office.focus("decision", 0.36);
      clearTimeout(closeUp);
      closeUp = setTimeout(() => office.focus(lanes.length > 1 ? null : lane.rooms[lane.index], 0.78), 3200);
      break;
    }
    default:
      break;
  }
}

// Advance a lane to the clock; scrubbing jumps, playing steps one event at a time with a short dwell.
function advance(lane, now, scrubbing) {
  let target = -1;
  while (target + 1 < lane.events.length && lane.offsets[target + 1] <= clock.t) target += 1;
  if (target === lane.index) return false;
  const jump = scrubbing || target < lane.index;
  const next = jump ? target : lane.index + 1;
  if (!jump && now - lane.shownAt < MIN_DWELL * 1000 / Math.max(1, clock.rate / 4)) return false;
  lane.index = next;
  lane.shownAt = now;
  if (next < 0) {  // before the first event (e.g. scrubbed back to the start): a clean worker at reception
    lane.actor.walkTo("reception", true);
    lane.actor.say("");
    lane.actor.stamp(null, "", false);
    return true;
  }
  const event = lane.events[next];
  if (truck) lane.pkg = truck.packages[event._pkg].name;
  lane.actor.walkTo(lane.rooms[next], jump);
  const step = explainStep(lane.events, next);
  lane.actor.say(`${ACTOR_ICONS[step.actor]} ${clip(step.title, 30)}`);
  lane.finishedAt = event.type === "run_end" ? lane.offsets[next] : null;
  if (jump) {
    stampFor(lane, decisionOf(lane), false);
  } else {
    if (event.type !== "decision") stampFor(lane, decisionOf(lane), false);
    animate(lane, event);
    if (lanes.length === 1 && event.type !== "decision") office.focus(lane.rooms[next], 0.42);
  }
  return true;
}

// --- panel: caption (input -> processing -> output), lane board, decision detail ------------------
function stepFor(lane) {
  if (lane.index < 0) return null;
  return thinking(lane) ? thinkingStep(lane.model, clock.t - lane.offsets[lane.index]) : explainStep(lane.events, lane.index);
}

function renderCaption() {
  const lane = lanes[focusLane] || lanes[0];
  const step = stepFor(lane);
  $("caption").style.setProperty("--worker", lane.color);
  $("caption-who").textContent = step
    ? `${lane.name} · ${truck ? `thùng ${(lane.events[lane.index]?._pkg ?? 0) + 1}/${truck.packages.length} · ` : ""}sự kiện ${lane.index + 1}/${lane.events.length} · ${ACTOR_ICONS[step.actor]} ${step.who}: ${step.title}`
    : `${lane.name} · chưa bắt đầu — nhấn Phát lại hoặc phím cách`;
  let process = step?.process ?? "—";
  let output = step?.output ?? "—";
  const event = lane.events[lane.index];
  if (truck && event && !thinking(lane)) {
    const parcel = truck.packages[event._pkg];
    if (event.type === "run_start") process += " · Cổng đã quét OSV (chế độ thực nghiệm: không chặn, agent không thấy kết quả này)";
    if (event.type === "tool_result" && event.tool === "read_manifest" && parcel?.hooks === false) {
      output += " → Không có script cài đặt: sản phẩm thật cho gói này đi làn xanh (lô thực nghiệm vẫn phân tích để đo)";
    }
  }
  $("caption-in").textContent = step?.input ?? "—";
  $("caption-process").textContent = process;
  $("caption-out").textContent = output;
  $("caption-out").parentElement.classList.toggle("untrusted", Boolean(step?.untrustedOutput));
  $("caption").dataset.actor = step?.actor || "system";
}

function renderBoard() {
  const finished = lanes.filter((lane) => lane.finishedAt !== null).sort((a, b) => a.finishedAt - b.finishedAt);
  $("board").replaceChildren(...lanes.map((lane, at) => {
    const card = element("li");
    const button = element("button", undefined, `lane-card${at === focusLane ? " focused" : ""}`);
    button.type = "button";
    button.style.setProperty("--worker", lane.color);
    button.setAttribute("aria-pressed", String(at === focusLane));
    button.addEventListener("click", () => { focusLane = at; render(); });
    const decision = decisionOf(lane);
    const rank = finished.indexOf(lane);
    const head = element("div", undefined, "lane-head");
    head.append(element("strong", `🧑 ${lane.name}`), element("span", lane.model, "count"),
                element("span", rank >= 0 ? `#${rank + 1} · ${seconds(lane.finishedAt)}` : seconds(Math.min(clock.t, lane.offsets.at(-1) ?? 0)),
                        rank >= 0 ? "rank" : "lane-clock"));
    const step = stepFor(lane);
    const calls = lane.events.slice(0, lane.index + 1).filter((item) => item.type === "tool_call").length;
    const now = element("p", step ? `${ACTOR_ICONS[step.actor]} ${clip(step.title, 60)}` : "chờ bắt đầu", "lane-now");
    const verdict = element("p", decision ? `${LABELS[decision.final_label] || decision.final_label} · ${ACTIONS[decision.final_action] || "—"} · ${decision.rule}`
                                          : `${calls} lần gọi công cụ`, "lane-decision");
    verdict.dataset.action = decision?.final_action || "";
    button.append(head, now, verdict);
    card.append(button);
    return card;
  }));
}

function renderDetail(lane) {
  const decision = decisionOf(lane);
  const verdicts = lane.events.slice(0, lane.index + 1).filter((event) => event.type === "verdict");
  const proposal = (verdicts.reverse().find((event) => event.valid) || verdicts[0])?.verdict;
  $("detail-title").textContent = `${lane.name}: QUYẾT ĐỊNH CUỐI (LUẬT CỨNG)`;
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
  const log = $("event-log");
  if (log.dataset.run !== lane.run) {
    log.dataset.run = lane.run;
    log.replaceChildren(...lane.events.map((event, at) => {
      const step = explainStep(lane.events, at);
      const item = element("li");
      const button = element("button", undefined, "log-item");
      button.type = "button";
      button.style.setProperty("--room", ROOM_COLORS[lane.rooms[at]]);
      button.append(element("span", String(at + 1).padStart(2, "0"), "log-index"),
                    element("span", `${ACTOR_ICONS[step.actor]} ${clip(step.title, 80)}`, "log-text"));
      button.addEventListener("click", () => { stop(); seek(lane.offsets[at]); });
      item.append(button);
      return item;
    }));
  }
  [...log.querySelectorAll(".log-item")].forEach((button, at) => {
    button.classList.toggle("current", at === lane.index);
    button.classList.toggle("past", at < lane.index);
    if (at === lane.index && clock.playing) {
      // Scroll the log box only; scrollIntoView would move the whole page away from the 3D view.
      const top = button.offsetTop - log.offsetTop;
      if (top < log.scrollTop || top + button.offsetHeight > log.scrollTop + log.clientHeight) log.scrollTop = top - log.clientHeight / 2;
    }
  });
}

function renderScene() {
  const decisions = lanes.map((lane) => decisionOf(lane));
  office.setLamps(decisions.map((decision) => decision?.final_action));
  const lead = lanes[focusLane] || lanes[0];
  office.setEvidence(decisionOf(lead)?.evidence_checks || []);
  const reading = lanes.map((lane) => lane.events[lane.index]).find((event) => event?.tool === "read_file" && event.type === "tool_call");
  office.setScreen("code", reading ? `📄 ${argsText(reading.args)}` : "");
  const checks = decisions.flatMap((decision) => decision?.evidence_checks || []);
  office.setScreen("evidence", checks.length ? `✔ ${checks.filter((check) => check.exists).length}  ✘ ${checks.filter((check) => !check.exists).length}` : "");
  office.setScreen("reception", lead ? `📦 ${lead.pkg}` : "");
  // The npm gate barrier follows the selected model's final action (approve/deny-scripts, dry-run);
  // in truck mode it follows the whole truck instead (see renderTruck).
  if (!truck) office.setGate(decisionOf(lead)?.final_action || null);
  const waiting = truck ? tally(truck, clock.t).review : decisions.filter((decision) => decision?.final_action === "review").length;
  office.setInbox(waiting);
  office.setScreen("reviewer", waiting ? `📥 ${waiting} ca chờ duyệt tay` : "");
}

function truckItems(t) {
  const current = currentParcel(truck, t);
  return truck.packages.map((pkg) => ({ zone: parcelZone(pkg, t, truck), action: t >= pkg.decidedAt ? pkg.action : null, hot: pkg === current }));
}

function houseText(t, counts) {
  if (t < 0.4) return "";
  if (t >= truck.outroAt) return FINAL_TEXT[truck.final];
  const done = truck.packages.length - counts.pending;
  return `⏳ Chờ kiểm tra: ${done}/${truck.packages.length} gói xong`;
}

let truckPanelKey = "";
function renderTruck(scrubbing) {
  const t = clock.t;
  const counts = tally(truck, t);
  const phase = truckPhase(t, truck);
  office.setTruck({ phase, items: truckItems(t), houseText: houseText(t, counts),
                    truckLabel: `🚚 ${truck.packages.length} gói · ✅ ${counts.approve} · 👁 ${counts.review} · ⛔ ${counts.deny}` }, scrubbing);
  office.setGate(t >= truck.outroAt ? truck.final : null);
  office.setInbox(counts.review);
  if (office.isDirector() && (phase.where === "toGate" || phase.where === "toHouse" || phase.where === "registry")) {
    const point = office.truckPoint();
    office.focusAt(point.x, point.z, 0.4);
  } else if (office.isDirector() && t >= truck.outroAt) {
    office.focusAt(-33, 2, 0.42);
  }
  // One-off moments, only while playing forward (never replayed by scrubbing).
  if (!scrubbing && clock.playing) {
    if (!beats.intro && t >= 0.2) {
      beats.intro = true;
      office.robotReact("assistant", "work");
      office.sendPacket(office.housePoint(), office.registryPoint(), "#61e8c2", null, `npm install (${truck.packages.length} gói)`);
    }
    if (!beats.outro && t >= truck.outroAt) {
      beats.outro = true;
      const gate = office.staffHead("guard");
      office.sendPacket(gate, office.housePoint(), truck.final === "approve" ? "#2fe0a8" : truck.final === "deny" ? "#ff4a3d" : "#ffaa1a", () => {
        office.robotReact("assistant", truck.final === "approve" ? "ok" : "bad");
        office.staffReact("dev", truck.final === "approve" ? "thumbs" : "raise");
      }, FINAL_TEXT[truck.final]);
      if (truck.final === "approve") office.celebrate("approve");
    }
  }
  const key = `${counts.approve}.${counts.review}.${counts.deny}.${currentParcel(truck, t)?.index ?? -1}.${t >= truck.outroAt}`;
  if (key !== truckPanelKey) { truckPanelKey = key; renderTruckPanel(counts); }
}

function reportCard(pkg) {
  const card = element("article", undefined, `report-card report-${pkg.action}`);
  const verdict = pkg.verdict || {};
  const decision = pkg.decision || {};
  card.append(element("h3", pkg.action === "deny" ? "📄 PHIẾU BÁO CÁO — GÓI BỊ TỪ CHỐI" : "👁 PHIẾU CHỜ DUYỆT"));
  card.append(element("p", `${pkg.name} · ${LABELS[decision.final_label] || decision.final_label || "?"} · luật ${decision.rule || "?"}`, "report-title"));
  if (pkg.action === "deny") {
    card.append(element("p", verdict.description || "", "report-why"));
    const list = element("ul", undefined, "plain-list behaviors");
    for (const behavior of (verdict.behaviors || []).slice(0, 4)) {
      const item = element("li");
      item.append(element("span", behavior.severity || "", `sev sev-${behavior.severity}`), element("span", `${behavior.behavior} `),
                  element("code", `${behavior.evidence?.file}:${behavior.evidence?.lines}`));
      if (behavior.impact) item.append(element("small", ` — ${behavior.impact}`));
      list.append(item);
    }
    card.append(element("small", "HÀNH VI VÀ BẰNG CHỨNG"), list);
    const fix = element("ul", undefined, "plain-list");
    for (const step of (verdict.remediation || []).slice(0, 4)) fix.append(element("li", `→ ${step}`));
    card.append(element("small", "VIỆC CẦN LÀM"), fix);
    card.append(element("p", "Gói được giữ trong khu cách ly (không xóa) để đối chiếu. Gửi tới: 🧑‍💻 người dùng + 🤖 trợ lý AI lập trình.", "report-to"));
  } else {
    const list = element("ul", undefined, "plain-list");
    for (const reason of (decision.reasons || ["Cần người xem xét"]).slice(0, 3)) list.append(element("li", reason));
    card.append(list, element("p", "Gói nằm trên kệ chờ duyệt ở Bàn người xem.", "report-to"));
  }
  return card;
}

function renderTruckPanel(counts) {
  const t = clock.t;
  const current = currentParcel(truck, t);
  $("truck-counts").replaceChildren(
    element("span", `✅ ${counts.approve} an toàn`, "chip chip-approve"), element("span", `👁 ${counts.review} chờ duyệt`, "chip chip-review"),
    element("span", `⛔ ${counts.deny} cách ly`, "chip chip-deny"), element("span", `⏳ ${counts.pending} chưa kiểm`, "chip"));
  const final = $("truck-final");
  final.textContent = t >= truck.outroAt ? FINAL_TEXT[truck.final] : "Kết quả cả xe: nghiêm ngặt nhất thắng (có 1 gói độc là giữ cả xe).";
  final.dataset.action = t >= truck.outroAt ? truck.final : "";
  $("truck-parcels").replaceChildren(...truck.packages.map((pkg) => {
    const item = element("li");
    const button = element("button", undefined, `parcel-item${pkg === current ? " current" : ""}`);
    button.type = "button";
    const done = t >= pkg.decidedAt;
    button.dataset.action = done ? pkg.action : "";
    button.append(element("span", done ? { approve: "✅", review: "👁", deny: "⛔" }[pkg.action] : pkg === current ? "🔎" : "📦"),
                  element("span", pkg.name, "parcel-name"),
                  element("span", pkg.hooks === false ? "không script" : "", "count"));
    button.addEventListener("click", () => { stop(); seek(pkg.start); });
    item.append(button);
    return item;
  }));
  const decided = truck.packages.filter((pkg) => t >= pkg.decidedAt && pkg.action !== "approve")
    .sort((a, b) => (a.action === "deny" ? 0 : 1) - (b.action === "deny" ? 0 : 1));
  $("truck-reports").replaceChildren(...(decided.length ? decided.slice(0, 6).map(reportCard) : [element("p", "Chưa có phiếu nào.", "count")]));
}

function render(scrubbing = false) {
  if (!lanes.length) return;
  if (truck) renderTruck(scrubbing);
  $("clock").textContent = `${seconds(clock.t)} / ${seconds(clock.duration)} thời gian thật`;
  $("progress").value = String(Math.round(clock.t * 10));
  const busyLanes = [];
  for (const lane of lanes) {
    const busy = thinking(lane);
    lane.actor.think(busy);
    if (busy) {
      lane.actor.say(`💭 đang suy nghĩ ${seconds(clock.t - lane.offsets[lane.index])}`, true);
      busyLanes.push(lane);
    }
  }
  // The GPU racks light up in the colours of the models generating right now (all local, no cloud).
  office.setThinking(busyLanes.map((lane) => lane.color));
  office.setScreen("server", busyLanes.length ? `⚡ GPU: ${busyLanes.map((lane) => lane.name).join(", ")} đang sinh` : "");
  const phase = Math.max(...lanes.map((lane) => {
    const seen = lane.rooms.slice(0, lane.index + 1).reverse().map((id) => PHASE[id]).find((value) => value !== undefined);
    return seen ?? -1;
  }));
  document.querySelectorAll(".phase-bar li").forEach((item) => {
    const value = Number(item.dataset.phase);
    item.classList.toggle("done", value < phase);
    item.classList.toggle("current", value === phase);
  });
  renderCaption();
  renderBoard();
  renderDetail(lanes[focusLane] || lanes[0]);
}

// --- clock ----------------------------------------------------------------------------------------
function update(scrubbing = false) {
  const now = performance.now();
  let changed = false;
  for (const lane of lanes) changed = advance(lane, now, scrubbing) || changed;
  const done = lanes.every((lane) => lane.index === lane.events.length - 1);
  if (clock.playing && done && clock.t >= clock.duration) stop();
  if (changed || scrubbing) renderScene(); // the 3D props change only on a new event: keep the GPU idle
  render(scrubbing);
}

// A lane "lags" while an event is already due but still waiting for its on-screen dwell.
function lagging(lane) {
  return lane.index + 1 < lane.events.length && lane.offsets[lane.index + 1] <= clock.t;
}

setInterval(() => {
  const now = performance.now();
  if (clock.playing) {
    // The clock waits for lagging workers: it slows down during instant tool bursts, so the time shown
    // (and every "thinking N s") always matches what the workers are doing on screen.
    if (!lanes.some(lagging)) clock.t = Math.min(clock.duration, clock.t + (now - clock.last) / 1000 * clock.rate);
    update();
  }
  clock.last = now;
}, 100);

function stop() {
  clock.playing = false;
  office.setAnimating(false);
  $("play").textContent = "▶ Phát lại";
}

function play() {
  if (clock.playing) return stop();
  if (lanes.every((lane) => lane.index === lane.events.length - 1)) seek(0);
  clock.playing = true;
  clock.last = performance.now();
  office.setAnimating(true);
  $("play").textContent = "⏸ Tạm dừng";
}

function seek(time) {
  generation += 1;
  clock.t = Math.max(0, Math.min(time, clock.duration));
  if (truck) Object.assign(beats, { intro: clock.t > 0.2, outro: clock.t >= truck.outroAt });
  for (const lane of lanes) {
    lane.index = -1;
    lane.actor.walkTo("reception", true);
    lane.actor.say("");
    lane.actor.stamp(null, "", false);
    lane.actor.think(false);
  }
  update(true);
}

// --- loading --------------------------------------------------------------------------------------
let runs = [];
const groups = new Map(); // "w57-reg-a-*" -> runs that differ only in the model variant

function syncHash() {
  const next = new URLSearchParams({ mode: $("mode").value, run: $("run-select").value, pkg: $("package-select").value });
  if (params.get("bench") === "1") next.set("bench", "1");
  history.replaceState(null, "", `#${next}`);
  const first = lanes[0];
  if (first) $("timeline-link").href = `/#run=${encodeURIComponent(first.run)}&pkg=${encodeURIComponent(first.pkg)}`;
}

async function loadTruck(run) {
  stop();
  const names = (await getJson(`/api/runs/${encodeURIComponent(run)}/packages`)).map((item) => item.package);
  const traces = await Promise.all(names.map(async (name) => {
    const query = new URLSearchParams({ run, pkg: name, after: "-1" });
    return { package: name, events: (await getJson(`/api/trace?${query}`)).filter((event) => event.type !== "thought") };
  }));
  truck = buildTruck(traces.filter((trace) => trace.events.length));
  office.clearWorkers(1);
  focusLane = 0;
  $("event-log").dataset.run = "";
  const variant = variantOf(run);
  const model = truck.events.find((event) => event.type === "run_start")?.model || "agent";
  const name = variant ? `A-${variant}` : model;
  const color = VARIANT_COLORS[variant] || "#61e8c2";
  lanes = [{ run, pkg: truck.packages[0]?.name || "", events: truck.events, offsets: truck.offsets, rooms: truck.events.map(roomFor),
             variant, model, name, color, index: -1, lane: 0, shownAt: 0, finishedAt: null,
             actor: office.addWorker({ id: run, name, color, lane: 0 }) }];
  office.setupTruck(truck.packages.map((pkg) => pkg.name));
  clock.duration = truck.duration;
  $("progress").max = String(Math.round(clock.duration * 10));
  $("package-name").textContent = `Xe hàng: ${truck.packages.length} gói từ lô ${run}`;
  $("package-meta").textContent = `${name} (${model}) kiểm từng thùng · thời gian thật của từng trace, ghép nối tiếp`;
  truckPanelKey = "";
  syncHash();
  seek(0);
}

async function packagesFor(choice) {
  if ($("mode").value !== "compare") return (await getJson(`/api/runs/${encodeURIComponent(choice)}/packages`)).map((item) => item.package);
  const lists = await Promise.all(groups.get(choice).map((run) => getJson(`/api/runs/${encodeURIComponent(run)}/packages`)));
  const [first, ...rest] = lists.map((list) => list.map((item) => item.package));
  return (first || []).filter((name) => rest.every((list) => list.includes(name)));
}

async function loadLanes() {
  stop();
  if (truck) {  // leaving truck mode: park an empty truck at the gate
    truck = null;
    office.setupTruck([]);
    office.setTruck({ phase: { where: "gate", progress: 1 }, items: [], truckLabel: "🚚 Xe hàng", houseText: "" }, true);
  }
  const choice = $("run-select").value;
  const pkg = $("package-select").value;
  const order = { LLM: 0, SLM: 1, TLM: 2 };
  const chosen = $("mode").value === "compare"
    ? [...groups.get(choice)].sort((a, b) => (order[variantOf(a)] ?? 9) - (order[variantOf(b)] ?? 9))
    : [choice];
  office.clearWorkers(chosen.length);
  focusLane = 0;
  $("event-log").dataset.run = "";
  lanes = await Promise.all(chosen.map((run, index) => makeLane(run, pkg, index)));
  clock.duration = Math.max(...lanes.map((lane) => lane.offsets.at(-1) ?? 0), 0.1);
  $("progress").max = String(Math.round(clock.duration * 10));
  $("package-name").textContent = pkg;
  const ends = lanes.map((lane) => lane.events.findLast((event) => event.type === "run_end"));
  $("package-meta").textContent = lanes.map((lane, at) => `${lane.name}: ${ends[at] ? `${ends[at].elapsed_s} s` : "đang chạy"}`).join(" · ");
  syncHash();
  office.focus(null, 0.8);
  seek(0);
}

async function loadChoice(preferredPackage) {
  if ($("mode").value === "truck") return loadTruck($("run-select").value);
  const names = await packagesFor($("run-select").value);
  $("package-select").replaceChildren(...names.map((name) => { const option = element("option", name); option.value = name; return option; }));
  $("package-select").value = names.includes(preferredPackage) ? preferredPackage : names[0] || "";
  if (names.length) await loadLanes();
}

async function loadMode(preferredRun, preferredPackage) {
  const mode = $("mode").value;
  const compare = mode === "compare";
  const choices = compare ? [...groups.keys()] : runs;
  document.body.dataset.mode = mode;
  $("truck-block").hidden = mode !== "truck";
  $("package-select").disabled = mode === "truck";
  if (mode === "truck") {
    // The truck story plays at 16x with the director camera following the truck and the parcels.
    clock.rate = 16;
    $("rate").value = "16";
    office.speed.value = 2.5;
    $("director").checked = true;
    office.setDirector(true);
  }
  $("run-select").replaceChildren(...choices.map((value) => {
    const option = element("option", compare ? value.replace("*", "{LLM,SLM,TLM}") : value);
    option.value = value;
    return option;
  }));
  $("run-label").textContent = compare ? "Bộ run" : "Run";
  const preferred = compare ? "w57-reg-a-*" : mode === "truck" ? "w57-reg-a-llm" : null;
  $("run-select").value = choices.includes(preferredRun) ? preferredRun : choices.includes(preferred) ? preferred : choices[0];
  await loadChoice(preferredPackage || "canary-fixture@1.0.0");
}

async function start() {
  runs = await getJson("/api/runs");
  for (const run of runs) {
    if (!variantOf(run)) continue;
    const key = run.replace(VARIANT, (_, lead) => `${lead}a-*`);
    groups.set(key, [...(groups.get(key) || []), run]);
  }
  for (const [key, members] of groups) if (members.length < 2) groups.delete(key);
  $("mode").querySelector('option[value="compare"]').disabled = groups.size === 0;
  // The truck story is the default view; "#mode=compare" races the models, "#mode=single" opens one run.
  const asked = params.get("mode");
  $("mode").value = asked === "single" ? "single" : asked === "compare" && groups.size ? "compare" : "truck";
  await loadMode(params.get("run"), params.get("pkg"));
}

$("mode").addEventListener("change", () => loadMode(null, $("package-select").value));
$("run-select").addEventListener("change", () => loadChoice($("package-select").value));
$("package-select").addEventListener("change", loadLanes);
$("play").addEventListener("click", play);
$("progress").addEventListener("input", (event) => { stop(); seek(Number(event.target.value) / 10); });
$("rate").addEventListener("change", (event) => { clock.rate = Number(event.target.value); office.speed.value = Math.min(2.5, Math.max(1, clock.rate / 4)); });
$("director").addEventListener("change", (event) => { office.setDirector(event.target.checked); office.focus(null, 0.8); });
$("reset-view").addEventListener("click", () => { $("director").checked = false; office.setDirector(false); });
$("previous").addEventListener("click", () => {
  stop();
  const lane = lanes[focusLane];
  if (lane) seek(lane.offsets[Math.max(0, lane.index - 1)] ?? 0);
});
$("next").addEventListener("click", () => {
  stop();
  const lane = lanes[focusLane];
  if (lane) seek(lane.offsets[Math.min(lane.events.length - 1, lane.index + 1)] ?? clock.duration);
});
addEventListener("keydown", (event) => {
  if (event.target.closest("select, input, button, a")) return; // keep native keys on controls
  if (event.key === " ") { event.preventDefault(); play(); }
  else if (event.key === "ArrowRight") $("next").click();
  else if (event.key === "ArrowLeft") $("previous").click();
  else if (["1", "2", "3"].includes(event.key) && lanes[Number(event.key) - 1]) { focusLane = Number(event.key) - 1; render(); }
});
start().catch((error) => { $("caption-who").textContent = `Không tải được dữ liệu: ${error.message}`; });
