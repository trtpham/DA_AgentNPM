// node --test tests/office_scenarios.test.mjs — truck scenarios cover every outcome, simulations are labelled.
import test from "node:test";
import assert from "node:assert/strict";
import { composeScenario, SCENARIOS, synthesize } from "../viewer/static/office/scenarios.mjs";
import { buildTruck } from "../viewer/static/office/truck.mjs";
import { explainStep } from "../viewer/static/office/explain.mjs";
import { roomFor } from "../viewer/static/office/events.mjs";

const fakeTrace = (pkg, action, rule) => [
  { type: "run_start", ts: "2026-11-05T00:00:00Z", package: pkg },
  { type: "decision", final_action: action, rule, final_label: "x", reasons: ["r"], evidence_checks: [], ts: "2026-11-05T00:00:10Z", package: pkg },
  { type: "run_end", ts: "2026-11-05T00:00:11Z", package: pkg },
];
const ACTIONS = { "canary-fixture@1.0.0": "deny", "benign-install-fixture@1.0.0": "approve" };
const loadTrace = async (run, pkg) => fakeTrace(pkg, ACTIONS[pkg] || "review", "R7_review");

test("every synthetic step is marked and explained as a simulation", () => {
  for (const story of ["green", "cache", "typo", "fetch_error", "limit", "r3", "r5", "r1"]) {
    const events = synthesize(`demo-${story}@1.0.0`, story);
    assert.ok(events.every((event) => event.synthetic), story);
    assert.ok(events.some((event) => event.type === "decision"), story);
    events.forEach((_, index) => assert.match(explainStep(events, index).title, /^\[MÔ PHỎNG\]/));
  }
});

test("rule simulations reach the rule they illustrate", () => {
  const rule = (story) => synthesize("x@1", story).find((event) => event.type === "decision").rule;
  assert.equal(rule("r1"), "R1");
  assert.equal(rule("r3"), "R3");
  assert.equal(rule("r5"), "R5");
  assert.equal(rule("limit"), "R2");
  assert.equal(rule("fetch_error"), "R2");
  assert.ok(synthesize("x@1", "limit").some((event) => event.type === "limit"));
  assert.equal(roomFor(synthesize("x@1", "r1").find((event) => event.type === "sandbox_result")), "lab");
});

test("the scenarios cover delivered, held for review and blocked trucks", async () => {
  const finals = {};
  for (const scenario of SCENARIOS.filter((item) => !item.useRun)) {
    const truck = buildTruck(await composeScenario(scenario, loadTrace));
    finals[scenario.id] = truck.final;
    assert.ok(truck.packages.length > 0, scenario.id);
  }
  assert.equal(finals.safe, "approve");
  assert.equal(finals["malicious-dep"], "deny");
  assert.equal(finals.osv, "deny");
  assert.equal(finals.native, "approve"); // the reviewer lets the swc parcel through
  assert.equal(finals.obfuscated, "deny"); // the reviewer refuses it
  assert.equal(finals["model-fail"], "review");
  assert.equal(finals.sandbox, "deny");
  assert.equal(finals.typosquat, "review");
});

test("real parcels keep their source; a missing run is skipped, not invented", async () => {
  const scenario = SCENARIOS.find((item) => item.id === "malicious-dep");
  const parcels = await composeScenario(scenario, async (run, pkg) => (pkg.startsWith("canary") ? [] : fakeTrace(pkg, "approve", "R7")));
  assert.ok(!parcels.some((parcel) => parcel.package.startsWith("canary")));
  assert.deepEqual([...new Set(parcels.map((parcel) => parcel.source))].sort(), ["design", "real"]);
});
