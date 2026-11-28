import test from "node:test";
import assert from "node:assert/strict";
import {
  behaviorTriplet,
  extractSnippet,
  filterSummaryCases,
  fmtMetric,
  parseLineRange,
  partitionRuns,
  pickDefaultRun,
  sandboxFromEvents,
} from "../../viewer/static/summary.mjs";

test("parseLineRange parses single and range line specs", () => {
  assert.deepEqual(parseLineRange("12"), { start: 12, end: 12 });
  assert.deepEqual(parseLineRange("10-15"), { start: 10, end: 15 });
  assert.equal(parseLineRange("abc"), null);
  assert.equal(parseLineRange("0"), null);
});

test("behaviorTriplet extracts concrete source, action, and target", () => {
  const t = behaviorTriplet({
    behavior: "Exfiltrate npm token",
    technique: "network-request",
    evidence: { file: "setup.js", lines: "4" },
    analysis: "Reads ~/.npmrc and posts to https://evil.invalid/collect",
    impact: "Leaks token",
  });
  assert.equal(t.source, "~/.npmrc");
  assert.match(t.action, /network-request/);
  assert.equal(t.target, "https://evil.invalid/collect");
});

test("extractSnippet highlights cited lines from read_file tool_result", () => {
  const events = [
    { type: "tool_call", tool: "read_file", args: { file: "install.js", start: 10, end: 13 } },
    {
      type: "tool_result",
      tool: "read_file",
      ok: true,
      data_preview: "line 10\nfetch('https://x.invalid')\nline 12\nline 13",
    },
  ];
  const snippet = extractSnippet(events, "install.js", "11");
  assert.ok(snippet);
  assert.equal(snippet.covers, true);
  assert.deepEqual(
    snippet.lines.filter((l) => l.cited).map((l) => l.num),
    [11],
  );
  assert.equal(extractSnippet(events, "missing.js", "1"), null);
});

test("sandboxFromEvents decodes run_sandbox tool_result JSON", () => {
  const events = [
    {
      type: "tool_result",
      tool: "run_sandbox",
      ok: true,
      data_preview: JSON.stringify({ outcome: "ok", canary_touched: ["ssh"], connects: [] }),
    },
  ];
  const sbx = sandboxFromEvents(events);
  assert.equal(sbx.used_in_run, true);
  assert.deepEqual(sbx.canary_touched, ["ssh"]);
});

test("filterSummaryCases filters by error category and text query", () => {
  const cases = [
    { package: "evil@1.0.0", kinds: ["malicious_approved"], rule: "R7", label: "benign", expected: "malicious" },
    { package: "good@1.0.0", kinds: ["false_positive", "disagree"], rule: "R7_risk", label: "benign", expected: "benign" },
    { package: "clean@1.0.0", kinds: [], rule: "R7", label: "benign", expected: "benign" },
  ];
  assert.equal(filterSummaryCases(cases, "all_errors", "").length, 2);
  assert.equal(filterSummaryCases(cases, "disagree", "").length, 1);
  assert.equal(filterSummaryCases(cases, "all", "evil").length, 1);
  assert.equal(fmtMetric(0.8302), "0,830");
  assert.equal(fmtMetric(null), "—");
});

test("pickDefaultRun prefers real benchmark runs over alphabetical ablation runs", () => {
  const runs = ["abl-no-alias-a-slm", "demo-live-npm", "test-v1-a-slm-x", "test-v1-a-llm-x", "smoke1"];
  assert.equal(pickDefaultRun(runs), "test-v1-a-llm-x");
  assert.equal(pickDefaultRun(["abl-1", "smoke-2"]), "abl-1");
  const groups = partitionRuns(runs);
  assert.deepEqual(groups.featured, ["test-v1-a-llm-x", "test-v1-a-slm-x", "demo-live-npm"]);
  assert.deepEqual(groups.other, ["abl-no-alias-a-slm", "smoke1"]);
});
