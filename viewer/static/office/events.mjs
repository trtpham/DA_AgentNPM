// Map one agent trace event to a room of the 3D office. Pure: no Three.js, no DOM, so `node --test` covers it.
// Trace events come from agent/trace.py; their text fields are untrusted package data and are only ever
// shown with textContent by panel code.

export const ROOMS = Object.freeze({
  reception: { name: "Lễ tân", step: "Nhận diện gói" },
  code: { name: "Phòng đọc mã", step: "Phân tích mã nguồn" },
  intel: { name: "Phòng tra cứu", step: "Bối cảnh OSV/Registry" },
  lab: { name: "Phòng thí nghiệm", step: "Sandbox (chưa nối, W5-6)", locked: true },
  evidence: { name: "Bàn kiểm chứng", step: "Kiểm chứng bằng chứng" },
  decision: { name: "Phòng quyết định", step: "Luật R1–R8, dry-run" },
  hallway: { name: "Hành lang", step: "Lỗi hoặc cần thử lại" },
});

const CODE_TOOLS = new Set(["read_file", "extract_indicators", "deobfuscate"]);

/**
 * Decide which room an event belongs to.
 * @param {{type: string, tool?: string, kind?: string}} event one trace line
 * @returns {keyof typeof ROOMS}
 *
 * PROVISIONAL (O-0 spike). The real rule set is written in O-1; see KE_HOACH_VAN_PHONG_3D.md §2.1.
 */
export function roomFor(event) {
  if (event.type === "run_start" || event.tool === "read_manifest") return "reception";
  if (CODE_TOOLS.has(event.tool)) return "code";
  if (event.type === "sandbox_result") return "lab";
  if (event.type === "verdict") return "evidence";
  if (event.type === "human_review") return "decision";
  if (event.type === "decision" || event.type === "run_end") return "decision";
  return "hallway";
}
