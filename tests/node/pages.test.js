// Smoke tests: EXECUTE every page's scripts (in the order the HTML lists them) in a stub DOM against the committed site/data/site.json.
// They fail on any uncaught exception and check that the key elements exist afterwards. They do not test how anything looks.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { runPage } = require("./stubdom.js");

const SITE = path.resolve(__dirname, "../../site");
const DATA = path.join(SITE, "data", "site.json");
const site = JSON.parse(fs.readFileSync(DATA, "utf8"));
const run = (page) => runPage(path.join(SITE, page + ".html"), DATA);
const noErrors = (r) => assert.deepEqual(r.errors.map((e) => String((e && e.stack) || e).split("\n").slice(0, 3).join(" | ")), []);
const BAD = /\b(correct|wrong|right|miss|win|beat)\b/i;

test("the committed site.json is real data (not synthetic)", () => {
  assert.equal(site.synthetic, false);
  assert.equal(site.running_score, null);
});

test("result page: decision text, verdict cards, plot, stat cards, details", async () => {
  const r = await run("index");
  noErrors(r);
  const d = r.doc;
  assert.equal(d.getElementById("headline-text").textContent, site.headline.headline);
  const cards = d.getElementById("verdicts").querySelectorAll(".verdict");
  assert.equal(cards.length, 2);
  assert.deepEqual(cards.map((c) => c.querySelector(".tag").textContent), ["H1", "H2"]);
  assert.ok(cards[0].textContent.includes(site.headline.decision_h1) && cards[1].textContent.includes(site.headline.decision_h2));
  assert.equal(d.getElementById("interval-plot").querySelectorAll("svg").length, 1);
  assert.ok(d.getElementById("interval-alt").textContent.length > 50);
  assert.equal(d.getElementById("statcards").querySelectorAll(".stat").length, 4);
  const det = d.querySelector("details.allnums");
  assert.ok(det && d.getElementById("allnums-title").textContent.length > 5 && det.querySelectorAll("dd").length === 10);
  assert.ok(d.getElementById("power-table").querySelectorAll("tbody tr").length === 3);
});

test("evidence page: legend, both tables with chips and one primary badge, no running-score section", async () => {
  const r = await run("evidence");
  noErrors(r);
  const d = r.doc;
  assert.equal(d.getElementById("fan-legend").children.length, 4);
  const legendText = d.getElementById("fan-legend").textContent;
  ["dotted", "solid", "dash-dot"].forEach((w) => assert.ok(legendText.includes(w), w));
  const tables = d.getElementById("results").querySelectorAll("table");
  assert.equal(tables.length, 2);
  const [all, byPair] = tables;
  assert.equal(all.querySelectorAll("tbody tr").length, site.results_table.all_pairs.length);
  const pairRows = byPair.querySelectorAll("tbody tr");
  assert.equal(pairRows.length, site.results_table.by_pair_h24.length);
  assert.equal(pairRows.length, 6);
  pairRows.forEach((row) => {
    const chip = row.querySelector(".chip");
    assert.ok(chip, "pair row without chip");
    assert.ok(["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE"].includes(chip.textContent));
    assert.ok(chip.classes.some((c) => c.startsWith("pair-")));
  });
  const primary = d.getElementById("results").querySelectorAll(".badge.primary");
  assert.equal(primary.length, 1);
  const prow = all.querySelectorAll("tbody tr").find((tr) => tr.querySelector(".badge.primary"));
  assert.equal(prow.querySelector("td").textContent, "h = 24");
  assert.equal(d.getElementById("results").querySelectorAll(".badge").length, 3 + 6);
  assert.equal(d.getElementById("h-run"), null, "running-score section must be removed in real mode");
  assert.equal(d.getElementById("running"), null);
  assert.equal(d.getElementById("downloads").hidden, false);
  assert.equal(d.getElementById("downloads").querySelectorAll("a").length, 3);
  assert.equal(d.getElementById("load-error").hidden, true);
});

test("evidence page: fan chart for every origin has end labels and a neutral sentence", async () => {
  const r = await run("evidence");
  noErrors(r);
  const d = r.doc;
  const sel = d.getElementById("origin");
  assert.equal(sel.querySelectorAll("option").length, site.featured.length);
  for (let i = 0; i < site.featured.length; i++) {
    sel.value = String(i);
    sel.dispatch("change");
    const fan = d.getElementById("fan");
    assert.equal(fan.querySelectorAll("text.end-label").length, 2);
    assert.deepEqual(fan.querySelectorAll("text.end-label").map((t) => t.textContent), ["mean", "actual"]);
    assert.equal(fan.querySelectorAll("path.s-sample").length, 11);
    assert.equal(fan.querySelectorAll("path.s-mean").length, 1);
    assert.equal(fan.querySelectorAll("path.s-actual").length, 1);
    const cap = d.getElementById("fan-caption");
    assert.ok(cap.querySelector(".chip"));
    assert.match(cap.textContent, /The mean of the samples ends (above|below|at) .*; the actual path ends (above|below|at) .*; the signal pointed (up|down)\.$/);
    assert.doesNotMatch(cap.textContent, BAD);
    assert.equal(d.getElementById("fan-legend").querySelector("line.s-sample").classes.some((c) => c.startsWith("pair-")), true);
  }
});

test("game page: first window renders; a full playthrough shows chips, progress and the final tallies", async () => {
  const r = await run("game");
  noErrors(r);
  const d = r.doc;
  const n = site.game.length;
  assert.equal(n, 40);
  assert.ok(d.getElementById("stage").querySelector("svg"));
  assert.ok(d.getElementById("btn-up") && d.getElementById("btn-down"));
  assert.equal(d.getElementById("tallies").children.length, 3);
  assert.deepEqual(d.getElementById("tallies").children.map((c) => c.classes[0]), ["you", "kronos", "coin"]);
  for (let i = 0; i < n; i++) {
    d.getElementById("btn-up").click();
    assert.ok(d.getElementById("stage").querySelector(".chip"), "revealed pair chip");
    assert.equal(d.getElementById("progressbar").getAttribute("aria-valuenow"), String(i + 1));
    assert.ok(d.getElementById("progressbar").firstElementChild.style.width.endsWith("%"));
    d.getElementById("btn-next").click();
  }
  assert.match(d.getElementById("stage").textContent, /Final tallies/);
  assert.equal(r.errors.length, 0);
});

test("method page: TOC, sections, hash tables and the recorded deviations as lists", async () => {
  const r = await run("method");
  noErrors(r);
  const d = r.doc;
  assert.ok(d.getElementById("toc").querySelectorAll("li").length >= 8);
  assert.ok(d.querySelectorAll(".longform table").length >= 3);
  const devs = d.querySelectorAll(".callout.deviation");
  assert.equal(devs.length, site.deviations.length);
  assert.ok(devs.some((x) => x.querySelectorAll("ul li").length === 6));
  assert.ok(d.getElementById("recorded-deviations"));
  assert.equal(d.querySelector(".preamble").textContent, site.preamble);
});

test("limits page: TOC, labelled callouts, lead sentence and the date note", async () => {
  const r = await run("limits");
  noErrors(r);
  const d = r.doc;
  assert.ok(d.getElementById("toc").querySelectorAll("li").length >= 3);
  const lim = d.getElementById("limits-list").querySelectorAll("li.callout.limit");
  assert.equal(lim.length, site.limits.length);
  lim.forEach((li) => assert.equal(li.firstChild.classes.includes("label"), true));
  assert.equal(d.getElementById("disclosures-list").querySelectorAll("li.callout.disclosure").length, site.disclosures.length);
  assert.ok(d.getElementById("limits-list").textContent.includes("as of 5 Nov 2026"));
  assert.equal(d.querySelector(".preamble").textContent, site.preamble);
});
