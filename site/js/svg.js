// Inline SVG chart helpers. Plain geometry; all data comes from site.json.
(function (root) {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";   // XML namespace identifier, not a network resource

  function s(tag, attrs, text) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    return e;
  }

  function scale(d0, d1, r0, r1) {
    const span = d1 - d0 || 1;
    return (v) => r0 + ((v - d0) / span) * (r1 - r0);
  }

  // Round ticks inside [lo, hi]: step is 1, 2 or 5 times a power of ten. decimals = digits needed to print the step.
  function niceScale(lo, hi, count) {
    const raw = (hi - lo) / count || 1;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
    const decimals = Math.max(0, -Math.floor(Math.log10(step) + 1e-9));
    const ticks = [];
    for (let k = Math.ceil(lo / step - 1e-9); k * step <= hi + step * 1e-9; k++) ticks.push(Number((k * step).toFixed(decimals + 2)) + 0);
    return { ticks, step, decimals };
  }

  function niceTicks(lo, hi, count) { return niceScale(lo, hi, count).ticks; }

  // Axis range that contains every value in every array (plus extra values) with a fractional pad.
  function dataRange(arrays, extra, padFrac) {
    let lo = Infinity, hi = -Infinity;
    arrays.concat([extra || []]).forEach((a) => a.forEach((v) => { if (v < lo) lo = v; if (v > hi) hi = v; }));
    const pad = (hi - lo) * (padFrac == null ? 0.06 : padFrac) || 1;
    return [lo - pad, hi + pad];
  }

  // Make sure `v` is among the ticks (kept sorted).
  function withTick(ticks, v) {
    return ticks.some((t) => Math.abs(t - v) < 1e-9) ? ticks : ticks.concat([v]).sort((p, q) => p - q);
  }

  function pathD(xs, ys) {
    return xs.map((x, i) => (i ? "L" : "M") + x.toFixed(1) + " " + ys[i].toFixed(1)).join(" ");
  }

  // Create an <svg> with a viewBox; width/height come from CSS (class "chart").
  function chart(w, h, label) {
    const svg = s("svg", { viewBox: "0 0 " + w + " " + h, class: "chart", role: "img", "aria-label": label });
    return svg;
  }

  function axes(svg, box, xTicks, yTicks, xLabel, yLabel, xFmt, yFmt) {
    const { l, r, t, b, x, y } = box;
    yTicks.forEach((v) => {
      svg.appendChild(s("line", { class: "grid", x1: l, x2: r, y1: y(v), y2: y(v) }));
      svg.appendChild(s("text", { x: l - 6, y: y(v) + 4, "text-anchor": "end" }, yFmt(v)));
    });
    xTicks.forEach((v) => {
      svg.appendChild(s("line", { class: "axis", x1: x(v), x2: x(v), y1: b, y2: b + 5 }));
      svg.appendChild(s("text", { x: x(v), y: b + 19, "text-anchor": "middle" }, xFmt(v)));
    });
    svg.appendChild(s("line", { class: "axis", x1: l, x2: r, y1: b, y2: b }));
    svg.appendChild(s("line", { class: "axis", x1: l, x2: l, y1: t, y2: b }));
    svg.appendChild(s("text", { x: (l + r) / 2, y: b + 38, "text-anchor": "middle" }, xLabel));
    const yl = s("text", { x: 14, y: (t + b) / 2, "text-anchor": "middle", transform: "rotate(-90 14 " + (t + b) / 2 + ")" }, yLabel);
    svg.appendChild(yl);
  }

  // A legend row: a short line sample drawn with the same CSS class as the chart series.
  function legendItem(cls, label) {
    const li = document.createElement("li");
    const svg = s("svg", { viewBox: "0 0 50 12", "aria-hidden": "true" });
    svg.appendChild(s("line", { class: cls, x1: 1, x2: 49, y1: 6, y2: 6 }));
    li.appendChild(svg);
    li.appendChild(document.createTextNode(label));
    return li;
  }

  const api = { s, scale, niceScale, niceTicks, dataRange, withTick, pathD, chart, axes, legendItem };
  root.KLSVG = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
