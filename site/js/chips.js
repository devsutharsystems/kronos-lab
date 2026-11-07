// Pair identity: a short text label and a hue class per trading pair. Pure functions (tested with node).
(function (root) {
  "use strict";
  const LABELS = { BTCUSDT: "BTC", ETHUSDT: "ETH", SOLUSDT: "SOL", XRPUSDT: "XRP", BNBUSDT: "BNB", DOGEUSDT: "DOGE" };
  const label = (pair) => LABELS[pair] || String(pair).replace(/USDT$/, "");
  const hueClass = (pair) => (LABELS[pair] ? "pair-" + LABELS[pair].toLowerCase() : "");
  const api = { LABELS, label, hueClass };
  root.KLChips = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
