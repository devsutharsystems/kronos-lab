// Game logic as pure functions (no DOM, no globals). Works in the browser (window.KLGame) and in node (module.exports).
// Context is normalised so the last close is the reference level; the truth is whether the final actual close is above it.
(function (root) {
  "use strict";

  // +1 if the final actual close is above the reference level, -1 if below, 0 if equal.
  function trueDirection(actual, reference) {
    const last = actual[actual.length - 1];
    return last > reference ? 1 : last < reference ? -1 : 0;
  }

  function reference(win) {
    const c = win.context;
    return c[c.length - 1][3];                 // last context close
  }

  function initialState() {
    return { index: 0, revealed: false, you: 0, kronos: 0, coin: 0, answered: 0, history: [] };
  }

  // Record the player's call for the current window; returns a NEW state (the input is not mutated).
  function answer(state, win, youCall) {
    if (state.revealed) return state;
    const truth = trueDirection(win.actual, reference(win));
    const hit = (call) => (call === truth ? 1 : 0);
    const rec = { you: youCall, kronos: win.kronos_call, coin: win.coin_flip, truth: truth,
                  youHit: hit(youCall), kronosHit: hit(win.kronos_call), coinHit: hit(win.coin_flip) };
    return Object.assign({}, state, {
      revealed: true,
      you: state.you + rec.youHit, kronos: state.kronos + rec.kronosHit, coin: state.coin + rec.coinHit,
      answered: state.answered + 1, history: state.history.concat([rec]),
    });
  }

  function next(state) {
    return state.revealed ? Object.assign({}, state, { index: state.index + 1, revealed: false }) : state;
  }

  function isFinished(state, total) {
    return state.index >= total;
  }

  function tallies(state) {
    return { you: state.you, kronos: state.kronos, coin: state.coin, answered: state.answered };
  }

  // Price range for drawing: context OHLC plus (optionally) the actual closes.
  function priceRange(win, includeActual) {
    let lo = Infinity, hi = -Infinity;
    win.context.forEach((b) => { lo = Math.min(lo, b[2]); hi = Math.max(hi, b[1]); });
    if (includeActual) win.actual.forEach((v) => { lo = Math.min(lo, v); hi = Math.max(hi, v); });
    return [lo, hi];
  }

  const api = { trueDirection, reference, initialState, answer, next, isFinished, tallies, priceRange };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.KLGame = api;
})(typeof window !== "undefined" ? window : globalThis);
