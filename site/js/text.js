// Method and Limits pages: text is rendered from site.json (quoted from PREREGISTRATION.md at build time),
// so no figures are typed into the HTML.
window.KL = window.KL || {};
KL.text = {
  swipe: "Swipe sideways to see all columns",
  results: "Only pre-registered and already-computed figures are shown. All rows except the all-pairs row at the primary horizon are exploratory.",
  badgePrimary: "primary", badgeExploratory: "exploratory",
  verdictTag: { h1: "H1", h2: "H2" },
  toc: "On this page",
  callout: { deviation: "Recorded deviation", limit: "Limit", disclosure: "Disclosure" },
  game: { progress: (a, t) => "Answered " + a + " of " + t, thisWas: "This was ", on: " on " },
  verdict: { h1: "Versus a coin flip", h2: "Versus always-up" },
  est: { h1: "Kronos accuracy", h2: "Kronos accuracy minus always-up accuracy" },
  decision: "Decision", rawP: "Raw p-value (exact test)", holmP: "Holm-adjusted p-value",
  intervalName: (level) => level + " % day-block interval",
  scored: "Origins scored", of: "out of", planned: "planned", downCalls: "Kronos down-calls",
  powerScored: "Smallest detectable edge at the number scored", powerPlanned: "Smallest detectable edge at the planned number",
  largestEdge: "Largest edge not ruled out (upper end of the interval)", overCoin: "over a coin flip", overAlwaysUp: "over always-up",
  noDownCalls: "Kronos made no down-calls, so the comparison with always-up carries no information.",
  downText: (d, shift) => "Kronos made " + d + " down-calls. The smallest detectable shift in the share of correct down-calls is about " + shift + ".",
  powerCols: ["Analysis set N", "Smallest detectable edge", "Accuracy needed"],
  plotTitle: "Where the estimates sit against their reference lines",
  plot: { chartLabel: "Interval plot: Kronos accuracy and the accuracy difference with their intervals against reference lines",
    rowNames: { accuracy: "Kronos accuracy", difference: "Kronos accuracy minus always-up accuracy" },
    estimate: "estimate", interval: "interval", to: "to", reference: "reference", naive: "naive, ignores clustering",
    crosses: "The interval includes the reference line", excludes: "The interval does not include the reference line" },
  plotNote: "Diamond: estimate. Thick bar: the day-block interval. Thin bar: the naive interval. Dashed line: the reference value.",
  downloads: { csv: "Download CSV", json: "Download JSON", dictionary: "Data dictionary" },
  evidence: { allPairs: "All pairs, by horizon", byPair: "By pair, at the primary horizon",
    cols: { horizon: "Horizon (bars)", n: "N", acc: "Kronos accuracy", pers: "Persistence accuracy (exploratory)", status: "Status", pair: "Pair" },
    horizonPrefix: "h = " },
};
KL.hints = KL.text;   // older name

(async function () {
  "use strict";
  const site = await KL.loadSite();
  if (!site) return;
  const { el } = KL;
  const DEVIATIONS_AFTER = "5";   // the section that names launch_run.sh as a run-critical file
  const TITLES = { "3": "Hypotheses", "4": "Data and window", "5": "Model and inference", "6": "Definitions",
    "7": "Primary analysis", "8": "Power", "9": "Exploratory analyses", "10": "Run protocol" };

  // Long hex strings (hashes) are shown in monospace and may wrap anywhere.
  function richInto(node, text) {
    text.split(/([0-9a-f]{40,})/).forEach((part, i) => node.appendChild(i % 2 ? el("code", { class: "mono", text: part }) : document.createTextNode(part)));
    return node;
  }

  function renderTable(t) {
    const wrap = el("div", {}, [el("p", { class: "small", text: KL.hints.swipe }),
      KL.table(t.header, t.rows.map((r) => ({ cells: r })), [], { cls: "wide", mono: t.mono })]);
    return wrap;
  }

  function renderItems(items) {
    const frag = document.createDocumentFragment();
    let ul = null, sub = null;
    items.forEach((it) => {
      if (it.level === -2) { ul = sub = null; frag.appendChild(renderTable(it.table)); return; }
      if (it.level === -1) { ul = sub = null; frag.appendChild(richInto(el("p"), it.text)); return; }
      if (it.level === 0) { if (!ul) { ul = el("ul"); frag.appendChild(ul); } const li = richInto(el("li"), it.text); ul.appendChild(li); sub = null; return; }
      if (!ul) { ul = el("ul"); frag.appendChild(ul); }
      const last = ul.lastElementChild || ul.appendChild(el("li"));
      if (!sub || sub.parentNode !== last) { sub = el("ul"); last.appendChild(sub); }
      sub.appendChild(richInto(el("li"), it.text));
    });
    return frag;
  }

  const m = document.getElementById("method-sections");
  if (m) {
    Object.keys(site.method).forEach((k) => {
      m.appendChild(el("h2", { text: TITLES[k] || "Section" }));
      m.appendChild(renderItems(site.method[k]));
      if (k === DEVIATIONS_AFTER) {
        m.appendChild(el("h2", { id: "recorded-deviations", text: "Recorded deviations" }));
        if (!site.deviations.length) m.appendChild(el("p", { text: "No deviations are recorded." }));
        site.deviations.forEach((d) => {
          m.appendChild(el("div", { class: "callout deviation" }, [el("div", { class: "label", text: KL.text.callout.deviation }),
            el("h3", { text: d.date + (d.title ? ": " + d.title : "") }), el("p", { text: d.text })]));
        });
      }
    });
  }
  document.querySelectorAll(".preamble").forEach((n) => { n.textContent = site.preamble; });
  const lim = document.getElementById("limits-list");
  if (lim) site.limits.forEach((t) => {
    const li = richInto(el("li", { class: "callout limit" }), t);
    li.insertBefore(el("div", { class: "label", text: KL.text.callout.limit }), li.firstChild);
    site.limit_notes.filter((n) => t.includes(n.contains)).forEach((n) => li.appendChild(el("div", { class: "small", text: n.text })));
    lim.appendChild(li);
  });
  const dis = document.getElementById("disclosures-list");
  if (dis) site.disclosures.forEach((t) => {
    const li = richInto(el("li", { class: "callout disclosure" }), t);
    li.insertBefore(el("div", { class: "label", text: KL.text.callout.disclosure }), li.firstChild);
    dis.appendChild(li);
  });
  const sel = document.getElementById("selection-rules");
  if (sel) {
    const s = site.selection;
    [s.pool, "Fan-chart origins: " + s.featured.rule + ", seed " + s.featured.seed + ", " + s.featured.n + " origins.",
      "Game windows: " + s.game.rule + ", seed " + s.game.seed + ", " + s.game.n + " windows.",
      "Coin flips: " + s.coin_flips.rule + ", seed " + s.coin_flips.seed + ".", s.reveal_note].forEach((t) => sel.appendChild(el("li", { text: t })));
  }

  // In-page table of contents from the long-form headings (shown on wide screens; see style.css)
  const toc = document.getElementById("toc");
  if (toc) {
    const used = new Set(), ul = el("ul");
    document.querySelectorAll(".longform h2").forEach((h, i) => {
      if (!h.id) {
        let id = h.textContent.toLowerCase().replace(/[^a-z]+/g, "-").replace(/^-|-$/g, "") || "section";
        while (used.has(id) || document.getElementById(id)) id += "-x";
        h.id = id;
      }
      used.add(h.id);
      ul.appendChild(el("li", {}, [el("a", { href: "#" + h.id, text: h.textContent })]));
    });
    toc.replaceChildren(el("p", { text: KL.text.toc }), ul);
  }
})();
