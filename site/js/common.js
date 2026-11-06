// Shared helpers: load site.json, synthetic banner, data binding, formatting, tiny DOM utilities.
// No numbers are typed here: everything shown comes from data/site.json.
(function (root) {
  "use strict";

  function el(tag, attrs, children) {
    const e = document.createElement(tag);
    for (const k in attrs || {}) {
      if (k === "text") e.textContent = attrs[k];
      else e.setAttribute(k, attrs[k]);
    }
    for (const c of children || []) e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    return e;
  }

  function get(obj, path) {
    return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
  }

  const fmt = {
    pct: (x, d) => (x == null ? "n/a" : (x * 100).toFixed(d == null ? 1 : d) + " %"),
    pp: (x, d) => (x == null ? "n/a" : (x >= 0 ? "+" : "") + (x * 100).toFixed(d == null ? 1 : d) + " pp"),
    ppRaw: (x, d) => (x == null ? "n/a" : x.toFixed(d == null ? 2 : d) + " pp"),
    signedPct: (x, d) => (x == null ? "n/a" : (x >= 0 ? "+" : "") + x.toFixed(d == null ? 2 : d) + " %"),
    p: (x) => (x == null ? "n/a" : x < 0.001 ? x.toExponential(2) : x.toFixed(4)),
    int: (x) => (x == null ? "n/a" : String(Math.round(x))),
    num: (x, d) => (x == null ? "n/a" : x.toFixed(d == null ? 3 : d)),
  };

  function applyFmt(v, how) {
    if (v == null) return "n/a";
    if (Array.isArray(v)) {
      if (how === "ci") return "[" + v.map((x) => fmt.pct(x)).join(", ") + "]";
      if (how === "cipp") return "[" + v.map((x) => fmt.pp(x)).join(", ") + "]";
      return v.join(", ");
    }
    if (how && fmt[how]) return fmt[how](v);
    return String(v);
  }

  function bindAll(site) {
    document.querySelectorAll("[data-bind]").forEach((n) => {
      n.textContent = applyFmt(get(site, n.getAttribute("data-bind")), n.getAttribute("data-fmt"));
    });
    document.querySelectorAll("a[data-prereg]").forEach((a) => a.setAttribute("href", PREREG_URL));
  }

  function applySynthetic(site) {
    const banner = document.getElementById("synthetic-banner");
    if (site.synthetic) {
      banner.textContent = "SYNTHETIC DEMO DATA, NOT KRONOS RESULTS";
      banner.hidden = false;
      document.body.classList.add("has-banner");
      if (!document.title.startsWith("[SYNTHETIC]")) document.title = "[SYNTHETIC] " + document.title;
    } else {
      banner.hidden = true;
    }
  }

  function table(headers, rows, numericCols, opts) {
    opts = opts || {};
    const num = new Set(numericCols || []);
    const mono = new Set(opts.mono || []);
    const t = el("table", { class: [opts.cls || "", opts.stickyFirst ? "sticky-first" : ""].join(" ").trim() });
    const thead = el("thead");
    const hr = el("tr");
    headers.forEach((h, i) => hr.appendChild(el("th", { scope: "col", class: (num.has(i) ? "num " : "") + (mono.has(i) ? "mono" : ""), text: h })));
    thead.appendChild(hr);
    t.appendChild(thead);
    const tb = el("tbody");
    rows.forEach((r) => {
      const tr = el("tr", r.cls ? { class: r.cls } : {});
      r.cells.forEach((c, i) => {
        const td = el("td", { class: (num.has(i) ? "num " : "") + (mono.has(i) ? "mono" : "") });
        if (c instanceof Node) td.appendChild(c); else td.textContent = c;
        tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    return el("div", { class: "tablewrap" }, [t]);
  }

  let siteCache = null;
  function loadSite() { return siteCache || (siteCache = loadSiteOnce()); }

  async function loadSiteOnce() {
    try {
      const r = await fetch("data/site.json", { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const site = await r.json();
      applySynthetic(site);
      bindAll(site);
      return site;
    } catch (e) {
      const m = document.getElementById("load-error");
      if (m) { m.textContent = "Could not load data/site.json (" + e.message + "). Serve the site folder over HTTP."; m.hidden = false; }
      return null;
    }
  }

  root.KL = Object.assign(root.KL || {}, { el, get, fmt, applyFmt, table, loadSite, bindAll });
})(window);
