// Evidence page: fan chart, running score vs coin-flip band (synthetic builds only), results tables. All numbers come from site.json.
// Every part is built independently: if one fails, the others still render and the failure is shown on the page.
(async function () {
  "use strict";
  const site = await KL.loadSite();
  if (!site) return;
  const { el, fmt, table } = KL;
  const S = KLSVG, T = KL.text, E = T.evidence, F = T.fan;
  const part = (name, fn) => {
    try { fn(); } catch (e) {
      const m = document.getElementById("load-error");
      m.textContent = (m.textContent ? m.textContent + " " : "") + T.scriptError(name, e && e.message ? e.message : String(e));
      m.hidden = false;
      if (typeof console !== "undefined") console.error(e);
    }
  };

  // ---------------- results tables first: they must never depend on the charts (copied from results.json; all but the primary row exploratory)
  part("tables", () => {
    const badge = (primary) => el("span", { class: primary ? "badge primary" : "badge", text: primary ? T.badgePrimary : T.badgeExploratory });
    const rt = site.results_table;
    const allRows = rt.all_pairs.map((r) => ({ cls: r.primary ? "primary-row" : "", cells: [E.horizonPrefix + r.horizon, fmt.int(r.n), fmt.pct(r.kronos_accuracy),
      fmt.pct(r.persistence_accuracy), badge(r.primary)] }));
    const pairRows = rt.by_pair_h24.map((r) => ({ cells: [KL.chip(r.pair), fmt.int(r.n), fmt.pct(r.kronos_accuracy), badge(false)] }));
    const intro = [el("p", { class: "small", text: T.swipe })];
    if (!site.synthetic) intro.unshift(el("p", { text: T.results }));
    document.getElementById("results").replaceChildren(...intro,
      el("h3", { text: E.allPairs }),
      table([E.cols.horizon, E.cols.n, E.cols.acc, E.cols.pers, E.cols.status], allRows, [1, 2, 3], { cls: "wide", stickyFirst: true }),
      el("h3", { text: E.byPair }),
      table([E.cols.pair, E.cols.n, E.cols.acc, E.cols.status], pairRows, [1, 2], { cls: "wide", stickyFirst: true }));
  });

  // ---------------- downloads (real mode only: the files are copies of the committed exports)
  part("downloads", () => {
    const dl = document.getElementById("downloads");
    if (site.synthetic) return;
    dl.replaceChildren(
      el("a", { class: "btn", href: "data/results_summary.csv", download: "", text: T.downloads.csv }),
      el("a", { class: "btn", href: "data/results.json", download: "", text: T.downloads.json }),
      el("a", { class: "btn", href: "data/data_dictionary.csv", download: "", text: T.downloads.dictionary }));
    dl.hidden = false;
  });

  // ---------------- fan chart
  part("fan chart", () => {
    const sel = document.getElementById("origin");
    site.featured.forEach((f, i) => sel.appendChild(el("option", { value: String(i), text: f.pair + "  " + f.date })));
    const fl = document.getElementById("fan-legend");
    fl.replaceChildren(S.legendItem("s-sample", F.legend.sample), S.legendItem("s-mean", F.legend.mean),
      S.legendItem("s-actual", F.legend.actual), S.legendItem("s-zero", F.legend.zero));
    const rel = (v) => (v > 0 ? F.above : v < 0 ? F.below : F.at);

    function drawFan(i) {
      const f = site.featured[i];
      const W = 640, H = 340, l = 86, r = 78, t = 14, b = 270;
      const [lo, hi] = S.dataRange(f.samples.concat([f.mean, f.actual]), [0], 0.08);
      const sc = S.niceScale(lo, hi, 5), yTicks = S.withTick(sc.ticks, 0);
      const n = f.mean.length;
      const x = S.scale(0, n - 1, l, W - r), y = S.scale(lo, hi, b, t);
      const svg = S.chart(W, H, F.chartLabel);
      const xt = [0, Math.round((n - 1) / 3), Math.round(((n - 1) * 2) / 3), n - 1];
      S.axes(svg, { l, r: W - r, t, b, x, y }, xt, yTicks, F.axisX, F.axisY, (v) => String(v + 1), (v) => fmt.signedPct(v, sc.decimals));
      const xs = f.mean.map((_, k) => x(k));
      svg.appendChild(S.s("line", { class: "s-zero", x1: l, x2: W - r, y1: y(0), y2: y(0) }));
      f.samples.forEach((p) => svg.appendChild(S.s("path", { class: ("s-sample " + KLChips.hueClass(f.pair)).trim(), d: S.pathD(xs, p.map(y)) })));
      svg.appendChild(S.s("path", { class: "s-mean", d: S.pathD(xs, f.mean.map(y)) }));
      svg.appendChild(S.s("path", { class: "s-actual", d: S.pathD(xs, f.actual.map(y)) }));
      // direct labels at the end of each line (kept 14 px apart so they never overlap)
      const yMean = y(f.mean[n - 1]);
      let yAct = y(f.actual[n - 1]);
      if (Math.abs(yAct - yMean) < 14) yAct = yAct >= yMean ? yMean + 14 : yMean - 14;
      svg.appendChild(S.s("text", { class: "end-label", x: x(n - 1) + 6, y: yMean + 4 }, F.endMean));
      svg.appendChild(S.s("text", { class: "end-label", x: x(n - 1) + 6, y: yAct + 4 }, F.endActual));
      document.getElementById("fan").replaceChildren(svg);
      const sampleLine = fl.querySelector("line.s-sample");
      if (sampleLine) sampleLine.setAttribute("class", ("s-sample " + KLChips.hueClass(f.pair)).trim());
      // neutral, descriptive sentence built from the data
      const mEnd = f.mean[n - 1], aEnd = f.actual[n - 1];
      const text = " " + f.date + ". " + F.sentence(rel(mEnd) + " (" + fmt.signedPct(mEnd) + ")", rel(aEnd) + " (" + fmt.signedPct(aEnd) + ")", f.signal_24 > 0 ? F.up : F.down);
      document.getElementById("fan-caption").replaceChildren(KL.chip(f.pair), document.createTextNode(text));
    }
    sel.addEventListener("change", () => drawFan(Number(sel.value)));
    if (site.featured.length) drawFan(0);
  });

  // ---------------- running score vs coin-flip band: synthetic builds only; in real mode the whole section is removed
  part("running score", () => {
    const rs = site.running_score;
    const sec = document.getElementById("h-run") && document.getElementById("h-run").parentElement;
    if (!rs) { if (sec) sec.remove(); return; }
    if (!rs.n.length) return;
    const W = 640, H = 340, l = 66, r = 16, t = 14, b = 270;
    const REF = 0.5;                                  // chance level for a two-way call
    const [lo, hi] = S.dataRange([rs.kronos, rs.band_lo, rs.band_hi, rs.band_median], [REF], 0.06);
    const sc = S.niceScale(lo, hi, 5), yTicks = S.withTick(sc.ticks, REF);
    const x = S.scale(rs.n[0], rs.n[rs.n.length - 1], l, W - r), y = S.scale(lo, hi, b, t);
    const svg = S.chart(W, H, "Running share of correct calls for Kronos against the coin-flip band");
    const xt = S.niceScale(rs.n[0], rs.n[rs.n.length - 1], 4).ticks.map(Math.round);
    S.axes(svg, { l, r: W - r, t, b, x, y }, xt, yTicks, "origins scored (forecast day, then pair)", "share correct",
      (v) => String(v), (v) => fmt.pct(v, Math.max(0, sc.decimals - 2)));
    svg.appendChild(S.s("line", { class: "s-zero", x1: l, x2: W - r, y1: y(REF), y2: y(REF) }));
    const xs = rs.n.map(x);
    const hiY = rs.band_hi.map((v) => y(v)), loY = rs.band_lo.map((v) => y(v));
    svg.appendChild(S.s("path", { class: "s-band", d: S.pathD(xs, hiY) + " " + S.pathD(xs.slice().reverse(), loY.slice().reverse()).replace(/^M/, "L") + " Z" }));
    svg.appendChild(S.s("path", { class: "s-bandedge", d: S.pathD(xs, hiY) }));
    svg.appendChild(S.s("path", { class: "s-bandedge", d: S.pathD(xs, loY) }));
    svg.appendChild(S.s("path", { class: "s-median", d: S.pathD(xs, rs.band_median.map(y)) }));
    svg.appendChild(S.s("path", { class: "s-mean", d: S.pathD(xs, rs.kronos.map(y)) }));
    document.getElementById("running").replaceChildren(svg);
    document.getElementById("running-legend").append(S.legendItem("s-mean", "Kronos: share of correct calls so far"),
      S.legendItem("s-bandedge", "Coin-flip band (central range of simulated fair-coin runs)"), S.legendItem("s-median", "Coin-flip median"),
      S.legendItem("s-zero", fmt.pct(REF, 0) + " = chance level"));
    document.getElementById("running-note").textContent = rs.band + ". The band is an illustration; the inference is on the front page.";
  });
})();
