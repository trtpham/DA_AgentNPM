import { test } from "node:test";
import assert from "node:assert/strict";
import { RULE_LADDER, ruleFamily, ruleLadder, ruleSentence } from "../../viewer/static/office/rules.mjs";

test("ladder follows the order of agent/decide.py", () => {
  assert.deepEqual(RULE_LADDER.map((rule) => rule.code), ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"]);
});

test("rules above the fired one are skipped, below are unchecked", () => {
  const states = ruleLadder("R3").map((rule) => rule.state);
  assert.deepEqual(states, ["skipped", "skipped", "fired", "unchecked", "unchecked", "unchecked", "unchecked", "unchecked"]);
});

test("R7 variants fire on R7 and say why the package was held", () => {
  assert.equal(ruleFamily("R7_flow"), "R7");
  const fired = ruleLadder("R7_flow").find((rule) => rule.state === "fired");
  assert.equal(fired.code, "R7");
  assert.match(fired.variant, /mạng/);
  assert.match(ruleSentence("R7_review"), /người xem/);
});

test("unknown or missing rule leaves the whole ladder unchecked", () => {
  assert.ok(ruleLadder(undefined).every((rule) => rule.state === "unchecked"));
  assert.equal(ruleFamily("R9"), "");
  assert.match(ruleSentence(null), /không ghi luật/);
});
