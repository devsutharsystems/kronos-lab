// Serve site/ ONLY under the prefix /kronos-lab/ (as GitHub Pages serves a project site) on a loopback server and load every page.
// A path outside the prefix returns 404, so a root-absolute URL such as "/style.css" would fail here. No network beyond 127.0.0.1.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { runPageHttp } = require("./stubdom.js");

const SITE = path.resolve(__dirname, "../../site");
const PREFIX = "/kronos-lab/";
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".csv": "text/csv" };
const PAGES = ["index", "evidence", "game", "method", "limits"];

function start() {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, "http://127.0.0.1");
    if (!url.pathname.startsWith(PREFIX)) { res.statusCode = 404; return res.end("outside prefix"); }
    const rel = decodeURIComponent(url.pathname.slice(PREFIX.length)) || "index.html";
    const file = path.resolve(SITE, rel);
    if (!file.startsWith(SITE + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { res.statusCode = 404; return res.end("not found"); }
    res.setHeader("Content-Type", TYPES[path.extname(file)] || "application/octet-stream");
    res.end(fs.readFileSync(file));
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

test("control: a root-absolute path is 404 under the prefix server, the prefixed path is 200", async () => {
  const server = await start();
  const base = "http://127.0.0.1:" + server.address().port;
  try {
    assert.equal((await fetch(base + "/style.css")).status, 404);
    assert.equal((await fetch(base + PREFIX + "style.css")).status, 200);
    assert.equal((await fetch(base + PREFIX + "data/site.json")).status, 200);
  } finally { server.close(); }
});

for (const page of PAGES) {
  test("page " + page + " loads its scripts, stylesheet and data under " + PREFIX, async () => {
    const server = await start();
    const base = "http://127.0.0.1:" + server.address().port + PREFIX;
    try {
      const html = await (await fetch(base + page + ".html")).text();
      const css = [...html.matchAll(/<link[^>]*href="([^"]+\.css)"/g)].map((m) => m[1]);
      assert.ok(css.length >= 1);
      for (const c of css) assert.equal((await fetch(new URL(c, base + page + ".html"))).status, 200, c);
      const r = await runPageHttp(base + page + ".html");
      assert.deepEqual(r.errors.map((e) => String((e && e.stack) || e).split("\n").slice(0, 2).join(" | ")), []);
      assert.ok(r.scripts.length >= 3);
      assert.ok(r.fetched.includes(PREFIX + "data/site.json"), "data/site.json was not fetched under the prefix");
      assert.ok(r.fetched.every((p) => p.startsWith(PREFIX)), "a request left the prefix: " + r.fetched.filter((p) => !p.startsWith(PREFIX)));
      if (page === "evidence") {
        for (const f of ["data/results_summary.csv", "data/results.json", "data/data_dictionary.csv"]) {
          assert.equal((await fetch(new URL(f, base))).status, 200, f);
          assert.ok(r.doc.getElementById("downloads").querySelectorAll("a").some((a) => a.getAttribute("href") === f), f);
        }
        assert.equal(r.doc.getElementById("results").querySelectorAll("table").length, 2);
      }
      if (page === "index") assert.equal(r.doc.getElementById("verdicts").querySelectorAll(".verdict").length, 2);
    } finally { server.close(); }
  });
}
