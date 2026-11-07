// Node tests for the pure functions in site/js/plot.js. Fixtures are made-up numbers (SYNTHETIC); they only exercise the geometry.
const test = require("node:test");
const assert = require("node:assert/strict");
const P = require("../../site/js/plot.js");

const site = (acc, ci, naive, diff, dci) => ({ primary: { accuracy: acc, ci_accuracy: ci, naive_binomial_ci95: naive, accuracy_diff: diff, ci_diff: dci } });

test("rowsFromSite reads only primary fields and includes the naive interval when present", () => {
  const rows = P.rowsFromSite(site(0.51, [0.48, 0.54], [0.49, 0.53], 0.04, [-0.02, 0.09]));
  assert.equal(rows.length, 2);
  assert.deepEqual(rows[0].naive, [0.49, 0.53]);
  assert.equal(rows[0].ref, 0.5);
  assert.equal(rows[1].ref, 0);
  assert.equal(rows[1].naive, null);
  assert.equal(P.rowsFromSite(site(0.51, [0.48, 0.54], undefined, 0.04, [-0.02, 0.09]))[0].naive, null);
  assert.equal(P.rowsFromSite({ primary: { accuracy: 0.5 } }), null);
});

test("axis contains the estimate, both intervals and the reference line, with round ticks", () => {
  const row = P.rowsFromSite(site(0.51, [0.48, 0.54], [0.49, 0.53], 0.04, [-0.02, 0.09]))[0];
  const ax = P.axisFor(row, 5);
  [0.51, 0.48, 0.54, 0.49, 0.53, 0.5].forEach((v) => assert.ok(v > ax.lo && v < ax.hi, String(v)));
  assert.ok(ax.ticks.some((t) => Math.abs(t - 0.5) < 1e-9));
  assert.ok(ax.ticks.every((t) => t >= ax.lo - 1e-9 && t <= ax.hi + 1e-9));
});

test("position maps the axis ends to the pixel ends and is monotonic", () => {
  const ax = { lo: 0.4, hi: 0.6 };
  assert.equal(P.position(0.4, ax, 24, 616), 24);
  assert.equal(P.position(0.6, ax, 24, 616), 616);
  assert.ok(P.position(0.5, ax, 24, 616) > 24 && P.position(0.5, ax, 24, 616) < 616);
  assert.ok(P.position(0.45, ax, 0, 100) < P.position(0.55, ax, 0, 100));
});

test("an interval that crosses the reference line is flagged, and one that does not is not", () => {
  const [acc, diff] = P.rowsFromSite(site(0.51, [0.48, 0.54], null, 0.04, [-0.02, 0.09]));
  assert.equal(P.crossesRef(acc), true);                 // interval covers 0.5
  assert.equal(P.crossesRef(diff), true);                // interval covers 0
  const away = P.rowsFromSite(site(0.6, [0.55, 0.65], null, 0.1, [0.05, 0.15]));
  assert.equal(P.crossesRef(away[0]), false);
  assert.equal(P.crossesRef(away[1]), false);
  // the reference line stays inside the axis even when the interval is far from it
  const ax = P.axisFor(away[0], 5);
  assert.ok(0.5 > ax.lo && 0.5 < ax.hi);
});

test("alternative text lists every number and uses no loaded words", () => {
  const rows = P.rowsFromSite(site(0.51, [0.48, 0.54], [0.49, 0.53], 0.04, [-0.02, 0.09]));
  const t = { rowNames: { accuracy: "A", difference: "D" }, estimate: "estimate", interval: "interval", to: "to", reference: "reference", naive: "naive",
    crosses: "includes", excludes: "excludes" };
  const alt = P.altText(rows, (r, v) => String(v), t);
  ["0.51", "0.48", "0.54", "0.49", "0.53", "0.5", "0.04", "-0.02", "0.09"].forEach((n) => assert.ok(alt.includes(n), n));
  assert.ok(!/\b(win|beats?|edge detected)\b/i.test(alt));
});
