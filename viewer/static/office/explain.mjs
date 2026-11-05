// Turn one trace event into a plain-Vietnamese "input -> processing -> output" step.
// Pure (no DOM, no Three.js) so `node --test` covers it. Returned strings are shown with textContent only;
// anything copied from the trace (args, previews, reasons) is untrusted package or model data.

export const TOOL_INFO = Object.freeze({
  read_manifest: { robot: "Robot manifest", what: "Đọc package.json: script cài đặt, phụ thuộc, file nhị phân. Chỉ đọc, không chạy npm." },
  extract_indicators: { robot: "Robot quét mã", what: "Quét file mà script cài đặt dùng, tìm URL, IP, eval, child_process, process.env, chuỗi mã hóa dài." },
  read_file: { robot: "Robot đọc mã", what: "Đọc đúng các dòng được yêu cầu trong file của gói. Chỉ đọc chữ, KHÔNG chạy mã." },
  deobfuscate: { robot: "Robot giải rối", what: "Định dạng lại mã viết một dòng và giải các chuỗi base64/hex để đọc được." },
});

export const ERROR_INFO = Object.freeze({
  normalized_output: "Chuẩn hóa câu trả lời của mô hình: bỏ mã MITRE chưa kiểm chứng, sửa định dạng số dòng.",
  invalid_verdict: "Kết luận bị trả lại: trích bằng chứng ở dòng mô hình chưa đọc hoặc không tồn tại.",
  repeated_invalid: "Mô hình lặp lại cùng một kết luận sai nhiều lần, hệ thống dừng lại.",
  bad_tool_call: "Mô hình gọi công cụ sai tên hoặc sai tham số.",
  json_invalid: "Câu trả lời không phải JSON hợp lệ, yêu cầu viết lại.",
  truncated_output: "Câu trả lời bị cắt vì quá dài, yêu cầu viết ngắn hơn.",
  model_error: "Không gọi được mô hình (Ollama lỗi hoặc hết giờ).",
  fetch_failed: "Không tải hoặc giải nén an toàn được gói (registry lỗi, hoặc tarball có đường dẫn thoát ra ngoài).",
});

const ACTIONS = { approve: "CHO PHÉP", review: "CHUYỂN NGƯỜI XEM", deny: "TỪ CHỐI" };
const LABELS = { benign: "Lành tính", suspicious: "Nghi vấn", malicious: "Độc hại" };
const clip = (text, length) => {
  const value = String(text ?? "").replace(/\s+/g, " ").trim();
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
};

export function argsText(args) {
  if (!args || typeof args !== "object") return "";
  if (args.file) {
    const range = args.start ? ` dòng ${args.start}${args.end && args.end !== args.start ? `–${args.end}` : ""}` : " (từ đầu file)";
    return `${args.file}${range}`;
  }
  if (args.package) return "thư mục gói đã giải nén";
  return Object.keys(args).length ? clip(JSON.stringify(args), 60) : "toàn bộ đường cài đặt của gói";
}

// Summarise a tool's data preview: JSON indicators become a count, file text becomes its first lines.
export function previewText(event) {
  const preview = event.data_preview;
  if (!preview) return "";
  if (event.tool === "extract_indicators") {
    const types = [...new Set([...String(preview).matchAll(/"type":\s*"([a-z_]+)"/g)].map((match) => match[1]))];
    return types.length ? `chỉ báo: ${types.slice(0, 5).join(", ")}` : clip(preview, 80);
  }
  if (event.tool === "read_manifest") {
    const hooks = [...String(preview).matchAll(/"(preinstall|install|postinstall)":\s*"([^"]*)"/g)].map((match) => `${match[1]}: ${match[2]}`);
    return hooks.length ? `hook ${hooks.slice(0, 2).join("; ")}` : "không thấy script cài đặt";
  }
  return clip(preview, 90);
}

function callFor(events, index) {
  const result = events[index];
  for (let at = index - 1; at >= 0; at -= 1) {
    if (events[at].type === "tool_call" && events[at].tool === result.tool) return events[at];
  }
  return null;
}

/**
 * @returns {{actor: "system"|"model"|"tool"|"rules", who: string, title: string,
 *            input: string, process: string, output: string, untrustedOutput: boolean}}
 */
export function explainStep(events, index) {
  const step = explainEvent(events, index);
  // Simulated steps (truck scenarios) say so in the title, so nobody mistakes them for agent output.
  return events[index]?.synthetic ? { ...step, title: `[MÔ PHỎNG] ${step.title}` } : step;
}

function explainEvent(events, index) {
  const event = events[index] || {};
  const step = { actor: "system", who: "Hệ thống", title: event.type || "", input: "—", process: "—", output: "—", untrustedOutput: false };
  switch (event.type) {
    case "run_start":
      return { ...step, title: "Nhận gói cần kiểm tra", input: `Gói ${event.package || ""} đã tải bằng npm pack, chưa chạy script nào`,
               process: `Khởi động agent dùng mô hình ${event.model}, tối đa ${event.max_steps ?? 15} bước`, output: "Bắt đầu điều tra" };
    case "tool_call": {
      const info = TOOL_INFO[event.tool];
      return { ...step, actor: "model", who: "Mô hình AI", title: `Mô hình yêu cầu công cụ ${event.tool}`,
               input: argsText(event.args), process: info ? `Gửi yêu cầu cho ${info.robot}` : "Yêu cầu một công cụ không có trong danh sách",
               output: "Chờ robot trả kết quả…" };
    }
    case "tool_result": {
      const info = TOOL_INFO[event.tool];
      const call = callFor(events, index);
      const preview = previewText(event);
      return { ...step, actor: "tool", who: info?.robot || event.tool, title: `${info?.robot || event.tool} trả kết quả`,
               input: call ? argsText(call.args) : "—", process: info?.what || event.tool,
               output: event.ok ? `${event.summary || "OK"}${preview ? ` — ${preview}` : ""}` : `Lỗi: ${event.summary || "không đọc được"}`,
               untrustedOutput: Boolean(preview) };
    }
    case "error":
      return { ...step, actor: "rules", who: "Bộ kiểm tra", title: `Kiểm tra phát hiện: ${event.kind}`,
               input: "Câu trả lời vừa nhận từ mô hình", process: ERROR_INFO[event.kind] || "Phát hiện bất thường trong lượt chạy",
               output: clip(event.message || "", 110) || "—", untrustedOutput: true };
    case "verdict": {
      const verdict = event.verdict || {};
      const behaviors = verdict.behaviors || [];
      return { ...step, actor: "model", who: "Mô hình AI", title: event.valid ? "Mô hình nộp kết luận" : "Mô hình nộp kết luận (chưa hợp lệ)",
               input: "Mọi đoạn mã và chỉ báo đã đọc", process: "Viết kết luận JSON: nhãn, độ tin cậy, từng hành vi kèm file:dòng",
               output: `${LABELS[verdict.label] || verdict.label || "?"} · tin cậy ${Math.round((verdict.confidence ?? 0) * 100)}% · ${behaviors.length} hành vi`
                 + (event.valid ? "" : ` · lỗi: ${clip((event.validation_errors || []).join("; "), 60)}`),
               untrustedOutput: true };
    }
    case "decision": {
      const checks = event.evidence_checks || [];
      const good = checks.filter((check) => check.exists).length;
      const command = event.final_action === "approve" ? `npm approve-scripts ${event.package || ""}`
        : event.final_action === "deny" ? `npm deny-scripts ${event.package || ""}` : "không chạy lệnh, chờ người xem";
      return { ...step, actor: "rules", who: "Thẩm phán luật", title: `Luật ${event.rule} ra quyết định`,
               input: `Kết luận của mô hình + ${checks.length} bằng chứng (✔ ${good} · ✘ ${checks.length - good})`,
               process: `Luật ${event.rule}: ${clip((event.reasons || [])[0] || "", 90)}`,
               output: `${LABELS[event.final_label] || event.final_label} → ${ACTIONS[event.final_action] || "—"} · ${command} (dry-run)` };
    }
    case "sandbox_result":
      return { ...step, actor: "tool", who: "Robot sandbox", title: "Chạy thử script trong sandbox",
               input: "Gói đã giải nén, trong container tắt mạng, chỉ đọc, có file khóa mồi",
               process: "Chạy npm install dưới strace, ghi tiến trình, file và kết nối",
               output: `${(event.canary_touched || []).length ? `Chạm khóa mồi: ${event.canary_touched.join(", ")}` : "Không chạm khóa mồi"} — ${clip(event.summary || "", 90)}`,
               untrustedOutput: true };
    case "human_review":
      return { ...step, actor: "system", who: "Người xem", title: `Người xem quyết định: ${ACTIONS[event.final_action] || event.final_action}`,
               input: "Phiếu chờ duyệt: lý do của luật, bằng chứng file:dòng",
               process: clip(event.reason || "Đọc phiếu và quyết định", 110),
               output: `${ACTIONS[event.final_action] || "—"} (thay cho kết luận chuyển người xem)` };
    case "run_end":
      return { ...step, title: "Hoàn tất", input: "Toàn bộ lượt chạy", process: "Ghi trace và số đo",
               output: `${event.steps} bước mô hình · ${event.elapsed_s} giây${event.tokens_per_s ? ` · ${event.tokens_per_s} token/giây` : ""}` };
    case "limit":
      return { ...step, actor: "rules", who: "Bộ kiểm tra", title: "Hết giới hạn 15 bước", input: "Số bước đã dùng",
               process: "Không có kết luận hợp lệ trong giới hạn", output: "Chuyển người xem (luật R2)" };
    default:
      return step;
  }
}

export function thinkingStep(model, waited) {
  return { actor: "model", who: "Mô hình AI", title: "Mô hình đang suy nghĩ",
           input: "Kết quả công cụ vừa nhận + toàn bộ hội thoại trước đó",
           process: `${model} đang sinh câu trả lời trên GPU (đã ${waited.toFixed(1)} giây)`,
           output: "Bước tiếp theo: gọi thêm công cụ hoặc nộp kết luận", untrustedOutput: false };
}
