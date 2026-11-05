// node --test tests/js/office_truck.test.mjs — "truck" mode: one install request, many parcels.
import test from "node:test";
import assert from "node:assert/strict";
import { buildTruck, currentParcel, finalAction, GAP, hasInstallHooks, INTRO, parcelZone, tally, truckPhase } from "../../viewer/static/office/truck.mjs";

const at = (seconds) => new Date(Date.UTC(2026, 10, 5, 0, 0, seconds)).toISOString();
const trace = (name, action, length = 10) => ({
  package: name,
  events: [
    { type: "run_start", ts: at(0) },
    { type: "tool_result", tool: "read_manifest", ok: true, ts: at(1),
      data_preview: action === "approve" ? '{"scripts": {"untrusted": true, "content": {}}}' : '{"scripts": {"content": {"postinstall": "node x.js"}}}' },
    { type: "verdict", valid: true, verdict: { label: "x" }, ts: at(length - 2) },
    { type: "decision", final_action: action, rule: "R7", ts: at(length - 1) },
    { type: "run_end", ts: at(length) },
  ],
});

test("strictest action wins and a missing decision counts as review", () => {
  assert.equal(finalAction(["approve", "approve"]), "approve");
  assert.equal(finalAction(["approve", "review"]), "review");
  assert.equal(finalAction(["review", "deny", "approve"]), "deny");
  assert.equal(finalAction(["approve", null]), "review");
  assert.equal(finalAction([]), null);
});

test("traces are laid end to end after the truck's arrival", () => {
  const truck = buildTruck([trace("a@1.0.0", "approve"), trace("b@1.0.0", "deny", 20)]);
  const [a, b] = truck.packages;
  assert.equal(a.start, INTRO);
  assert.equal(b.start, a.end + GAP);
  assert.equal(truck.events.length, 10);
  assert.deepEqual(truck.events.map((event) => event._pkg), [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]);
  assert.equal(truck.offsets[5], b.start);
  assert.equal(truck.final, "deny");
  assert.equal(b.decidedAt, b.start + 19);
});

test("hooks are read from the manifest preview", () => {
  assert.equal(hasInstallHooks(trace("a@1", "approve").events), false);
  assert.equal(hasInstallHooks(trace("b@1", "deny").events), true);
  assert.equal(hasInstallHooks([{ type: "run_start" }]), null);
});

test("parcels move truck -> stack -> reception -> outcome zone", () => {
  const truck = buildTruck([trace("a@1.0.0", "approve"), trace("b@1.0.0", "review"), trace("c@1.0.0", "deny")]);
  const [a, b, c] = truck.packages;
  assert.equal(parcelZone(a, 1, truck), "truck");
  assert.equal(parcelZone(b, INTRO, truck), "stack");
  assert.equal(parcelZone(a, a.start + 1, truck), "reception");
  assert.equal(parcelZone(a, a.decidedAt, truck), "approved");
  assert.equal(parcelZone(b, b.decidedAt + 0.1, truck), "review");
  assert.equal(parcelZone(c, truck.duration, truck), "quarantine");
  // A held truck never loads its approved parcels.
  assert.equal(parcelZone(a, truck.duration, truck), "approved");
  assert.deepEqual(tally(truck, truck.duration), { approve: 1, review: 1, deny: 1, pending: 0 });
  assert.equal(currentParcel(truck, b.start + 1).name, "b@1.0.0");
});

test("only an all-approved truck leaves for the user's machine", () => {
  const good = buildTruck([trace("a@1.0.0", "approve")]);
  assert.equal(truckPhase(0, good).where, "registry");
  assert.equal(truckPhase(3, good).where, "toGate");
  assert.equal(truckPhase(good.duration, good).where, "house");
  assert.equal(parcelZone(good.packages[0], good.duration, good), "loaded");
  const held = buildTruck([trace("a@1.0.0", "approve"), trace("b@1.0.0", "deny")]);
  assert.equal(truckPhase(held.duration, held).where, "gate");
});

test("a reviewer's call replaces a review verdict, and the parcel waits on the shelf until then", () => {
  const base = trace("swc@1.0.0", "review");
  const humanEvent = { type: "human_review", final_action: "approve", ts: at(16) };
  const truck = buildTruck([{ ...base, events: [...base.events, humanEvent] }]);
  const [pkg] = truck.packages;
  assert.equal(pkg.agentAction, "review");
  assert.equal(pkg.action, "approve");
  assert.equal(parcelZone(pkg, pkg.agentAt + 0.5, truck), "review");
  assert.equal(parcelZone(pkg, pkg.decidedAt, truck), "approved"); // on the pallet first
  assert.equal(parcelZone(pkg, truck.duration, truck), "loaded"); // all approved: the truck takes it
  assert.equal(truck.final, "approve");
});

test("a reviewer cannot overturn a deny, and a blocklisted parcel is quarantined at once", () => {
  const base = trace("bad@1.0.0", "deny");
  const humanEvent = { type: "human_review", final_action: "approve", ts: at(16) };
  const truck = buildTruck([{ ...base, events: [...base.events, humanEvent] }, { ...trace("osv@1.0.0", "review"), osv: true }]);
  assert.equal(truck.packages[0].action, "deny");
  const blocked = truck.packages[1];
  assert.equal(parcelZone(blocked, blocked.start, truck), "quarantine");
  assert.equal(truck.final, "deny");
});
