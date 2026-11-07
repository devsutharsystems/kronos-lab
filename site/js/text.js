// Method and Limits pages: text is rendered from site.json (quoted from PREREGISTRATION.md at build time),
// so no figures are typed into the HTML.
window.KL = window.KL || {};
KL.hints = { swipe: "Swipe sideways to see all columns",
  results: "Only pre-registered and already-computed figures are shown. All rows except the all-pairs row at the primary horizon are exploratory." };

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
          m.appendChild(el("h3", { text: d.date + (d.title ? ": " + d.title : "") }));
          m.appendChild(el("p", { text: d.text }));
        });
      }
    });
  }
  document.querySelectorAll(".preamble").forEach((n) => { n.textContent = site.preamble; });
  const lim = document.getElementById("limits-list");
  if (lim) site.limits.forEach((t) => {
    const li = richInto(el("li"), t);
    site.limit_notes.filter((n) => t.includes(n.contains)).forEach((n) => li.appendChild(el("div", { class: "small", text: n.text })));
    lim.appendChild(li);
  });
  const dis = document.getElementById("disclosures-list");
  if (dis) site.disclosures.forEach((t) => dis.appendChild(richInto(el("li"), t)));
  const sel = document.getElementById("selection-rules");
  if (sel) {
    const s = site.selection;
    [s.pool, "Fan-chart origins: " + s.featured.rule + ", seed " + s.featured.seed + ", " + s.featured.n + " origins.",
      "Game windows: " + s.game.rule + ", seed " + s.game.seed + ", " + s.game.n + " windows.",
      "Coin flips: " + s.coin_flips.rule + ", seed " + s.coin_flips.seed + ".", s.reveal_note].forEach((t) => sel.appendChild(el("li", { text: t })));
  }
})();
