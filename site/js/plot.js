// Interval plot helpers: pure functions (tested with node) and the SVG drawing. All numbers come from site.json.
(function (root) {
  "use strict";
  const S = typeof require !== "undefined" ? require("./svg.js") : root.KLSVG;
  const CHANCE = 0.5;    // chance level for a two-way call
  const NULL_DIFF = 0;   // no difference

  const finite2 = (a) => Array.isArray(a) && a.length === 2 && a.every((v) => typeof v === "number" && isFinite(v));

  // Rows of the plot, from site.json.primary only. The naive interval is used only when the file carries it.
  function rowsFromSite(site) {
    const p = site.primary;
    if (typeof p.accuracy !== "number" || !finite2(p.ci_accuracy) || typeof p.accuracy_diff !== "number" || !finite2(p.ci_diff)) return null;
    return [
      { id: "accuracy", tone: "h1", est: p.accuracy, ci: p.ci_accuracy, naive: finite2(p.naive_binomial_ci95) ? p.naive_binomial_ci95 : null, ref: CHANCE },
      { id: "difference", tone: "h2", est: p.accuracy_diff, ci: p.ci_diff, naive: null, ref: NULL_DIFF },
    ];
  }

  // Axis for one row: contains the estimate, both intervals and the reference line, with round ticks.
  function axisFor(row, count) {
    const vals = [row.est, row.ci[0], row.ci[1], row.ref].concat(row.naive || []);
    const [lo, hi] = S.dataRange([vals], [], 0.12);
    const sc = S.niceScale(lo, hi, count || 5);
    return { lo, hi, ticks: S.withTick(sc.ticks, row.ref), decimals: sc.decimals };
  }

  // Position of value v on the axis between pixel x0 and x1.
  function position(v, axis, x0, x1) {
    return x0 + ((v - axis.lo) / (axis.hi - axis.lo || 1)) * (x1 - x0);
  }

  // Does the interval cover the reference line?
  function crossesRef(row) { return row.ci[0] <= row.ref && row.ref <= row.ci[1]; }

  // Plain-text alternative that lists every number the plot uses. `f` formats a number for a row; `t` holds the text strings.
  function altText(rows, f, t) {
    return rows.map((r) => {
      const parts = [t.rowNames[r.id] + ": " + t.estimate + " " + f(r, r.est) + ", " + t.interval + " " + f(r, r.ci[0]) + " " + t.to + " " + f(r, r.ci[1]),
        t.reference + " " + f(r, r.ref)];
      if (r.naive) parts.push(t.naive + " " + f(r, r.naive[0]) + " " + t.to + " " + f(r, r.naive[1]));
      parts.push(crossesRef(r) ? t.crosses : t.excludes);
      return parts.join("; ") + ".";
    }).join(" ");
  }

  // Draw both rows into one SVG. t = text strings; f(row, v) = number formatter; level = interval level for the labels.
  function draw(site, t, f) {
    const rows = rowsFromSite(site);
    if (!rows) return null;
    const W = 640, H = 330, l = 24, r = 24, panelH = 140;
    const svg = S.chart(W, H, t.chartLabel);
    rows.forEach((row, i) => {
      const top = 10 + i * (panelH + 12), mid = top + 52, bottom = top + panelH - 34;
      const ax = axisFor(row, 5), x = (v) => position(v, ax, l, W - r);
      svg.appendChild(S.s("text", { x: l, y: top + 12, class: "plot-title" }, t.rowNames[row.id]));
      ax.ticks.forEach((v) => {
        svg.appendChild(S.s("line", { class: "axis", x1: x(v), x2: x(v), y1: bottom, y2: bottom + 5 }));
        svg.appendChild(S.s("text", { x: x(v), y: bottom + 19, "text-anchor": "middle" }, f(row, v, ax.decimals)));
      });
      svg.appendChild(S.s("line", { class: "axis", x1: l, x2: W - r, y1: bottom, y2: bottom }));
      svg.appendChild(S.s("line", { class: "s-zero", x1: x(row.ref), x2: x(row.ref), y1: top + 20, y2: bottom }));
      svg.appendChild(S.s("text", { x: x(row.ref), y: top + 32, "text-anchor": "middle", class: "plot-ref" }, t.reference + " " + f(row, row.ref)));
      if (row.naive) {
        svg.appendChild(S.s("line", { class: "ci-naive", x1: x(row.naive[0]), x2: x(row.naive[1]), y1: mid + 20, y2: mid + 20 }));
        svg.appendChild(S.s("text", { x: x(row.naive[1]) + 6, y: mid + 24, class: "plot-note" }, t.naive));
      }
      svg.appendChild(S.s("line", { class: "ci-main " + row.tone, x1: x(row.ci[0]), x2: x(row.ci[1]), y1: mid, y2: mid }));
      [row.ci[0], row.ci[1]].forEach((v) => svg.appendChild(S.s("line", { class: "ci-cap", x1: x(v), x2: x(v), y1: mid - 7, y2: mid + 7 })));
      const cx = x(row.est);
      svg.appendChild(S.s("path", { class: "ci-point", d: "M" + cx + " " + (mid - 8) + " L" + (cx + 8) + " " + mid + " L" + cx + " " + (mid + 8) + " L" + (cx - 8) + " " + mid + " Z" }));
    });
    return { svg, alt: altText(rows, f, t), rows };
  }

  const api = { CHANCE, NULL_DIFF, rowsFromSite, axisFor, position, crossesRef, altText, draw };
  root.KLPlot = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
