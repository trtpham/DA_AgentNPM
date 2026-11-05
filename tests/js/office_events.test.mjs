// node --test tests/js/office_events.test.mjs — pure mapping of trace events to office rooms.
import test from "node:test";
import assert from "node:assert/strict";
import { ROOMS, roomFor } from "../../viewer/static/office/events.mjs";

test("every room has a Vietnamese name and step", () => {
  for (const room of Object.values(ROOMS)) assert.ok(room.name && room.step);
  assert.equal(ROOMS.lab.locked, true); // sandbox room stays locked until W5-6
});

test("mapping always returns a known room, even for unknown events", () => {
  const samples = [
    { type: "run_start" }, { type: "tool_call", tool: "read_manifest" }, { type: "tool_call", tool: "read_file" },
    { type: "tool_result", tool: "deobfuscate" }, { type: "verdict" }, { type: "decision" }, { type: "run_end" },
    { type: "error", kind: "invalid_verdict" }, { type: "limit" }, { type: "something_new" }, {},
  ];
  for (const event of samples) assert.ok(roomFor(event) in ROOMS, JSON.stringify(event));
});

test("the four agent steps land in their rooms", () => {
  assert.equal(roomFor({ type: "run_start" }), "reception");
  assert.equal(roomFor({ type: "tool_call", tool: "extract_indicators" }), "code");
  assert.equal(roomFor({ type: "decision" }), "decision");
});
