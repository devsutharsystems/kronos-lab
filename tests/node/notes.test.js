// Node tests for site/js/notes.js. The fixtures are made-up (SYNTHETIC) numbers that only exercise the conditions.
const test = require("node:test");
const assert = require("node:assert/strict");
const N = require("../../site/js/notes.js");

const site = (p1, p2, d1, d2, up, n, total) => ({ protocol: { alpha: 0.05, origins_total: total },
  primary: { p_h1_holm: p1, p_h2_holm: p2, always_up_accuracy: up, n }, headline: { decision_h1: d1, decision_h2: d2 } });
const NE = "no detectable edge";

test("holm note shows only when a Holm p is below alpha and the decision is no detectable edge", () => {
  assert.equal(N.holmNote(site(0.4, 0.5, NE, NE, 0.5, 1, 2)), null);
  assert.match(N.holmNote(site(0.4, 0.03, NE, NE, 0.5, 1, 2)), /^One test was below 0\.05 on its own \(versus always-up\)\./);
  assert.match(N.holmNote(site(0.01, 0.03, NE, NE, 0.5, 1, 2)), /^Both tests were/);
  assert.equal(N.holmNote(site(0.4, 0.03, NE, "beats always-up", 0.5, 1, 2)), null);   // a declared edge needs no caveat
});

test("always-up note only when always-up accuracy is below one half", () => {
  assert.equal(N.alwaysUpNote(site(1, 1, NE, NE, 0.5, 1, 2)), null);
  assert.equal(N.alwaysUpNote(site(1, 1, NE, NE, 0.51, 1, 2)), null);
  assert.match(N.alwaysUpNote(site(1, 1, NE, NE, 0.49, 1, 2)), /not pre-registered\.$/);
});

test("analysis-set note only when fewer origins were scored than planned", () => {
  assert.equal(N.analysisSetNote(site(1, 1, NE, NE, 0.5, 5, 5)), null);
  assert.match(N.analysisSetNote(site(1, 1, NE, NE, 0.5, 4, 5)), /^Analysis set: 4 origins scored, out of 5 planned\./);
});
