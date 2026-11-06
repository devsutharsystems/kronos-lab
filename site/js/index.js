// Index page: headline, primary statistics and power table, all from site.json.
(async function () {
  "use strict";
  const site = await KL.loadSite();
  if (!site) return;
  const { el, fmt, table } = KL;

  document.getElementById("headline-text").textContent = site.headline.headline;
  document.getElementById("underpowered").hidden = !site.headline.underpowered;

  const p = site.primary;
  const ub1 = site.headline.largest_edge_not_ruled_out_h1;
  const ub2 = site.headline.largest_gain_vs_always_up_not_ruled_out_h2;
  const notRuledOut = document.getElementById("not-ruled-out");
  const noEdge1 = site.headline.decision_h1 === "no detectable edge";
  const noEdge2 = site.headline.decision_h2 === "no detectable edge";
  if (noEdge1 || noEdge2) {
    const parts = [];
    if (noEdge1 && ub1 != null) parts.push("over a coin flip: " + fmt.pp(ub1));
    if (noEdge2 && ub2 != null) parts.push("over always-up: " + fmt.pp(ub2));
    notRuledOut.textContent = "Largest edge not ruled out (upper end of the interval), " + parts.join("; ") + ".";
    notRuledOut.hidden = false;
  }

  // Power table from site.json
  const rows = site.power.rows.map((r) => ({ cells: [fmt.int(r.n), fmt.ppRaw(r.min_detectable_edge_pp, 3), fmt.pct(r.accuracy_needed, 2)] }));
  document.getElementById("power-table").replaceChildren(
    table(["Analysis set N", "Smallest detectable edge", "Accuracy needed"], rows, [0, 1, 2]));
  document.getElementById("power-down").textContent =
    site.power.D ? "Kronos made " + fmt.int(site.power.D) + " down-calls. The smallest detectable shift in the share of correct down-calls is about " +
      fmt.ppRaw(site.power.min_detectable_shift_down_calls_pp, 3) + "." : "Kronos made no down-calls, so the comparison with always-up carries no information.";
})();
