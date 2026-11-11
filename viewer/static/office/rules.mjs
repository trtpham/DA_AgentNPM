// The hard decision rules of agent/decide.py, in plain Vietnamese, in the order the code checks them.
// decide() returns at the first rule that matches, so for a decision made by rule X every rule above X
// is known not to match and every rule below X was never looked at. Pure: no DOM, `node --test` covers it.

export const RULE_LADDER = Object.freeze([
  { code: "R1", when: "Sandbox thấy gói chạm file khóa mồi (canary)", then: "Độc hại → chặn" },
  { code: "R2", when: "Phân tích lỗi hoặc dùng hết giới hạn bước", then: "Đáng ngờ → người xem" },
  { code: "R3", when: "Mô hình nêu hành vi nhưng không vị trí file:dòng nào có thật trong gói", then: "Đáng ngờ → người xem" },
  { code: "R4", when: "Kết luận độc hại mà không có bằng chứng thật (lưới an toàn)", then: "Đáng ngờ → người xem" },
  { code: "R5", when: "OSV báo gói là mã độc nhưng mô hình nói lành", then: "Đáng ngờ → người xem" },
  { code: "R6", when: "Độc hại, tin cậy ≥ ngưỡng chặn (mặc định 0,8), có bằng chứng thật", then: "Độc hại → chặn" },
  { code: "R7", when: "Lành, tin cậy ≥ ngưỡng cho phép (mặc định 0,8), có bằng chứng thật — và không vướng điều kiện R7_* nào", then: "Lành → cho phép" },
  { code: "R8", when: "Không rơi vào luật nào ở trên (ví dụ tin cậy thấp, hoặc nhãn đáng ngờ)", then: "Giữ nhãn → người xem" },
]);

// R7 variants: a benign verdict that met the threshold but is held back for a person.
export const R7_VARIANTS = Object.freeze({
  R7_review: "Chưa được phép tự động cho phép: đường cài đặt chưa xem hết (ví dụ tải mã ngoài gói, file nhị phân, file không đọc được)",
  R7_flow: "Có luồng dữ liệu nhạy cảm (secret/biến môi trường) đi ra mạng",
  R7_sandbox: "Sandbox thấy gói ghi file khởi động",
  R7_risk: "Kết luận lành nhưng không giải thích các dòng cài đặt rủi ro",
});

export const TERMS = Object.freeze({
  "dry-run": "Chạy thử: chỉ in lệnh npm approve-scripts / deny-scripts sẽ chạy, không sửa package.json.",
  verdict: "Kết luận JSON mô hình nộp: nhãn, độ tin cậy, từng hành vi kèm file:dòng. Chỉ là đề xuất.",
  "bằng chứng": "Vị trí file:dòng mô hình trích. Hệ thống kiểm file và dòng đó có thật trong gói hay không.",
  "nhãn chuẩn": "Nhãn do người kiểm tra ghi trong data/labels.csv, dùng để chấm agent đúng hay sai.",
  "tin cậy": "Con số 0–1 mô hình tự nêu. Luật chỉ chặn/cho phép tự động khi ≥ ngưỡng (mặc định 0,8).",
});

/** The family code of a rule: "R7_review" -> "R7", unknown -> "". */
export function ruleFamily(code) {
  const match = /^R([1-8])(?:_[a-z]+)?$/.exec(String(code || ""));
  return match ? `R${match[1]}` : "";
}

/**
 * The ladder for one decision: each rule marked "skipped" (checked, did not match), "fired" or "unchecked".
 * @param {string} code the rule from the trace, e.g. "R7_review"
 * @returns {{code: string, when: string, then: string, state: "skipped"|"fired"|"unchecked", variant?: string}[]}
 */
export function ruleLadder(code) {
  const family = ruleFamily(code);
  const at = RULE_LADDER.findIndex((rule) => rule.code === family);
  return RULE_LADDER.map((rule, index) => {
    const state = at < 0 ? "unchecked" : index < at ? "skipped" : index === at ? "fired" : "unchecked";
    const variant = state === "fired" && code !== family ? R7_VARIANTS[code] : undefined;
    return variant ? { ...rule, state, variant, then: "Lành → người xem (bị giữ lại)" } : { ...rule, state };
  });
}

/** One sentence: which rule decided, and what it means. */
export function ruleSentence(code) {
  const family = ruleFamily(code);
  const rule = RULE_LADDER.find((item) => item.code === family);
  if (!rule) return "Trace cũ không ghi luật nào đã quyết định.";
  if (R7_VARIANTS[code]) return `${code}: mô hình nói lành và đủ tin cậy, nhưng bị giữ lại cho người xem vì ${R7_VARIANTS[code].toLowerCase()}.`;
  return `${code}: ${rule.when.charAt(0).toLowerCase()}${rule.when.slice(1)} → ${rule.then.toLowerCase()}.`;
}
