// node --test tests/office_explain.test.mjs — plain-language input/process/output for each trace event.
import test from "node:test";
import assert from "node:assert/strict";
import { explainStep, previewText, argsText, TOOL_INFO, ERROR_INFO } from "../viewer/static/office/explain.mjs";

const events = [
  { type: "run_start", package: "canary-fixture@1.0.0", model: "qwen3.5:9b", max_steps: 15 },
  { type: "tool_call", tool: "read_file", args: { file: "inspect.js", start: 2, end: 2 } },
  { type: "tool_result", tool: "read_file", ok: true, summary: "OK", data_preview: "const key = read('~/.ssh/id_rsa')" },
  { type: "verdict", valid: true, verdict: { label: "malicious", confidence: 0.95, behaviors: [{}, {}] } },
  { type: "decision", package: "canary-fixture@1.0.0", final_label: "malicious", final_action: "deny", rule: "R6",
    reasons: ["Verified malicious behavior meets deny threshold"], evidence_checks: [{ exists: true }, { exists: false }] },
  { type: "error", kind: "invalid_verdict", message: "unread evidence lines: package.json:1" },
  { type: "something_new" },
];

test("every step has who, input, process and output", () => {
  events.forEach((_, index) => {
    const step = explainStep(events, index);
    for (const field of ["who", "title", "input", "process", "output"]) assert.equal(typeof step[field], "string", `${index}.${field}`);
    assert.ok(["system", "model", "tool", "rules"].includes(step.actor));
  });
});

test("a tool result reuses the input of its matching call and marks package text untrusted", () => {
  const step = explainStep(events, 2);
  assert.equal(step.actor, "tool");
  assert.equal(step.input, "inspect.js dòng 2");
  assert.match(step.process, /KHÔNG chạy mã/);
  assert.equal(step.untrustedOutput, true);
});

test("the decision names the rule, the evidence tally and a dry-run command", () => {
  const step = explainStep(events, 4);
  assert.equal(step.actor, "rules");
  assert.match(step.input, /✔ 1 · ✘ 1/);
  assert.match(step.output, /TỪ CHỐI · npm deny-scripts canary-fixture@1.0.0 \(dry-run\)/);
});

test("known errors are explained, unknown ones still render", () => {
  assert.equal(explainStep(events, 5).process, ERROR_INFO.invalid_verdict);
  assert.equal(explainStep(events, 6).output, "—");
});

test("previews summarise indicators and hooks", () => {
  assert.equal(previewText({ tool: "extract_indicators", data_preview: '[{"type": "url"}, {"type": "eval"}, {"type": "url"}]' }), "chỉ báo: url, eval");
  assert.equal(previewText({ tool: "read_manifest", data_preview: '{"postinstall": "node inspect.js"}' }), "hook postinstall: node inspect.js");
  assert.equal(argsText({ file: "a.js" }), "a.js (từ đầu file)");
  assert.ok(Object.keys(TOOL_INFO).includes("deobfuscate"));
});
