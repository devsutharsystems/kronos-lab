// Method and Limits pages: text is rendered from site.json (quoted from PREREGISTRATION.md at build time),
// so no figures are typed into the HTML.
(async function () {
  "use strict";
  const site = await KL.loadSite();
  if (!site) return;
  const { el } = KL;
  const TITLES = { "3": "Hypotheses", "4": "Data and window", "5": "Model and inference", "6": "Definitions",
    "7": "Primary analysis", "8": "Power", "9": "Exploratory analyses", "10": "Run protocol" };

  function renderItems(items) {
    const frag = document.createDocumentFragment();
    let ul = null, sub = null;
    items.forEach((it) => {
      if (it.level === -1) { ul = sub = null; frag.appendChild(el("p", { text: it.text })); return; }
      if (it.level === 0) { if (!ul) { ul = el("ul"); frag.appendChild(ul); } const li = el("li", { text: it.text }); ul.appendChild(li); sub = null; return; }
      if (!ul) { ul = el("ul"); frag.appendChild(ul); }
      const last = ul.lastElementChild || ul.appendChild(el("li"));
      if (!sub || sub.parentNode !== last) { sub = el("ul"); last.appendChild(sub); }
      sub.appendChild(el("li", { text: it.text }));
    });
    return frag;
  }

  const m = document.getElementById("method-sections");
  if (m) {
    Object.keys(site.method).forEach((k) => {
      m.appendChild(el("h2", { text: TITLES[k] || "Section" }));
      m.appendChild(renderItems(site.method[k]));
    });
  }
  const lim = document.getElementById("limits-list");
  if (lim) site.limits.forEach((t) => lim.appendChild(el("li", { text: t })));
  const dis = document.getElementById("disclosures-list");
  if (dis) site.disclosures.forEach((t) => dis.appendChild(el("li", { text: t })));
  const sel = document.getElementById("selection-rules");
  if (sel) {
    const s = site.selection;
    [s.pool, "Fan-chart origins: " + s.featured.rule + ", seed " + s.featured.seed + ", " + s.featured.n + " origins.",
      "Game windows: " + s.game.rule + ", seed " + s.game.seed + ", " + s.game.n + " windows.",
      "Coin flips: " + s.coin_flips.rule + ", seed " + s.coin_flips.seed + ".", s.reveal_note].forEach((t) => sel.appendChild(el("li", { text: t })));
  }
})();
