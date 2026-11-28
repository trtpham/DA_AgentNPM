// Pure helpers for the 2D result pages (single package & run summary). No DOM, covered by `node --test`.
// All strings extracted from traces remain untrusted data; callers render them with textContent only.
import { previewOf } from "./office/explain.mjs";

const TECHNIQUE_SOURCE = {
  "read-secret-file": "Tệp nhạy cảm (.npmrc / .ssh / .aws / credentials)",
  "read-env": "Biến môi trường (process.env)",
  "read-package-file": "Tệp trong gói cài đặt",
  "write-package-file": "Mã script trong gói",
  "write-outside-package": "Mã script trong gói",
  "network-request": "Script cài đặt / dữ liệu cục bộ",
  "binary-download": "URL tải nhị phân từ xa",
  "download-code": "URL mã nguồn từ xa",
  "execute-process": "Hook cài đặt (preinstall / install / postinstall)",
  "native-build": "Mã nguồn C/C++ / binding.gyp",
  "decode-data": "Chuỗi mã hóa (base64 / hex / obfuscated)",
  "dynamic-eval": "Chuỗi / mã được nạp động",
  "print-output": "Dữ liệu trong script cài đặt",
};

const TECHNIQUE_ACTION = {
  "read-secret-file": "Đọc tệp bí mật",
  "read-env": "Đọc biến môi trường",
  "read-package-file": "Đọc tệp trong gói",
  "write-package-file": "Ghi tệp trong gói",
  "write-outside-package": "Ghi tệp ngoài thư mục gói",
  "network-request": "Gửi / mở kết nối mạng",
  "binary-download": "Tải tệp nhị phân dựng sẵn",
  "download-code": "Tải và nạp mã từ xa",
  "execute-process": "Chạy tiến trình / lệnh hệ thống",
  "native-build": "Biên dịch addon native (node-gyp)",
  "decode-data": "Giải mã / giải rối chuỗi",
  "dynamic-eval": "Thực thi mã động (eval / Function)",
  "print-output": "In thông báo ra console",
};

const TECHNIQUE_TARGET = {
  "read-secret-file": "Bộ nhớ / luồng xử lý của script",
  "read-env": "Cấu hình / biến môi trường tiến trình",
  "read-package-file": "Logic nội bộ của script",
  "write-package-file": "Thư mục cài đặt của gói",
  "write-outside-package": "Thư mục hệ thống / thư mục người dùng",
  "network-request": "Máy chủ ngoài qua HTTP/TCP",
  "binary-download": "Tệp nhị phân trong thư mục gói",
  "download-code": "Tiến trình Node / shell cục bộ",
  "execute-process": "Tiến trình con của hệ điều hành",
  "native-build": "Tệp nhị phân .node cục bộ",
  "decode-data": "Chuỗi lệnh hoặc dữ liệu rõ",
  "dynamic-eval": "Ngữ cảnh thực thi JavaScript",
  "print-output": "stdout / stderr",
};

/** Parse "12" or "12-18" into {start, end}, or null if invalid. */
export function parseLineRange(text) {
  const match = /^([1-9]\d*)(?:-([1-9]\d*))?$/.exec(String(text || "").trim());
  if (!match) return null;
  const start = Number(match[1]);
  const end = match[2] ? Number(match[2]) : start;
  return end >= start ? { start, end } : { start: end, end: start };
}

/**
 * Derive a "Source -> Action -> Target" triplet for one model behavior.
 * Prefers concrete tokens found in analysis/impact (URLs, paths, env vars, commands), falling back
 * to technique defaults so every behavior reads consistently in Vietnamese.
 */
export function behaviorTriplet(behavior) {
  const item = behavior || {};
  const tech = String(item.technique || "").trim().toLowerCase();
  const analysis = String(item.analysis || "");
  const impact = String(item.impact || "");
  const combined = `${analysis} ${impact}`;
  const loc = item.evidence?.file ? `${item.evidence.file}:${item.evidence.lines ?? "?"}` : "";

  const secretMatch = combined.match(/(?:~\/)?\.(?:npmrc|ssh\/[^\s,'")]+|aws\/[^\s,'")]+|env|netrc|gitconfig)/i);
  const envMatch = combined.match(/process\.env(?:\.[A-Za-z0-9_]+)?/);
  const urlMatch = combined.match(/https?:\/\/[^\s,'")]+/i);
  const cmdMatch = combined.match(/\b(?:curl|wget|bash|sh|powershell|cmd|node-gyp|sw_vers|chmod|chown|python|npm|npx)\b/i);

  let source = TECHNIQUE_SOURCE[tech] || (loc ? `Mã tại ${loc}` : "Script cài đặt");
  if (secretMatch) source = secretMatch[0];
  else if (envMatch && (tech === "read-env" || !TECHNIQUE_SOURCE[tech])) source = envMatch[0];

  const action = TECHNIQUE_ACTION[tech]
    ? `${TECHNIQUE_ACTION[tech]} (${tech})`
    : String(item.behavior || tech || "Hành vi chưa phân loại");

  let target = TECHNIQUE_TARGET[tech] || "Môi trường cài đặt";
  if (urlMatch) target = urlMatch[0];
  else if (cmdMatch && tech === "execute-process") target = `Lệnh ${cmdMatch[0]}`;
  else if (impact.trim()) target = impact.trim().length > 90 ? `${impact.trim().slice(0, 89)}…` : impact.trim();

  return { source, action, target };
}

/**
 * Find the best read_file excerpt in `events` covering `file` and `lines`.
 * Returns `{file, start, end, citedStart, citedEnd, lines: [{num, text, cited}], exact}` or null.
 */
export function extractSnippet(events, file, linesText) {
  if (!file || !Array.isArray(events)) return null;
  const range = parseLineRange(linesText);
  const reads = [];
  for (let i = 0; i < events.length; i += 1) {
    const call = events[i];
    if (call?.type !== "tool_call" || call.tool !== "read_file" || call.args?.file !== file) continue;
    // Match the corresponding tool_result right after or shortly after.
    let result = null;
    for (let j = i + 1; j < events.length; j += 1) {
      if (events[j]?.type === "tool_result" && events[j].tool === "read_file") {
        result = events[j];
        break;
      }
      if (events[j]?.type === "tool_call") break;
    }
    if (!result || !result.ok) continue;
    const content = previewOf(result);
    if (!content) continue;
    const rawLines = content.split(/\r?\n/);
    const start = Number.isInteger(call.args?.start) && call.args.start >= 1 ? call.args.start : 1;
    const end = start + rawLines.length - 1;
    reads.push({ start, end, rawLines, stepIndex: i + 1 });
  }
  if (!reads.length) return null;

  let chosen = null;
  let covers = false;
  if (range) {
    // Prefer a wider context read (>= 3 lines) that covers the cited range, else an exact check read.
    const covering = reads.filter((r) => r.start <= range.start && r.end >= range.end);
    if (covering.length) {
      covers = true;
      chosen = covering.sort((a, b) => (b.rawLines.length - a.rawLines.length) || (a.start - b.start))[0];
    } else {
      chosen = reads[0];
    }
  } else {
    chosen = reads[0];
  }

  // Window around the cited range (up to 7 lines before and 7 lines after, max 18 lines) for readability.
  let sliceStart = 0;
  let sliceEnd = chosen.rawLines.length;
  if (range && covers && chosen.rawLines.length > 18) {
    const relStart = Math.max(0, range.start - chosen.start - 5);
    const relEnd = Math.min(chosen.rawLines.length, range.end - chosen.start + 6);
    sliceStart = relStart;
    sliceEnd = Math.max(relEnd, Math.min(chosen.rawLines.length, relStart + 16));
  } else if (chosen.rawLines.length > 18) {
    sliceEnd = 18;
  }

  const lines = [];
  for (let idx = sliceStart; idx < sliceEnd; idx += 1) {
    const num = chosen.start + idx;
    const cited = Boolean(range && num >= range.start && num <= range.end);
    lines.push({ num, text: chosen.rawLines[idx], cited });
  }
  return {
    file,
    start: chosen.start + sliceStart,
    end: chosen.start + sliceEnd - 1,
    citedStart: range?.start ?? null,
    citedEnd: range?.end ?? null,
    covers,
    stepIndex: chosen.stepIndex,
    lines,
  };
}

/** Extract sandbox report from trace events (run_sandbox / sandbox_report / sandbox_result) if present. */
export function sandboxFromEvents(events) {
  if (!Array.isArray(events)) return null;
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const event = events[i];
    if (event?.type === "sandbox_result") {
      return {
        used_in_run: true,
        ok: event.outcome === "ok",
        outcome: event.outcome,
        canary_touched: event.canary_touched || [],
        connects: event.connects || [],
        persistence_writes: event.persistence_writes || [],
        process_tree: event.process_tree || [],
        package_files_outside: event.package_files_outside || [],
        summary: event.summary || "",
      };
    }
    if (event?.type === "tool_result" && (event.tool === "run_sandbox" || event.tool === "sandbox_report") && event.ok) {
      const text = previewOf(event);
      try {
        const parsed = JSON.parse(text);
        if (parsed && typeof parsed === "object") {
          return { used_in_run: true, ...parsed };
        }
      } catch {
        return { used_in_run: true, ok: true, summary: event.summary || text };
      }
    }
  }
  return null;
}

/** Filter summary cases by category (`all_errors`, `malicious_approved`, `miss`, `false_positive`, `disagree`, `error`, `all`) and query text. */
export function filterSummaryCases(cases, kindFilter, queryText) {
  const text = String(queryText || "").trim().toLowerCase();
  const errorKinds = new Set(["malicious_approved", "miss", "false_positive", "error"]);
  return (cases || []).filter((item) => {
    const kinds = item.kinds || [];
    if (kindFilter === "all_errors" && !kinds.some((k) => errorKinds.has(k))) return false;
    else if (kindFilter !== "all" && kindFilter !== "all_errors" && !kinds.includes(kindFilter)) return false;
    if (!text) return true;
    return [item.package, item.rule, item.reason, item.error, item.expected, item.label]
      .some((val) => String(val || "").toLowerCase().includes(text));
  });
}

/** Format a 0..1 ratio or numeric metric with Vietnamese comma decimal separator. */
export function fmtMetric(value, digits = 3) {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return Number(value).toFixed(digits).replace(".", ",");
}

export const FEATURED_RUNS = [
  "test-v1-a-llm-x",
  "test-v1-a-slm-x",
  "test-v1-a-llm",
  "test-v1-a-slm",
  "test-v1-a-tlm",
  "dev-v1-a-llm-x",
  "dev-v1-a-slm-x",
  "demo-live-npm",
  "demo-live-tuan07",
];

function isFeaturedRun(name) {
  return FEATURED_RUNS.includes(name) || /^(?:test|dev)-v\d+-|^demo-|^sbx-/i.test(name);
}

/** Prefer real benchmark / live runs when opening the viewer with no #run= hash. */
export function pickDefaultRun(runs) {
  const list = runs || [];
  for (const preferred of FEATURED_RUNS) {
    if (list.includes(preferred)) return preferred;
  }
  const real = list.find((name) => isFeaturedRun(name));
  return real || list[0] || null;
}

/** Partition runs into `{ featured, other }` so the dropdown puts key runs on top. */
export function partitionRuns(runs) {
  const list = [...(runs || [])];
  const rank = new Map(FEATURED_RUNS.map((name, idx) => [name, idx]));
  const featured = [];
  const other = [];
  for (const name of list) {
    if (isFeaturedRun(name)) featured.push(name);
    else other.push(name);
  }
  featured.sort((a, b) => {
    const ra = rank.has(a) ? rank.get(a) : 999;
    const rb = rank.has(b) ? rank.get(b) : 999;
    return ra !== rb ? ra - rb : a.localeCompare(b);
  });
  return { featured, other };
}
