// A tiny DOM stand-in so the site's page scripts can be EXECUTED in node (no browser, no rendering, no network).
// It parses a site/*.html file, runs every <script src> in order inside one vm context, serves data/site.json from disk,
// and reports any uncaught exception. It checks that scripts run and build the expected elements, not how they look.
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const VOID = new Set(["meta", "link", "br", "img", "input", "hr"]);

class TextNode {
  constructor(t) { this.nodeType = 3; this.data = String(t); this.parentNode = null; }
  get textContent() { return this.data; }
  get parentElement() { return this.parentNode; }
}

class Element {
  constructor(tag, doc) {
    this.nodeType = 1; this.tagName = tag.toLowerCase(); this.doc = doc; this.children = []; this.attrs = {}; this.parentNode = null;
    this.style = {}; this.listeners = {}; this.hidden = false; this.focused = false;
  }
  get parentElement() { return this.parentNode; }
  get firstChild() { return this.children[0] || null; }
  get firstElementChild() { return this.children.find((c) => c.nodeType === 1) || null; }
  get lastElementChild() { return [...this.children].reverse().find((c) => c.nodeType === 1) || null; }
  get id() { return this.attrs.id || ""; }
  set id(v) { this.attrs.id = v; }
  get className() { return this.attrs.class || ""; }
  get title() { return this.attrs.title || ""; }
  get classes() { return (this.attrs.class || "").split(/\s+/).filter(Boolean); }
  get textContent() { return this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this.children.forEach((c) => (c.parentNode = null)); this.children = []; if (String(v) !== "") this.appendChild(new TextNode(v)); }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === "hidden") this.hidden = true; }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  _adopt(n) {
    if (n && n.isFragment) { const kids = n.children.slice(); n.children = []; kids.forEach((k) => this._adopt(k)); return; }
    if (n.parentNode) n.parentNode.children = n.parentNode.children.filter((c) => c !== n);
    n.parentNode = this; this.children.push(n);
  }
  appendChild(n) { this._adopt(n); return n; }
  append(...ns) { ns.forEach((n) => this._adopt(typeof n === "string" ? new TextNode(n) : n)); }
  replaceChildren(...ns) { this.children.forEach((c) => (c.parentNode = null)); this.children = []; this.append(...ns); }
  insertBefore(n, ref) {
    if (n.parentNode) n.parentNode.children = n.parentNode.children.filter((c) => c !== n);
    n.parentNode = this; const i = ref ? this.children.indexOf(ref) : -1;
    if (i < 0) this.children.push(n); else this.children.splice(i, 0, n);
    return n;
  }
  prepend(n) { this.insertBefore(typeof n === "string" ? new TextNode(n) : n, this.children[0]); }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((c) => c !== this); this.parentNode = null; }
  addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }
  dispatch(t, ev) { (this.listeners[t] || []).forEach((f) => f(Object.assign({ preventDefault() {}, key: "" }, ev))); }
  click() { this.dispatch("click"); }
  focus() { this.focused = true; }
  *walk() { yield this; for (const c of this.children) if (c.nodeType === 1) yield* c.walk(); }
  _matches(sel) {
    const m = sel.match(/^([a-z0-9]*)((?:[.#][\w-]+)*)$/i);
    if (!m) return false;
    if (m[1] && m[1].toLowerCase() !== this.tagName) return false;
    for (const part of m[2].match(/[.#][\w-]+/g) || []) {
      if (part[0] === "." && !this.classes.includes(part.slice(1))) return false;
      if (part[0] === "#" && this.id !== part.slice(1)) return false;
    }
    return true;
  }
  _isUnder(chain, from) {            // the element matches the last selector and each earlier selector matches some ancestor, in order
    let i = chain.length - 1;
    if (!this._matches(chain[i])) return false;
    let a = this.parentNode;
    for (i -= 1; i >= 0; i--) {
      while (a && a !== from.parentNode && !a._matches(chain[i])) a = a.parentNode;
      if (!a || a === from.parentNode) return false;
      a = a.parentNode;
    }
    return true;
  }
  querySelectorAll(sel) {
    const out = [];
    sel.split(",").forEach((one) => {
      const chain = one.trim().split(/\s+/);
      for (const e of this.walk()) if (e !== this && e._isUnder(chain, this)) if (!out.includes(e)) out.push(e);
    });
    return out;
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  getElementById(id) { for (const e of this.walk()) if (e.id === id) return e; return null; }
  find(sel) { return this.querySelectorAll(sel); }
}

function makeDocument() {
  const doc = {
    title: "", listeners: {},
    createElement: (t) => new Element(t, doc),
    createElementNS: (_ns, t) => new Element(t, doc),
    createTextNode: (t) => new TextNode(t),
    createDocumentFragment: () => { const f = new Element("#fragment", doc); f.isFragment = true; return f; },
    addEventListener(t, f) { (doc.listeners[t] = doc.listeners[t] || []).push(f); },
    getElementById: (id) => doc.documentElement.getElementById(id),
    querySelectorAll: (s) => doc.documentElement.querySelectorAll(s),
    querySelector: (s) => doc.documentElement.querySelector(s),
  };
  doc.documentElement = new Element("html", doc);
  return doc;
}

function parseHtml(html, doc) {
  const root = doc.documentElement;
  const stack = [root];
  const scripts = [];
  const re = /<!--[\s\S]*?-->|<!doctype[^>]*>|<script\b([^>]*)>([\s\S]*?)<\/script>|<style[\s\S]*?<\/style>|<\/([a-z0-9]+)\s*>|<([a-z0-9]+)((?:\s+[^>]*?)?)(\/?)>|([^<]+)/gi;
  let m;
  while ((m = re.exec(html))) {
    if (m[1] !== undefined) { const src = /src="([^"]+)"/.exec(m[1]); if (src) scripts.push(src[1]); continue; }
    if (m[3]) { if (stack.length > 1 && stack[stack.length - 1].tagName === m[3].toLowerCase()) stack.pop(); continue; }
    if (m[4]) {
      const el = doc.createElement(m[4]);
      for (const a of m[5].matchAll(/([\w:-]+)(?:="([^"]*)")?/g)) el.setAttribute(a[1], a[2] === undefined ? "" : a[2]);
      if (m[4].toLowerCase() === "html") continue;
      stack[stack.length - 1].appendChild(el);
      if (!VOID.has(m[4].toLowerCase()) && !m[6]) stack.push(el);
      continue;
    }
    if (m[7] !== undefined && stack.length > 1 && m[7].trim()) stack[stack.length - 1].appendChild(new TextNode(m[7]));
  }
  const find = (t) => root.querySelector(t);
  doc.body = find("body") || root;
  return scripts;
}

// Run a page: returns { doc, errors, scripts, win }. `siteFile` is the site.json to serve.
async function runPage(htmlFile, siteFile, opts = {}) {
  const doc = makeDocument();
  const scripts = parseHtml(fs.readFileSync(htmlFile, "utf8"), doc);
  const siteDir = path.dirname(htmlFile);
  const errors = [];
  const onRej = (e) => errors.push(e);
  process.on("unhandledRejection", onRej);
  const win = {
    document: doc,
    Node: Object.assign(function Node() {}, {}),
    fetch: async (url) => {
      if (url !== "data/site.json") throw new Error("unexpected fetch " + url);
      const text = fs.readFileSync(siteFile, "utf8");
      return { ok: true, status: 200, json: async () => JSON.parse(text) };
    },
    console, setTimeout, clearTimeout,
  };
  win.window = win;
  win.globalThis = win;
  Object.defineProperty(win.Node, Symbol.hasInstance, { value: (o) => !!o && (o.nodeType === 1 || o.nodeType === 3) });
  const ctx = vm.createContext(win);
  for (const s of scripts) {
    try { vm.runInContext(fs.readFileSync(path.join(siteDir, s), "utf8"), ctx, { filename: s }); }
    catch (e) { errors.push(e); }
  }
  await new Promise((r) => setTimeout(r, opts.wait || 60));
  process.off("unhandledRejection", onRej);
  return { doc, errors, scripts, win, ctx };
}

module.exports = { runPage, Element, TextNode };
