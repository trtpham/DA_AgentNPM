// Package text in traces: plain `data_preview` (older traces) and base64 `data_preview_b64` (from 20/11/2026).
import { test } from "node:test";
import assert from "node:assert/strict";
import { explainStep, previewOf, previewText } from "../../viewer/static/office/explain.mjs";
import { hasInstallHooks } from "../../viewer/static/office/truck.mjs";

const b64 = (text) => Buffer.from(text, "utf-8").toString("base64");
const SOURCE = "// Mẫu: <img src=x onerror=alert(1)>\nconst key = read('~/.ssh/id_rsa')";

test("old traces: plain data_preview is shown as it is", () => {
  assert.equal(previewOf({ data_preview: SOURCE }), SOURCE);
  assert.equal(previewOf({}), "");
  assert.equal(previewOf(null), "");
});

test("new traces: data_preview_b64 is decoded as UTF-8, markup stays plain text", () => {
  const event = { tool: "read_file", data_preview_b64: b64(SOURCE), data_preview_encoding: "base64" };
  assert.equal(previewOf(event), SOURCE);
  assert.match(previewText(event), /<img src=x onerror=alert\(1\)>/);
});

test("base64 wins when a trace carries both fields", () => {
  assert.equal(previewOf({ data_preview: "old", data_preview_b64: b64("new"), data_preview_encoding: "base64" }), "new");
});

test("a broken or unknown encoding is reported, never thrown", () => {
  assert.equal(previewOf({ data_preview_b64: "%%%not base64%%%", data_preview_encoding: "base64" }), "[không giải mã được dữ liệu base64]");
  assert.match(previewOf({ data_preview_b64: "abc", data_preview_encoding: "rot13" }), /chưa hỗ trợ/);
});

test("the step text and the truck hook check read both formats", () => {
  const manifest = '{"scripts": {"postinstall": "node setup.js"}}';
  const call = { type: "tool_call", tool: "read_file", args: { file: "setup.js", start: 1, end: 2 } };
  const plain = { type: "tool_result", tool: "read_file", ok: true, summary: "OK", data_preview: SOURCE, untrusted: true };
  const encoded = { ...plain, data_preview: undefined, data_preview_b64: b64(SOURCE), data_preview_encoding: "base64" };
  assert.equal(explainStep([call, encoded], 1).output, explainStep([call, plain], 1).output);
  assert.equal(explainStep([call, encoded], 1).untrustedOutput, true);
  for (const field of [{ data_preview: manifest }, { data_preview_b64: b64(manifest), data_preview_encoding: "base64" }]) {
    assert.equal(hasInstallHooks([{ type: "tool_result", tool: "read_manifest", ok: true, ...field }]), true);
  }
});
