// "Truck" mode logic, pure (no DOM, no Three.js) so `node --test` covers it.
// One install request = one truck carrying every package of a run. Packages are analysed one after
// another on the real clock of their traces; the whole truck gets the strictest verdict
// (deny > review > approve): one malicious parcel holds the whole delivery.

export const INTRO = 7;  // trace seconds: the request reaches the registry and the truck drives to the gate
export const GAP = 2;    // between two parcels
export const OUTRO = 7;  // the truck leaves for the user's machine, or stays held at the gate
const SEVERITY = { approve: 1, review: 2, deny: 3 };

/** Strictest action wins; a parcel without a decision (run error) counts as review. */
export function finalAction(actions) {
  if (!actions.length) return null;
  return actions.map((action) => action || "review").reduce((worst, action) => (SEVERITY[action] > SEVERITY[worst] ? action : worst));
}

// read_manifest previews list the lifecycle hooks; none means npm would run no install script.
export function hasInstallHooks(events) {
  const result = events.find((event) => event.type === "tool_result" && event.tool === "read_manifest" && event.ok);
  if (!result || !result.data_preview) return null;
  return /"(preinstall|install|postinstall)":\s*"/.test(String(result.data_preview));
}

/**
 * Lay the traces of a run end to end after the truck's arrival.
 * @param {{package: string, events: object[], source?: string, osv?: boolean, installedBefore?: boolean}[]} traces
 *   in truck order; `osv` = the gate found the package on a blocklist (blocked first, analysed after);
 *   a `human_review` event after the decision is a reviewer's final call on a review case.
 */
export function buildTruck(traces) {
  const events = [];
  const offsets = [];
  const packages = [];
  let cursor = INTRO;
  traces.forEach(({ package: name, events: trace, source = "real", osv = false, installedBefore = false }, index) => {
    const times = trace.map((event) => Date.parse(event.ts));
    const first = Number.isFinite(times[0]) ? times[0] : 0;
    const local = times.map((time, at) => (Number.isFinite(time) ? (time - first) / 1000 : at));
    const start = cursor;
    const firstIndex = events.length;
    trace.forEach((event, at) => {
      events.push({ ...event, _pkg: index });
      offsets.push(start + local[at]);
    });
    const decisionAt = trace.findIndex((event) => event.type === "decision");
    const decision = decisionAt >= 0 ? trace[decisionAt] : null;
    const verdicts = trace.filter((event) => event.type === "verdict");
    const verdict = (verdicts.slice().reverse().find((event) => event.valid) || verdicts.at(-1))?.verdict || null;
    const end = start + (local.at(-1) ?? 0);
    const agentAt = decision ? start + local[decisionAt] : end;
    const agentAction = decision?.final_action || "review";
    const humanAt = trace.findIndex((event) => event.type === "human_review");
    const human = humanAt >= 0 ? trace[humanAt] : null;
    packages.push({ name, index, start, end, firstIndex, lastIndex: events.length - 1, source, osv, installedBefore,
                    decision, verdict, agentAt, agentAction, human, hooks: hasInstallHooks(trace),
                    // the reviewer's call replaces a review verdict; otherwise the agent's action stands
                    decidedAt: human && agentAction === "review" ? start + local[humanAt] : agentAt,
                    action: human && agentAction === "review" ? human.final_action : agentAction });
    cursor = end + GAP;
  });
  const lastEnd = packages.length ? packages.at(-1).end : INTRO;
  const duration = lastEnd + OUTRO;
  return { events, offsets, packages, duration, outroAt: lastEnd + 0.5, final: finalAction(packages.map((item) => item.action)) };
}

/** Where a parcel is at clock time t: truck, stack, reception, approved, review, quarantine or loaded. */
export function parcelZone(pkg, t, truck) {
  if (t < INTRO * 0.8) return "truck";
  if (t < pkg.start) return "stack";
  // Blocked first, analysed after: a blocklisted parcel is quarantined as soon as its turn comes.
  if (pkg.osv) return "quarantine";
  if (t < pkg.agentAt) return "reception";
  if (t < pkg.decidedAt) return "review"; // waiting on the shelf for the human reviewer
  if (t >= truck.outroAt && truck.final === "approve") return "loaded";
  return pkg.action === "approve" ? "approved" : pkg.action === "deny" ? "quarantine" : "review";
}

/** Truck position along its trips: 0..1 from the registry to the gate, then 0..1 from the gate to the user. */
export function truckPhase(t, truck) {
  const depart = 1.6;
  if (t < depart) return { where: "registry", progress: 0 };
  if (t < INTRO * 0.75) return { where: "toGate", progress: (t - depart) / (INTRO * 0.75 - depart) };
  if (t >= truck.outroAt + 1 && truck.final === "approve") {
    const progress = Math.min(1, (t - truck.outroAt - 1) / (OUTRO - 2));
    return { where: progress >= 1 ? "house" : "toHouse", progress };
  }
  return { where: "gate", progress: 1 };
}

/** Counts by outcome among the parcels decided by time t. */
export function tally(truck, t) {
  const counts = { approve: 0, review: 0, deny: 0, pending: 0 };
  for (const pkg of truck.packages) counts[t >= pkg.decidedAt ? pkg.action : "pending"] += 1;
  return counts;
}

/** The parcel being worked on at time t, or null between parcels. */
export function currentParcel(truck, t) {
  return truck.packages.find((pkg) => t >= pkg.start && t < pkg.end + GAP) || null;
}
