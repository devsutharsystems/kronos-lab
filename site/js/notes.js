// Plain notes derived from site.json fields only (no typed figures). Pure functions, tested with node.
(function (root) {
  "use strict";
  const HALF = 0.5;                       // chance level for a two-way call
  const NO_EDGE = "no detectable edge";

  function holmNote(site) {
    const a = site.protocol.alpha, p = site.primary, h = site.headline, hits = [];
    if (p.p_h1_holm < a && h.decision_h1 === NO_EDGE) hits.push("versus a coin flip");
    if (p.p_h2_holm < a && h.decision_h2 === NO_EDGE) hits.push("versus always-up");
    if (!hits.length) return null;
    return (hits.length === 1 ? "One test was" : "Both tests were") + " below " + a + " on its own (" + hits.join(", ") + "). " +
      "The pre-registered rule also requires the day-block interval to exclude the null, and it did not, so no edge is declared. Both numbers are shown.";
  }

  function alwaysUpNote(site) {
    if (!(site.primary.always_up_accuracy < HALF)) return null;
    return "Always-up accuracy is the share of days that closed up. When it is below one half, this window had more down days than up days, " +
      "so always-up is a weak baseline here. This note is descriptive and was not pre-registered.";
  }

  function analysisSetNote(site) {
    const n = site.primary.n, total = site.protocol.origins_total;
    if (!(n < total)) return null;
    return "Analysis set: " + n + " origins scored, out of " + total + " planned. The run was closed at the cutoff before it finished; see ";
  }

  const api = { holmNote, alwaysUpNote, analysisSetNote };
  root.KLNotes = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
