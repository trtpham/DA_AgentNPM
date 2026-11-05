// Truck scenarios: every situation a package install can meet, built from real traces where they exist
// and from clearly labelled simulations where they do not. Pure (no DOM, no Three.js).
//
// source = "real":   a real agent trace from reports/ (the run and package are named);
//          "rule":   a rule that exists in agent/decide.py but has no trace yet (R1, R3, R5, R2 by limit);
//          "design": a product step that is not in the code yet (green lane, cache, typosquat check,
//                    human review outcome, previously installed warning).
// Simulated events carry `synthetic: true` and never pretend to be model output: their text says so.

export const SOURCES = {
  real: { badge: "THẬT", hint: "Trace thật của agent trong reports/" },
  rule: { badge: "MÔ PHỎNG", hint: "Luật có trong agent/decide.py, chưa có trace thật" },
  design: { badge: "THIẾT KẾ", hint: "Bước của thiết kế sản phẩm, chưa có trong code" },
};

const real = (run, pkg, extra = {}) => ({ kind: "real", run, pkg, ...extra });
const sim = (name, story, extra = {}) => ({ kind: "sim", name, story, ...extra });

export const SCENARIOS = [
  { id: "batch", title: "Lô thực nghiệm thật (chọn run)", useRun: true,
    what: "Toàn bộ gói của một lượt chạy thật, đúng như agent đã xử lý.", parcels: [] },
  { id: "safe", title: "1. Cài gói an toàn → giao hàng",
    what: "Đa số gói không có script cài đặt (làn xanh) hoặc đã kiểm trước đó (bộ nhớ đệm); gói có script được agent duyệt. Cả xe an toàn nên được giao.",
    parcels: [sim("demo-date-fmt@2.1.0", "green"), sim("demo-colors@1.4.0", "green"), sim("demo-cached-lib@3.0.0", "cache"),
              real("w57-reg-a-llm", "benign-install-fixture@1.0.0")] },
  { id: "malicious-dep", title: "2. Gói độc ẩn trong cây phụ thuộc → chặn cả xe",
    what: "Một gói con đọc khóa SSH. Nghiêm ngặt nhất thắng: giữ cả xe, gói độc vào cách ly, phiếu gửi người dùng.",
    parcels: [sim("demo-web-app-kit@1.0.0", "green"), real("w57-reg-a-llm", "benign-install-fixture@1.0.0"),
              real("w57-reg-a-llm", "canary-fixture@1.0.0"), sim("demo-colors@1.4.0", "green")] },
  { id: "osv", title: "3. OSV đã biết độc: chặn trước, phân tích sau",
    what: "Cổng thấy gói trong danh sách đen nên chặn giao ngay. Agent vẫn phân tích bản cách ly (không được biết kết quả OSV) để làm phiếu có bằng chứng.",
    parcels: [real("w57-reg-a-llm", "canary-fixture@1.0.0", { osv: true }), sim("demo-colors@1.4.0", "green")] },
  { id: "obfuscated", title: "4. Mã bị làm rối → người xem quyết định từ chối",
    what: "Agent đọc qua #pretty nhưng chưa đủ chắc (R8). Người xem đọc phiếu và từ chối.",
    parcels: [real("w57c-obf-a-llm", "obfuscated-install-fixture@1.0.0", { human: "deny" })] },
  { id: "native", title: "5. Gói lớn tải mã ngoài (swc) → người xem cho qua",
    what: "Script tải thêm mã và file .node ngoài gói; agent không thấy hết nên chuyển người (R7_review). Người xem duyệt cho qua, xe được giao.",
    parcels: [real("w57-reg-a-llm", "@swc/core@1.7.36", { human: "approve" }), sim("demo-colors@1.4.0", "green")] },
  { id: "model-fail", title: "6. Mô hình lỗi / lặp kết luận sai (R2)",
    what: "Model nhỏ trả JSON hỏng hoặc trích dòng chưa đọc nhiều lần. Hệ thống dừng và chuyển người, không bao giờ tự cho phép.",
    parcels: [real("w57-reg-a-tlm", "no-hook-fixture@1.0.0"), real("week4-dev-a-tlm-20261103", "@swc/core@1.7.25")] },
  { id: "fake-evidence", title: "7. AI bịa bằng chứng (R3)",
    what: "Model kết luận độc hại nhưng trích một dòng không tồn tại. Bộ kiểm chứng loại bằng chứng, luật hạ xuống người xem.",
    parcels: [sim("demo-fake-evidence@0.9.0", "r3")] },
  { id: "osv-disagree", title: "8. OSV báo độc, AI nói lành (R5)",
    what: "Hai nguồn bất đồng: luật không cho tự động cho phép, chuyển người xem đối chiếu.",
    parcels: [sim("demo-osv-disagree@1.2.0", "r5")] },
  { id: "sandbox", title: "9. Sandbox bắt quả tang (R1 — sau W5-6)",
    what: "Phân tích tĩnh chưa thấy gì, nhưng chạy thử trong sandbox thì script đọc file khóa SSH mồi. R1 từ chối ngay.",
    parcels: [sim("demo-sandbox-thief@0.1.0", "r1")] },
  { id: "typosquat", title: "10. Tên gần giống gói nổi tiếng",
    what: "lodahs gần giống lodash. Cổng gắn cờ trước khi tới AI; chuyển người xem xác nhận đúng tên muốn cài.",
    parcels: [sim("lodahs@4.17.21", "typo")] },
  { id: "unreachable", title: "11. Không tải được gói / vượt giới hạn bước",
    what: "Registry lỗi hoặc tarball không giải nén an toàn được; một gói khác làm agent hết 15 bước. Cả hai đều R2: chuyển người.",
    parcels: [sim("demo-unreachable@9.9.9", "fetch_error"), sim("demo-endless@1.0.0", "limit")] },
  { id: "installed-before", title: "12. Gói độc đã từng được cài trước đó",
    what: "Như tình huống 2, nhưng máy người dùng đã cài phiên bản này trước khi có hệ thống: phiếu yêu cầu đổi token và khóa ngay.",
    parcels: [real("w57-reg-a-llm", "canary-fixture@1.0.0", { installedBefore: true })] },
];

// --- synthetic traces -------------------------------------------------------------------------------
const NOTE = "[mô phỏng] ";
function stamp(base, seconds) { return new Date(base + seconds * 1000).toISOString(); }

function events(name, steps) {
  const base = Date.UTC(2026, 10, 5, 8, 0, 0);
  let at = 0;
  return steps.map(([gap, event]) => {
    at += gap;
    return { ...event, ts: stamp(base, at), package: name, synthetic: true };
  });
}

const manifest = (hooks) => [
  [0.4, { type: "tool_call", tool: "read_manifest", args: { package: "thư mục gói" } }],
  [0.2, { type: "tool_result", tool: "read_manifest", ok: true, summary: "OK",
          data_preview: hooks ? '{"scripts": {"content": {"postinstall": "node setup.js"}}}' : '{"scripts": {"untrusted": true, "content": {}}}' }],
];
const read = (file, start, end, preview) => [
  [3.5, { type: "tool_call", tool: "read_file", args: { file, start, end } }],
  [0.2, { type: "tool_result", tool: "read_file", ok: true, summary: "OK", data_preview: preview }],
];
const verdict = (label, confidence, description, behaviors) => [
  [5, { type: "verdict", valid: true, verdict: { label, confidence, description, behaviors,
                                                  remediation: label === "benign" ? [] : ["Chặn script bằng npm deny-scripts", "Ghim về phiên bản trước an toàn"] } }],
];
const decide = (label, action, rule, reason, checks = []) => [
  [0.6, { type: "decision", final_label: label, final_action: action, rule, reasons: [reason], evidence_checks: checks }],
];
const end = (steps) => [[0.3, { type: "run_end", steps, elapsed_s: null }]];

export function synthesize(name, story) {
  const start = [[0, { type: "run_start", model: "(không cần mô hình)", max_steps: 15 }]];
  switch (story) {
    case "green":
      return events(name, [...start, ...manifest(false),
        ...decide("benign", "approve", "LÀN XANH", `${NOTE}Không có script cài đặt: npm không chạy mã nào lúc cài, không cần AI`), ...end(0)]);
    case "cache":
      return events(name, [...start,
        ...decide("benign", "approve", "BỘ NHỚ ĐỆM", `${NOTE}Cùng tên@phiên bản và mã băm đã được duyệt trước đó`), ...end(0)]);
    case "typo":
      return events(name, [...start,
        ...decide("suspicious", "review", "TÊN GẦN GIỐNG", `${NOTE}Tên gần giống gói phổ biến "lodash" (đảo 2 ký tự); xác nhận đúng gói muốn cài`), ...end(0)]);
    case "fetch_error":
      return events(name, [...start,
        [1.5, { type: "error", kind: "fetch_failed", message: `${NOTE}npm pack thất bại: registry trả lỗi 503 / tarball có đường dẫn ra ngoài thư mục gói` }],
        ...decide("suspicious", "review", "R2", `${NOTE}Analysis failed or reached its step limit`), ...end(0)]);
    case "limit": {
      const loop = [];
      for (let step = 0; step < 4; step += 1) loop.push(...read("lib/loader.js", 1 + step * 150, 150 + step * 150, `${NOTE}…mã rất dài, cần đọc thêm…`));
      return events(name, [...start, ...manifest(true), ...loop,
        [1, { type: "limit", reason: "max_steps" }],
        ...decide("suspicious", "review", "R2", `${NOTE}Analysis failed or reached its step limit`), ...end(15)]);
    }
    case "r3":
      return events(name, [...start, ...manifest(true), ...read("setup.js", 1, 40, `${NOTE}const os = require("os"); console.log("setup");`),
        ...verdict("malicious", 0.9, `${NOTE}Mô hình cho rằng script gửi dữ liệu ra ngoài`,
                   [{ behavior: "Gửi dữ liệu tới máy chủ lạ", technique: "exfiltration", severity: "high",
                      evidence: { file: "setup.js", lines: "999" }, analysis: `${NOTE}trích dòng 999 nhưng file chỉ có 40 dòng`, impact: "—" }]),
        ...decide("suspicious", "review", "R3", "No behavior has verified file and lines", [{ file: "setup.js", lines: "999", exists: false }]), ...end(2)]);
    case "r5":
      return events(name, [...start, ...manifest(true), ...read("setup.js", 1, 30, `${NOTE}const fs = require("fs"); fs.mkdirSync("build");`),
        ...verdict("benign", 0.92, `${NOTE}Script chỉ tạo thư mục build trong gói`,
                   [{ behavior: "Tạo thư mục build", technique: "fs.mkdirSync", severity: "low",
                      evidence: { file: "setup.js", lines: "1" }, analysis: `${NOTE}trong thư mục gói`, impact: "Không đáng kể" }]),
        ...decide("suspicious", "review", "R5", "OSV MAL signal blocks automatic approval", [{ file: "setup.js", lines: "1", exists: true }]), ...end(2)]);
    case "r1":
      return events(name, [...start, ...manifest(true), ...read("install.js", 1, 60, `${NOTE}require("./lib/init")();`),
        [4, { type: "sandbox_result", outcome: "ok", canary_touched: ["ssh"],
              summary: `${NOTE}Chạy trong container tắt mạng: script mở /home/agent/.ssh/id_rsa (khóa mồi) và thử kết nối ra ngoài (bị chặn)` }],
        ...verdict("malicious", 0.97, `${NOTE}Đọc khóa SSH khi cài đặt (bắt được trong sandbox)`,
                   [{ behavior: "Đọc khóa SSH lúc cài", technique: "credential access", severity: "high",
                      evidence: { file: "lib/init.js", lines: "12" }, analysis: `${NOTE}xác nhận bằng sandbox: canary ssh bị chạm`, impact: "Lộ khóa SSH" }]),
        ...decide("malicious", "deny", "R1", "Sandbox canary touched", [{ file: "lib/init.js", lines: "12", exists: true }]), ...end(3)]);
    default:
      return events(name, [...start, ...end(0)]);
  }
}

/** A human reviewer's decision appended after a review verdict (design: not in the code yet). */
export function humanReview(events_, action) {
  const last = events_.at(-1);
  const base = Date.parse(last?.ts) || Date.UTC(2026, 10, 5, 8, 0, 0);
  return [...events_, { type: "human_review", final_action: action, reviewer: "Người xem", synthetic: true, package: last?.package,
                        ts: stamp(base, 6), reason: action === "approve"
                          ? `${NOTE}Người xem đọc phiếu, xác nhận nguồn tải là bản phát hành chính thức, cho phép`
                          : `${NOTE}Người xem đọc #pretty, thấy chuỗi giải mã không cần thiết cho việc cài, từ chối` }];
}

/**
 * Build the parcels of a scenario. `loadTrace(run, pkg)` fetches a real trace (or [] if missing).
 * Returns [{ package, events, source, osv, installedBefore }] in truck order.
 */
export async function composeScenario(scenario, loadTrace) {
  const parcels = [];
  for (const parcel of scenario.parcels) {
    if (parcel.kind === "real") {
      let trace = (await loadTrace(parcel.run, parcel.pkg)).filter((event) => event.type !== "thought");
      if (!trace.length) continue; // the run is not in this reports/ folder
      if (parcel.human) trace = humanReview(trace, parcel.human);
      parcels.push({ package: parcel.pkg, events: trace, source: parcel.human ? "real+design" : "real", run: parcel.run,
                     osv: Boolean(parcel.osv), installedBefore: Boolean(parcel.installedBefore) });
    } else {
      const source = ["green", "cache", "typo"].includes(parcel.story) ? "design" : "rule";
      parcels.push({ package: parcel.name, events: synthesize(parcel.name, parcel.story), source,
                     osv: parcel.story === "r5", installedBefore: false });
    }
  }
  return parcels;
}
