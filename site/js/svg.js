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

  function niceTicks(lo, hi, count) {
    const out = [];
    for (let i = 0; i <= count; i++) out.push(lo + ((hi - lo) * i) / count);
    return out;
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

  root.KLSVG = { s, scale, niceTicks, pathD, chart, axes, legendItem };
})(window);
