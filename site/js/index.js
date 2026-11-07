// Index page: verdict cards, interval plot, stat cards, notes and power table. Everything comes from site.json; strings live in text.js.
(async function () {
  "use strict";
  const site = await KL.loadSite();
  if (!site) return;
  const { el, fmt, table } = KL;
  const T = KL.text;

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
    if (noEdge1 && ub1 != null) parts.push(T.overCoin + ": " + fmt.pp(ub1));
    if (noEdge2 && ub2 != null) parts.push(T.overAlwaysUp + ": " + fmt.pp(ub2));
    notRuledOut.textContent = T.largestEdge + ", " + parts.join("; ") + ".";
    notRuledOut.hidden = false;
  }

  // Notes derived from site.json (see notes.js); each is shown only when its condition holds in the data.
  const show = (id, text) => { const n = document.getElementById(id); if (text) { n.textContent = text; n.hidden = false; } return n; };
  show("note-holm", KLNotes.holmNote(site));
  show("note-alwaysup", KLNotes.alwaysUpNote(site));
  const setText = KLNotes.analysisSetNote(site);
  if (setText) {
    const n = show("analysis-set", setText);
    n.appendChild(el("a", { href: "method.html#recorded-deviations", text: "Recorded deviations on the Method page" }));
    n.appendChild(document.createTextNode("."));
  }

  // Verdict cards (neutral styling; the decision text is shown exactly as it is in site.json)
  const level = site.protocol.ci_level;
  const row = (k, v) => el("div", { class: "kv" }, [el("span", { class: "k", text: k }), el("span", { class: "v", text: v })]);
  const verdict = (key, title, est, estText, ci, ciFmt, praw, pholm, decision) => el("section", { class: "card verdict", "aria-label": title }, [
    el("h3", { text: title }), el("p", { class: "decision", text: decision }),
    row(est, estText), row(T.intervalName(level), ci.map(ciFmt).join(" to ")), row(T.rawP, fmt.p(praw)), row(T.holmP, fmt.p(pholm))]);
  document.getElementById("verdicts").replaceChildren(
    verdict("h1", T.verdict.h1, T.est.h1, fmt.pct(p.accuracy), p.ci_accuracy, (v) => fmt.pct(v), p.p_h1_raw, p.p_h1_holm, site.headline.decision_h1),
    verdict("h2", T.verdict.h2, T.est.h2, fmt.pp(p.accuracy_diff), p.ci_diff, (v) => fmt.pp(v), p.p_h2_raw, p.p_h2_holm, site.headline.decision_h2));

  // Interval plot
  const f = (r, v, dec) => (r.id === "accuracy" ? fmt.pct(v, dec == null ? 2 : Math.max(0, dec - 2)) : fmt.pp(v, dec == null ? 2 : Math.max(0, dec - 2)));
  const plot = KLPlot.draw(site, T.plot, f);
  document.getElementById("plot-title").textContent = T.plotTitle;
  if (plot) {
    document.getElementById("interval-plot").replaceChildren(plot.svg);
    document.getElementById("interval-alt").textContent = plot.alt;
    document.getElementById("plot-note").textContent = T.plotNote;
  }

  // Stat cards
  const pa = site.power_at_actual_n.rows[0];
  const stat = (label, value) => el("div", { class: "card stat" }, [el("span", { class: "statval", text: value }), el("span", { class: "statlabel", text: label })]);
  document.getElementById("statcards").replaceChildren(
    stat(T.scored + " " + T.of + " " + T.planned, fmt.int(p.n) + " " + T.of + " " + fmt.int(site.protocol.origins_total)),
    stat(T.downCalls, fmt.int(site.headline.D)),
    stat(T.powerScored, fmt.ppRaw(pa.min_detectable_edge_pp, 3)),
    stat(T.powerPlanned, fmt.ppRaw(site.power.rows[site.power.rows.length - 1].min_detectable_edge_pp, 3)));

  // Power table from site.json
  const rows = site.power.rows.map((r) => ({ cells: [fmt.int(r.n), fmt.ppRaw(r.min_detectable_edge_pp, 3), fmt.pct(r.accuracy_needed, 2)] }));
  document.getElementById("power-table").replaceChildren(
    table(T.powerCols, rows, [0, 1, 2]));
  document.getElementById("power-down").textContent = site.power.D
    ? T.downText(fmt.int(site.power.D), fmt.ppRaw(site.power.min_detectable_shift_down_calls_pp, 3)) : T.noDownCalls;
})();
