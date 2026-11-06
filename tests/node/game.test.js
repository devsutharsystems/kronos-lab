// Node tests for the pure game logic in site/js/game.js (run: node --test tests/node). SYNTHETIC windows only.
const test = require("node:test");
const assert = require("node:assert/strict");
const G = require("../../site/js/game.js");

// A window whose context ends at the reference level 100 and whose final actual close is `actualEnd`.
function win(actualEnd, kronos, coin) {
  const bar = [100, 101, 99, 100];
  return { context: [bar, bar, bar], kronos_call: kronos, coin_flip: coin, actual: [100.5, actualEnd], reveal: { pair: "X", date: "D" } };
}

test("trueDirection compares the final actual close with the reference", () => {
  assert.equal(G.trueDirection([99, 101], 100), 1);
  assert.equal(G.trueDirection([101, 99], 100), -1);
  assert.equal(G.trueDirection([101, 100], 100), 0);
  assert.equal(G.reference(win(101, 1, 1)), 100);
});

test("answer is pure and scores You, Kronos and the coin flip separately", () => {
  const s0 = G.initialState();
  const frozen = JSON.stringify(s0);
  const w = win(103, 1, -1);                       // truth is up
  const s1 = G.answer(s0, w, 1);                   // you say up (right), Kronos up (right), coin down (wrong)
  assert.equal(JSON.stringify(s0), frozen);        // input state not mutated
  assert.deepEqual(G.tallies(s1), { you: 1, kronos: 1, coin: 0, answered: 1 });
  assert.equal(s1.revealed, true);
  assert.equal(s1.history[0].truth, 1);
});

test("a second answer in the same window is ignored", () => {
  const w = win(103, 1, 1);
  const s1 = G.answer(G.initialState(), w, -1);
  const s2 = G.answer(s1, w, 1);
  assert.equal(s2, s1);
  assert.deepEqual(G.tallies(s2), { you: 0, kronos: 1, coin: 1, answered: 1 });
});

test("next only advances after an answer", () => {
  const s0 = G.initialState();
  assert.equal(G.next(s0), s0);
  const s1 = G.next(G.answer(s0, win(97, -1, -1), -1));
  assert.equal(s1.index, 1);
  assert.equal(s1.revealed, false);
});

test("full playthrough tallies and finishing", () => {
  const wins = [win(103, 1, 1), win(97, 1, -1), win(103, -1, -1)];   // truths: up, down, up
  let s = G.initialState();
  const calls = [1, -1, -1];                                          // you: right, right, wrong
  wins.forEach((w, i) => { s = G.next(G.answer(s, w, calls[i])); });
  assert.deepEqual(G.tallies(s), { you: 2, kronos: 1, coin: 2, answered: 3 });   // coin: right, right, wrong
  assert.equal(G.isFinished(s, wins.length), true);
  assert.equal(G.isFinished(G.initialState(), wins.length), false);
});

test("priceRange covers the context and, when asked, the actual path", () => {
  const w = win(130, 1, 1);
  assert.deepEqual(G.priceRange(w, false), [99, 101]);
  assert.deepEqual(G.priceRange(w, true), [99, 130]);
});
