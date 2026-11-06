// Node tests for the pure axis helpers in site/js/svg.js. SYNTHETIC numbers only.
const test = require("node:test");
const assert = require("node:assert/strict");
const S = require("../../site/js/svg.js");

test("niceScale gives round ticks inside the range", () => {
  const a = S.niceScale(-3.7, 8.2, 5);
  assert.deepEqual(a.ticks, [-2, 0, 2, 4, 6, 8]);
  assert.equal(a.decimals, 0);
  const b = S.niceScale(0.47, 0.58, 5);
  assert.deepEqual(b.ticks, [0.48, 0.5, 0.52, 0.54, 0.56, 0.58]);
  assert.equal(b.decimals, 2);
  assert.ok(S.niceScale(-1, 1, 5).ticks.every((t) => t >= -1 && t <= 1));
});

test("zero is exactly a tick and never negative zero", () => {
  const t = S.niceScale(-1.3, 2.9, 5).ticks;
  assert.ok(t.some((v) => v === 0 && !Object.is(v, -0)));
  assert.ok(S.withTick(S.niceScale(0.41, 0.58, 5).ticks, 0.5).some((v) => Math.abs(v - 0.5) < 1e-9));
});

test("withTick adds a missing reference tick, sorted, without duplicating", () => {
  assert.deepEqual(S.withTick([0.2, 0.6], 0.5), [0.2, 0.5, 0.6]);
  assert.deepEqual(S.withTick([0.2, 0.5], 0.5), [0.2, 0.5]);
});

test("dataRange contains every value, the extras, and has padding", () => {
  const [lo, hi] = S.dataRange([[0.52, 0.49, 0.61], [0.4, 0.7]], [0.5], 0.06);
  assert.ok(lo < 0.4 && hi > 0.7);
  const [l2, h2] = S.dataRange([[3, 3]], [], 0.1);          // constant data still gets a non-empty range
  assert.ok(l2 < 3 && h2 > 3);
});
