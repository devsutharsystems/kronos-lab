// Node tests for site/js/chips.js (pair label and hue class).
const test = require("node:test");
const assert = require("node:assert/strict");
const C = require("../../site/js/chips.js");

test("every pair has a text label and a hue class", () => {
  assert.deepEqual(Object.values(C.LABELS), ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE"]);
  Object.entries(C.LABELS).forEach(([pair, lab]) => {
    assert.equal(C.label(pair), lab);
    assert.equal(C.hueClass(pair), "pair-" + lab.toLowerCase());
  });
});

test("an unknown pair still gets a text label and no hue class", () => {
  assert.equal(C.label("ADAUSDT"), "ADA");
  assert.equal(C.hueClass("ADAUSDT"), "");
});
