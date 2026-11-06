// Evidence page: fan chart, running score vs coin-flip band, results table. All numbers come from site.json.
(async function () {
  "use strict";
  const site = await KL.loadSite();
  if (!site) return;
  const { el, fmt, table } = KL;
  const S = KLSVG;

  // ---------------- fan chart
  const sel = document.getElementById("origin");
  site.featured.forEach((f, i) => sel.appendChild(el("option", { value: String(i), text: f.pair + "  " + f.date })));

  function drawFan(i) {
    const f = site.featured[i];
    const W = 640, H = 340, l = 62, r = 16, t = 14, b = 270;
    const all = [].concat(...f.samples, f.mean, f.actual, [0]);
    let lo = Math.min(...all), hi = Math.max(...all);
    const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
    const n = f.mean.length;
    const x = S.scale(0, n - 1, l, W - r), y = S.scale(lo, hi, b, t);
    const svg = S.chart(W, H, "Fan chart of the eleven sampled price paths, their mean, and the actual path, as percent change from the last context close");
    const xt = [0, Math.round((n - 1) / 3), Math.round(((n - 1) * 2) / 3), n - 1];
    S.axes(svg, { l, r: W - r, t, b, x, y }, xt, S.niceTicks(lo, hi, 5), "bar of the forecast day", "change vs last close",
      (v) => String(v + 1), (v) => fmt.signedPct(v, 1));
    const xs = f.mean.map((_, k) => x(k));
    svg.appendChild(S.s("line", { class: "s-zero", x1: l, x2: W - r, y1: y(0), y2: y(0) }));
    f.samples.forEach((p) => svg.appendChild(S.s("path", { class: "s-sample", d: S.pathD(xs, p.map(y)) })));
    svg.appendChild(S.s("path", { class: "s-mean", d: S.pathD(xs, f.mean.map(y)) }));
    svg.appendChild(S.s("path", { class: "s-actual", d: S.pathD(xs, f.actual.map(y)) }));
    document.getElementById("fan").replaceChildren(svg);
    const dir = (v) => (v > 0 ? "up" : v < 0 ? "down" : "flat");
    const kronosEnd = f.mean[n - 1], actualEnd = f.actual[n - 1];
    document.getElementById("fan-caption").textContent =
      f.pair + ", " + f.date + ". Kronos's mean path ends " + dir(kronosEnd) + " (" + fmt.signedPct(kronosEnd) + "); the actual path ends " +
      dir(actualEnd) + " (" + fmt.signedPct(actualEnd) + "). Kronos's call was " + (f.signal_24 === f.label_24 ? "correct" : "wrong") + " for this origin.";
  }
  sel.addEventListener("change", () => drawFan(Number(sel.value)));
  if (site.featured.length) drawFan(0);
  const fl = document.getElementById("fan-legend");
  fl.append(S.legendItem("s-sample", "One of the sampled paths"), S.legendItem("s-mean", "Mean of the sampled paths"),
    S.legendItem("s-actual", "Actual path"), S.legendItem("s-zero", "No change"));

  // ---------------- running score vs coin-flip band
  const rs = site.running_score;
  if (rs.n.length) {
    const W = 640, H = 340, l = 62, r = 16, t = 14, b = 270;
    const lastSpread = rs.band_hi[rs.n.length - 1] - rs.band_lo[rs.n.length - 1];
    const lo = Math.max(0, 0.5 - 1.6 * lastSpread), hi = Math.min(1, 0.5 + 1.6 * lastSpread);
    const clamp = (v) => Math.min(hi, Math.max(lo, v));
    const x = S.scale(rs.n[0], rs.n[rs.n.length - 1], l, W - r), y = S.scale(lo, hi, b, t);
    const svg = S.chart(W, H, "Running share of correct calls for Kronos against the coin-flip band");
    const xt = S.niceTicks(rs.n[0], rs.n[rs.n.length - 1], 4).map(Math.round);
    S.axes(svg, { l, r: W - r, t, b, x, y }, xt, S.niceTicks(lo, hi, 5), "origins scored (forecast day, then pair)", "share correct",
      (v) => String(v), (v) => fmt.pct(v, 0));
    const xs = rs.n.map(x);
    const hiY = rs.band_hi.map((v) => y(clamp(v))), loY = rs.band_lo.map((v) => y(clamp(v)));
    svg.appendChild(S.s("path", { class: "s-band", d: S.pathD(xs, hiY) + " " + S.pathD(xs.slice().reverse(), loY.slice().reverse()).replace(/^M/, "L") + " Z" }));
    svg.appendChild(S.s("path", { class: "s-bandedge", d: S.pathD(xs, hiY) }));
    svg.appendChild(S.s("path", { class: "s-bandedge", d: S.pathD(xs, loY) }));
    svg.appendChild(S.s("path", { class: "s-median", d: S.pathD(xs, rs.band_median.map((v) => y(clamp(v)))) }));
    svg.appendChild(S.s("path", { class: "s-mean", d: S.pathD(xs, rs.kronos.map((v) => y(clamp(v)))) }));
    document.getElementById("running").replaceChildren(svg);
    const rl = document.getElementById("running-legend");
    rl.append(S.legendItem("s-mean", "Kronos: share of correct calls so far"), S.legendItem("s-bandedge", "Coin-flip band (central range of simulated fair-coin runs)"),
      S.legendItem("s-median", "Coin-flip median"));
    document.getElementById("running-note").textContent = rs.band + ". The band is an illustration; the inference is on the front page.";
  }

  // ---------------- results table
  const rows = site.results_table.map((r) => {
    const tag = el("span", { class: r.primary ? "badge primary" : "badge", text: r.primary ? "primary" : "exploratory" });
    return { cls: r.primary ? "primary-row" : "", cells: [r.pair === "ALL" ? "all pairs" : r.pair, "h = " + r.horizon, fmt.int(r.n),
      fmt.pct(r.kronos_accuracy), r.primary ? "n/a" : fmt.pct(r.persistence_accuracy), tag] };
  });
  document.getElementById("results").replaceChildren(
    table(["Pair", "Horizon (bars)", "N", "Kronos accuracy", "Persistence accuracy", "Status"], rows, [2, 3, 4]));
})();
