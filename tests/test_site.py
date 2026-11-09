"""Static-site tests. site.json is built from SYNTHETIC data only; no test opens results/runs, data/processed or data/raw."""
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import colour as C  # noqa: E402  (tests/colour.py)

from kronos_lab import analysis as A

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
PAGES = ["index.html", "evidence.html", "game.html", "method.html", "limits.html"]
ATTRIBUTION = "Data: Binance Vision (data.binance.vision), CC BY-NC-SA 4.0; not affiliated with or endorsed by Binance."


def load_builder():
    spec = importlib.util.spec_from_file_location("build_site_data", ROOT / "scripts" / "build_site_data.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def builder():
    return load_builder()


def build(builder, seed=1):
    inp = A.synthetic_inputs(seed=seed, skill=0.1, rho=0.5, n_days=80)          # SYNTHETIC
    res = A.run_analysis(inp, B=300)
    return builder.build_site_json(inp, res, True, (ROOT / "PREREGISTRATION.md").read_text(), {"seed": seed})


@pytest.fixture(scope="module")
def site(builder):
    return build(builder)


# a. schema -------------------------------------------------------------------------------------------
def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def test_site_json_matches_schema(site):
    assert set(site) == {"synthetic", "synthetic_meta", "protocol", "headline", "primary", "power", "results_table", "running_score",
                         "featured", "game", "selection", "disclosures", "limits", "method", "preamble", "deviations", "limit_notes", "power_at_actual_n"}
    assert site["synthetic"] is True and isinstance(site["synthetic_meta"], dict)
    p = site["protocol"]
    assert p["lookback"] == 512 and p["samples"] == 11 and p["pred_len"] == 24 and p["days"] == 396
    assert p["horizons"] == [1, 4, 24] and len(p["pairs"]) == 6 and p["context_bars_shown"] == 72
    assert p["window_start"] == "2025-10-01" and p["window_end"] == "2026-10-31"
    h = site["headline"]
    assert isinstance(h["headline"], str) and isinstance(h["underpowered"], bool) and isinstance(h["n"], int)
    assert h["decision_h1"] in {"edge detected vs coin flip", "worse than a coin flip", "no detectable edge"}
    assert h["decision_h2"] in {"beats always-up", "worse than always-up", "no detectable edge"}
    assert len(site["power"]["rows"]) == 3 and all(is_num(r["min_detectable_edge_pp"]) for r in site["power"]["rows"])
    # featured: 12 origins, 11 x 24 sample paths
    assert len(site["featured"]) == 12 == p["featured_origins"]
    for f in site["featured"]:
        assert set(f) == {"pair", "date", "last_close", "samples", "mean", "actual", "signal_24", "label_24"}
        assert len(f["samples"]) == 11 and all(len(s) == 24 and all(is_num(v) for v in s) for s in f["samples"])
        assert len(f["mean"]) == 24 and len(f["actual"]) == 24
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", f["date"]) and f["signal_24"] in (-1, 1) and f["label_24"] in (-1, 1)
    # game: 40 windows, 72 context bars of OHLC
    assert len(site["game"]) == 40 == p["game_windows"]
    for g in site["game"]:
        assert set(g) == {"context", "kronos_call", "coin_flip", "actual", "reveal"}
        assert len(g["context"]) == 72 and all(len(b) == 4 and all(is_num(v) for v in b) for b in g["context"])
        assert len(g["actual"]) == 24 and g["kronos_call"] in (-1, 1) and g["coin_flip"] in (-1, 1)
        assert set(g["reveal"]) == {"pair", "date"}
    rs = site["running_score"]                        # SYNTHETIC build only; real mode has none (see test_real_mode_shape)
    n = len(rs["n"])
    assert 0 < n <= 300 and all(len(rs[k]) == n for k in ("kronos", "band_lo", "band_median", "band_hi"))
    assert all(lo <= m <= hi for lo, m, hi in zip(rs["band_lo"], rs["band_median"], rs["band_hi"]))
    rt = site["results_table"]
    assert [r["horizon"] for r in rt["all_pairs"]] == [1, 4, 24] and sum(r["primary"] for r in rt["all_pairs"]) == 1
    assert [r for r in rt["all_pairs"] if r["primary"]][0]["horizon"] == 24
    assert [r["pair"] for r in rt["by_pair_h24"]] == p["pairs"]
    assert set(site["method"]) == {str(k) for k in range(3, 11)} and all(site["method"][k] for k in site["method"])
    assert site["limits"] and all(isinstance(x, str) for x in site["limits"]) and site["disclosures"]
    assert site["selection"]["featured"]["seed"] == 20261108 and site["selection"]["game"]["seed"] == 20261109
    assert site["selection"]["coin_flips"]["seed"] == 20261110
    assert len(json.dumps(site, separators=(",", ":")).encode()) <= 2 * 1024 * 1024


# b. static checks -------------------------------------------------------------------------------------
def site_text_files():
    return [SITE / p for p in PAGES] + sorted((SITE / "js").glob("*.js"))


def prereg_url():
    m = re.search(r'const PREREG_URL = "([^"]+)"', (SITE / "js" / "config.js").read_text())
    assert m, "PREREG_URL constant missing"
    return m.group(1)


SVG_NS = "http://www.w3.org/2000/svg"   # XML namespace identifier required by createElementNS; never fetched


def test_no_off_site_urls_and_no_external_includes():
    allowed = {prereg_url(), SVG_NS}
    for f in site_text_files():
        for url in re.findall(r"https?://[^\s\"'<>)]+", f.read_text()):
            assert url in allowed, f"{f.name}: unexpected URL {url}"
    for f in [SITE / p for p in PAGES]:
        html = f.read_text()
        for src in re.findall(r"<script[^>]*\ssrc=\"([^\"]+)\"", html) + re.findall(r"<link[^>]*\shref=\"([^\"]+)\"", html):
            assert not re.match(r"(https?:)?//", src), f"{f.name}: off-site include {src}"
    css = (SITE / "style.css").read_text()
    assert "url(" not in css and "@import" not in css and "@font-face" not in css
    assert re.fullmatch(r"https://github\.com/[^/]+/[^/]+/blob/[0-9a-f]{40}/PREREGISTRATION\.md", prereg_url())
    assert fetch_calls_only_site_json()


def fetch_calls_only_site_json():
    for f in sorted((SITE / "js").glob("*.js")):
        for call in re.findall(r"fetch\(([^,)]+)", f.read_text()):
            assert call.strip() == '"data/site.json"', f"{f.name}: fetch({call})"
    assert not re.findall(r"XMLHttpRequest|WebSocket|sendBeacon|EventSource|import\(", "".join(f.read_text() for f in site_text_files()))
    return True


def test_every_page_has_disclaimer_attribution_and_prereg_link():
    for p in PAGES:
        html = (SITE / p).read_text()
        assert "Not financial advice" in html, p
        assert ATTRIBUTION in html, p
        assert "data-prereg" in html, p


def test_no_typed_percentages_p_values_or_counts():
    for f in site_text_files():
        t = f.read_text()
        assert not re.search(r"\d+(\.\d+)?\s?%", t), f"{f.name}: typed percentage"
        assert not re.search(r"p\s?[<=]\s?0\.", t), f"{f.name}: typed p-value"
    for p in PAGES:                                   # visible HTML text carries no digits at all (besides the attribution line)
        html = (SITE / p).read_text().replace(ATTRIBUTION, "")
        body = re.sub(r"<head>.*?</head>", "", html, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", body)
        assert not re.search(r"\d", text), f"{p}: digit in visible text: {re.findall(r'.{0,20}\d.{0,20}', text)[:3]}"


# c. synthetic flag --------------------------------------------------------------------------------------
def test_synthetic_banner_hook_on_every_page_and_title_prefix_in_code():
    common = (SITE / "js" / "common.js").read_text()
    assert "SYNTHETIC DEMO DATA, NOT KRONOS RESULTS" in common and '"[SYNTHETIC] "' in common
    assert "site.synthetic" in common
    for p in PAGES:
        html = (SITE / p).read_text()
        assert 'id="synthetic-banner"' in html and 'src="js/common.js"' in html, p
        assert "<title>" in html


def test_tracked_site_json_must_not_be_synthetic():
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "site/data/site.json"], capture_output=True, text=True).stdout.strip()
    if tracked:
        raw = (ROOT / "site" / "data" / "site.json").read_bytes()
        assert json.loads(raw)["synthetic"] is False and len(raw) <= 2 * 1024 * 1024


def test_only_site_json_is_trackable_under_site_data():
    tokens = (ROOT / ".gitignore").read_text().split()
    assert "site/data/*" in tokens and "!site/data/site.json" in tokens
    assert {"!site/data/results_summary.csv", "!site/data/data_dictionary.csv", "!site/data/results.json"} <= set(tokens)
    assert "results/synthetic_demo/" in tokens
    ls = subprocess.run(["git", "-C", str(ROOT), "ls-files", "site/data"], capture_output=True, text=True).stdout.split()
    assert set(ls) <= {"site/data/site.json", "site/data/results_summary.csv", "site/data/data_dictionary.csv", "site/data/results.json"}


def test_tracked_site_files_contain_no_local_paths():
    files = subprocess.run(["git", "-C", str(ROOT), "ls-files", "site"], capture_output=True, text=True).stdout.split()
    assert files
    for f in files:
        t = (ROOT / f).read_text(errors="replace")
        for bad in ("/Users/", "/private/", "/var/folders", "/home/", "C:\\Users"):
            assert bad not in t, f"{f} contains {bad}"


def test_real_mode_shape_has_no_running_score_and_is_exact(builder):
    # SYNTHETIC inputs built with synthetic=False only to exercise the real-mode branch in memory
    inp = A.synthetic_inputs(seed=1, skill=0.1, rho=0.5, n_days=80)
    res = json.loads(json.dumps(A.clean(A.run_analysis(inp, B=300))))
    s = builder.build_site_json(inp, res, False, (ROOT / "PREREGISTRATION.md").read_text(), None)
    assert s["synthetic"] is False and s["running_score"] is None and s["synthetic_meta"] is None
    for k in ("n", "k_correct", "n_days", "accuracy", "ci_accuracy", "always_up_accuracy", "accuracy_diff", "ci_diff", "p_h1_raw", "p_h2_raw",
              "p_h1_holm", "p_h2_holm", "kronos_down_calls_D", "exclusions_h24"):
        assert s["primary"][k] == res["primary"][k], k                       # exact, not rounded
    assert s["power"]["rows"] == res["power"]["rows"]


def test_real_site_json_equals_results_json_exactly():
    # reads only two committed files: results/final/results.json and site/data/site.json
    res = json.loads((ROOT / "results" / "final" / "results.json").read_text())
    site = json.loads((ROOT / "site" / "data" / "site.json").read_text())
    assert site["synthetic"] is False and res["data_source"] == "REAL"
    P, sp = res["primary"], site["primary"]
    for k in ("n", "k_correct", "n_days", "accuracy", "ci_accuracy", "always_up_accuracy", "accuracy_diff", "ci_diff", "p_h1_raw", "p_h2_raw",
              "p_h1_holm", "p_h2_holm", "kronos_down_calls_D", "discordant_kronos_right_alwaysup_wrong", "discordant_kronos_wrong_alwaysup_right",
              "exclusions_h24"):
        assert sp[k] == P[k], k
    assert sp["exclusions_h24"] == res["exclusions"]["h24"] == P["exclusions_h24"]
    h = site["headline"]
    assert h["decision_h1"] == P["decision_h1"] and h["decision_h2"] == P["decision_h2"] and h["headline"] == P["headline"]
    assert h["underpowered"] == P["underpowered"] and h["n"] == P["n"] and h["D"] == P["kronos_down_calls_D"]
    assert h["largest_edge_not_ruled_out_h1"] == P["largest_edge_not_ruled_out_h1"]
    assert h["largest_gain_vs_always_up_not_ruled_out_h2"] == P["largest_gain_vs_always_up_not_ruled_out_h2"]
    assert site["power"]["rows"] == res["power"]["rows"] and site["power"]["D"] == res["power"]["D"]
    assert site["power"]["min_detectable_shift_down_calls_pp"] == res["power"]["min_detectable_shift_down_calls_pp"]
    assert site["running_score"] is None
    rt = {r["horizon"]: r for r in site["results_table"]["all_pairs"]}
    assert rt[24]["kronos_accuracy"] == P["accuracy"]
    for hz in (1, 4):
        assert rt[hz]["kronos_accuracy"] == res["exploratory_accuracy_by_horizon"][f"h{hz}"]["accuracy"]
    for hz in (1, 4, 24):
        assert rt[hz]["persistence_accuracy"] == res["exploratory_persistence_baseline"][f"h{hz}"]["accuracy"]
    for r in site["results_table"]["by_pair_h24"]:
        assert r["kronos_accuracy"] == res["exploratory_by_pair"][r["pair"]]["accuracy"] and r["n"] == res["exploratory_by_pair"][r["pair"]]["n"]


def test_real_deviation_entry_and_limits_text_are_in_site_json():
    site = json.loads((ROOT / "site" / "data" / "site.json").read_text())
    assert any("run closed after the cutoff" in d["title"] and d["date"].startswith("2026-11-07") for d in site["deviations"])
    assert site["preamble"].startswith("These statements were true when the pre-registration was committed (")
    assert site["limit_notes"][0]["text"].endswith("as of 5 Nov 2026.")


# d. game windows --------------------------------------------------------------------------------------------
def walk_keys(o, path=()):
    if isinstance(o, dict):
        for k, v in o.items():
            yield path + (k,)
            yield from walk_keys(v, path + (k,))
    elif isinstance(o, list):
        for v in o:
            yield from walk_keys(v, path)


def test_game_hides_pair_and_date_outside_reveal_and_normalises_context(site):
    for g in site["game"]:
        for key_path in walk_keys({k: v for k, v in g.items() if k != "reveal"}):
            assert key_path[-1] not in ("pair", "date", "last_close")
        assert g["context"][-1][3] == 100
        flat = [v for bar in g["context"] for v in bar] + g["actual"]
        assert all(0 < v < 1000 for v in flat)            # relative levels only, never absolute prices
        assert all(b[1] >= max(b[0], b[3]) * 0.9999 and b[2] <= min(b[0], b[3]) * 1.0001 for b in g["context"])   # OHLC order, 4-sig rounding


def test_selection_is_deterministic_across_builds(builder, site):
    again = build(builder)
    h = lambda o: hashlib.sha256(json.dumps(o, sort_keys=True).encode()).hexdigest()
    assert h(site) == h(again)
    other = build(builder, seed=2)
    assert h(other["featured"]) != h(site["featured"])        # different data, different draw
    # selection never depends on outcome: the pool only needs complete data; draws come from the stated seeds
    assert site["selection"]["pool"].startswith("h=24 analysis set")


def test_site_data_builder_refuses_forbidden_output_dirs(builder, tmp_path, monkeypatch):
    # the builder's ROOT is pointed at a temporary tree, so the real results/ directories are never even stat-ed
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    assert builder.main(["--synthetic", "--out", str(tmp_path / "results" / "final")]) == 3
    assert builder.main(["--synthetic", "--out", str(tmp_path / "results" / "runs" / "x")]) == 3
    assert not (tmp_path / "results").exists()


def test_prereg_sections_parse():
    m = load_builder().prereg_sections((ROOT / "PREREGISTRATION.md").read_text())
    assert m[11] and m[2] and m[7] and any(x["level"] == 1 for x in m[7])
    assert not any(x["text"].lstrip().startswith("|") for v in m.values() for x in v)        # table rows become table items (a "|" inside the seed formula is fine)
    assert any("|" in x["text"] for v in m.values() for x in v)                              # and the seed formula text is kept


def test_every_pipe_table_in_the_preregistration_is_rendered(site, builder):
    text = (ROOT / "PREREGISTRATION.md").read_text()
    tables = builder.pipe_tables(text)
    assert len(tables) >= 3
    rendered = [x["table"] for k in sorted(site["method"], key=int) for x in site["method"][k] if x["level"] == -2]
    assert len(rendered) == len(tables)
    for want, got in zip(tables, rendered):                       # same order, same cells
        assert got["header"] == want["header"] and got["rows"] == want["rows"]
    # the hash cells really are in the page data
    flat = " ".join(c for t in rendered for r in t["rows"] for c in r)
    for h in re.findall(r"[0-9a-f]{64}", text.replace("`", "")):
        if f"| {h}" in text.replace("`", "") or f"{h} |" in text.replace("`", ""):
            assert h in flat


def test_power_rows_equal_analysis_power_table(site):
    want = A.power_table()["rows"]
    got = site["power"]["rows"]
    assert len(got) == len(want) == 3
    for g, w in zip(got, want):
        assert g["n"] == w["n"] and g["min_detectable_edge_pp"] == w["min_detectable_edge_pp"] and g["accuracy_needed"] == w["accuracy_needed"]


def test_preamble_deviations_and_issue_note(site, builder):
    assert site["preamble"].startswith("These statements were true when the pre-registration was committed (")
    assert site["preamble"].endswith("They are quoted unchanged and describe the state before the run, not now.")
    devs = builder.deviations((ROOT / "DEVIATIONS.md").read_text())
    assert site["deviations"] == devs and len(devs) >= 1 and all(d["date"] and d["text"] for d in devs)
    assert "sixth run-critical file" in " ".join(x["text"] for x in site["method"]["5"])      # the deviation sits after this section
    assert any("issue #265" in t for t in site["limits"])                                    # quote untouched
    assert site["limit_notes"][0]["text"].endswith("as of 5 Nov 2026.")


def test_deviations_parser_handles_several_entries(builder):
    t = "# Deviations\n\n## 2026-11-06 15:40:59 +0530: first\n\nBody one.\n\n## 2026-11-09 10:00:00 +0530: second\n\nBody two.\n"
    d = builder.deviations(t)
    assert [x["title"] for x in d] == ["first", "second"] and d[1]["date"] == "2026-11-09 10:00:00 +0530" and d[1]["text"] == "Body two."


def test_phase6_layout_rules_in_css_and_pages():
    css = (SITE / "style.css").read_text()
    banner = re.search(r"#synthetic-banner \{[^}]*\}", css).group(0)
    assert "position: sticky" in banner and "position: fixed" not in css and "has-banner" not in css      # real height, never assumed
    assert "table.wide { min-width: 36rem; }" in css and "white-space: nowrap" in css and "position: sticky; left: 0" in css
    assert ".mono" in css and "overflow-wrap: anywhere" in css.split(".mono")[1]
    for p in ("limits.html", "method.html"):
        assert 'class="card preamble"' in (SITE / p).read_text()
    assert "text.js" in (SITE / "evidence.html").read_text() and "notes.js" in (SITE / "index.html").read_text()
    assert 'id: "recorded-deviations"' in (SITE / "js" / "text.js").read_text()
    assert "Swipe sideways to see all columns" in (SITE / "js" / "text.js").read_text()
    ev = (SITE / "js" / "evidence.js").read_text()
    assert '"n/a"' not in ev and "clamp" not in ev


# e. size -----------------------------------------------------------------------------------------------------
def test_site_size_excluding_data_is_small():
    total = sum(f.stat().st_size for f in SITE.rglob("*") if f.is_file() and "data" not in f.relative_to(SITE).parts[:1])
    assert total <= 300 * 1024, total


# f. node tests ---------------------------------------------------------------------------------------------
def test_game_logic_node_tests():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "--test", str(ROOT / "tests" / "node" / "game.test.js"), str(ROOT / "tests" / "node" / "svg.test.js"), str(ROOT / "tests" / "node" / "notes.test.js"), str(ROOT / "tests" / "node" / "plot.test.js"), str(ROOT / "tests" / "node" / "chips.test.js"), str(ROOT / "tests" / "node" / "pages.test.js"), str(ROOT / "tests" / "node" / "subpath.test.js")], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-1000:]


# ---------------------------------------------------------------- Phase 7d
def js_strings(text: str):
    return [m.group(1) for m in re.finditer(r'"((?:[^"\\\n]|\\.)*)"', text)]


def test_no_win_beat_or_edge_detected_wording_in_html_or_js_strings():
    bad = re.compile(r"\b(win|beats?|edge detected)\b", re.I)
    for p in PAGES:
        html = (SITE / p).read_text()
        text = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html, flags=re.S)
        assert not bad.search(text), f"{p}: {bad.search(text).group(0)}"
    for f in sorted((SITE / "js").glob("*.js")):
        for lit in js_strings(f.read_text()):
            assert not bad.search(lit), f"{f.name}: {lit!r}"


def test_plot_uses_neutral_colours_only():
    css = (SITE / "style.css").read_text()
    for rule in re.findall(r"svg \.(?:ci-[a-z]+|plot-[a-z]+)[^{]*\{[^}]*\}", css):
        assert not re.search(r"#[0-9a-fA-F]{3,6}|--ok|--warn|--banner|red|green|--accent|--c-(kronos|actual)", rule), rule
    plot = (SITE / "js" / "plot.js").read_text()
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b|\bred\b|\bgreen\b|fill:|stroke:", plot)
    assert not re.search("[\U0001F300-\U0001FAFF\u2600-\u27BF]", "".join(f.read_text() for f in site_text_files()))   # no emoji


def test_plot_numbers_are_all_in_site_json(site):
    p = site["primary"]
    for k in ("accuracy", "accuracy_diff"):
        assert is_num(p[k])
    for k in ("ci_accuracy", "ci_diff", "naive_binomial_ci95"):
        assert len(p[k]) == 2 and all(is_num(v) for v in p[k]) and p[k][0] <= p[k][1], k
    assert isinstance(site["protocol"]["ci_level"], int) and site["protocol"]["ci_level"] == 95
    assert site["power_at_actual_n"]["rows"][0]["n"] == p["n"]


def test_real_site_downloads_are_byte_identical_copies():
    for name, src in (("results_summary.csv", "results/export/results_summary.csv"), ("data_dictionary.csv", "results/export/data_dictionary.csv"),
                      ("results.json", "results/final/results.json")):
        assert (ROOT / "site" / "data" / name).read_bytes() == (ROOT / src).read_bytes(), name
    ev = (SITE / "js" / "evidence.js").read_text()
    for href in ("data/results_summary.csv", "data/results.json", "data/data_dictionary.csv"):
        assert f'href: "{href}"' in ev


def _lum(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_text_contrast_is_at_least_4_5_in_light_and_dark():
    css = (SITE / "style.css").read_text()
    light = dict(re.findall(r"--([a-z-]+):\s*(#[0-9a-fA-F]{6})", re.search(r":root \{(.*?)\}", css, re.S).group(1)))
    dark = dict(re.findall(r"--([a-z-]+):\s*(#[0-9a-fA-F]{6})", re.search(r"prefers-color-scheme: dark\) \{\s*:root \{(.*?)\}", css, re.S).group(1)))
    for name, t in (("light", light), ("dark", {**light, **dark})):
        pairs = [("fg", "bg"), ("fg", "card"), ("fg", "zebra"), ("muted", "bg"), ("muted", "card"), ("muted", "zebra"), ("accent", "bg"),
                 ("accent", "card"), ("warn", "bg"), ("banner-fg", "banner-bg")]
        for fg, bg in pairs:
            assert _ratio(t[fg], t[bg]) >= 4.5, f"{name}: {fg} on {bg} = {_ratio(t[fg], t[bg]):.2f}"


def test_css_has_phase7d_layout_rules():
    css = (SITE / "style.css").read_text()
    assert "max-width: 72rem" in css and "48rem" in css and ".hero" in css and "grid-template-columns" in css
    assert "prefers-reduced-motion" in css and "@media print" in css and "tabular-nums" in css
    assert "nth-child(even)" in css and "thead th { position: sticky" in css
    assert ".badge.primary" in css and "dashed" in css.split(".badge {")[1].split("}")[0]     # shapes differ, not only colour


# ---------------------------------------------------------------- Phase 7e: palette, contrast, structure
PAIR_TOKENS = ["pair-btc", "pair-eth", "pair-sol", "pair-xrp", "pair-bnb", "pair-doge"]


def css_tokens():
    css = (SITE / "style.css").read_text()
    parse = lambda b: {k: v.strip() for k, v in re.findall(r"--([a-z0-9-]+):\s*([^;]+);", b)}
    light = parse(re.search(r":root \{(.*?)\}", css, re.S).group(1))
    dark = {**light, **parse(re.search(r"prefers-color-scheme: dark\) \{\s*:root \{(.*?)\}", css, re.S).group(1))}
    return {"light": light, "dark": dark}


def pct(v):
    return float(v.rstrip("%"))


def glass(t):
    m = re.fullmatch(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", t["glass-bg"])
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))), float(m.group(4))


def test_pair_hues_are_pairwise_distinct_ciede2000_at_least_15():
    for theme, t in css_tokens().items():
        d = C.distance_table({k: t[k] for k in PAIR_TOKENS})
        assert len(d) == 15
        worst = min(d.items(), key=lambda kv: kv[1])
        assert worst[1] >= 15, f"{theme}: {worst[0]} = {worst[1]:.1f}"


def test_identity_hues_avoid_green_and_red_and_are_not_outcome_colours():
    css = (SITE / "style.css").read_text()
    for theme, t in css_tokens().items():
        for k in PAIR_TOKENS + ["h1", "h2", "you", "kronos", "coin", "mesh-1", "mesh-2", "mesh-3", "mesh-4"]:
            hue = C.hue_degrees(t[k])
            assert not (70 <= hue <= 170), f"{theme} {k} {t[k]} is green ({hue:.0f})"
            assert not (hue >= 340 or hue <= 20), f"{theme} {k} {t[k]} is red/red-orange ({hue:.0f})"
    assert not any(k in css_tokens()["light"] for k in ("ok", "c-up", "c-down", "c-actual"))
    for sel, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S)):
        sel = sel.strip()
        if "var(--warn)" in body:                                   # warning red is for warnings and the synthetic banner only
            assert sel.startswith(".warn"), sel
        if "var(--banner" in body:
            assert sel.startswith("#synthetic-banner"), sel
        if "var(--pair-" in body and not sel.startswith(":root"):
            assert sel.startswith(".pair-"), sel                    # pair hues are consumed only through .pair-* classes
        if any(f"var(--{k})" in body for k in ("you", "kronos", "coin")):
            assert sel.startswith(".tallies"), sel                  # scoreboard hues are used only on the three scoreboard cards
        if "var(--h1)" in body or "var(--h2)" in body:
            assert re.match(r"(\.verdict|\.tag|svg \.ci-main)", sel), sel


def test_candles_use_neutral_colours_only():
    css = (SITE / "style.css").read_text()
    for cls in ("candle-up", "candle-down", "wick"):
        rule = re.search(r"svg \." + cls + r" \{[^}]*\}", css).group(0)
        assert not re.search(r"#[0-9a-fA-F]{3,6}|--pair|--h1|--h2|--accent|--warn", rule), rule
    assert "svg .candle-up { fill: var(--bg)" in css and "svg .candle-down { fill: var(--fg)" in css       # hollow above open, filled below open
    ui = (SITE / "js" / "game-ui.js").read_text()
    assert 'cl >= o ? "candle-up" : "candle-down"' in ui


def test_new_tokens_meet_contrast_in_light_and_dark():
    for theme, t in css_tokens().items():
        bg, fg, muted = t["bg"], t["fg"], t["muted"]
        # text on chips (hue tint over the page background)
        for k in PAIR_TOKENS:
            chip_bg = C.mix(t[k], bg, pct(t["chip-mix"]))
            assert C.cr_rgb(fg, chip_bg) >= 4.5, f"{theme} chip {k}"
            assert C.cr(t[k], bg) >= 3, f"{theme} {k} graphic on page"          # chip border / sampled paths
        # verdict cards: tinted glass over the page; tag text on the page background
        g, a = glass(t)
        base = C.over(g, a, bg)
        for k in ("h1", "h2"):
            vbg = C.mix(t[k], base, pct(t["tint-mix"]))
            assert C.cr_rgb(fg, vbg) >= 4.5 and C.cr_rgb(muted, vbg) >= 4.5, f"{theme} verdict {k}"
            assert C.cr(t[k], bg) >= 4.5, f"{theme} {k} tag text"
        # hero mesh: text against the worst point (every stop, every 50 % mix of two stops, and the page background), bare and under glass
        stops = [C.rgb(t[f"mesh-{i}"]) for i in (1, 2, 3, 4)]
        points = stops + [C.mix(x, y, 50) for i, x in enumerate(stops) for y in stops[i + 1:]] + [C.rgb(bg)]
        for pt in points:
            for txt in (fg, muted):
                assert C.cr_rgb(txt, pt) >= 4.5, f"{theme} text {txt} on mesh {C.hexs(pt)}"
                assert C.cr_rgb(txt, C.over(g, a, C.hexs(pt))) >= 4.5, f"{theme} text on glass over {C.hexs(pt)}"
        # UI borders and graphics
        for k in ("fg", "muted", "accent", "h1", "h2"):
            assert C.cr(t[k], bg) >= 3, f"{theme} {k} graphic"
        # text on the surfaces that carry the callouts, statcards and sticky table headers
        for k in ("card", "zebra"):
            assert C.cr(fg, t[k]) >= 4.5 and C.cr(muted, t[k]) >= 4.5, f"{theme} {k}"
        # decorative table gridlines (--line) are not required to reach 3:1; they never carry meaning on their own
        assert C.cr(fg, t["bg"]) >= 7


def test_result_page_puts_the_decision_text_first_in_the_dom():
    html = (SITE / "index.html").read_text()
    main = html.split("<main>")[1]
    i = main.index('id="headline-text"')
    for later in ('id="verdicts"', 'id="interval-plot"', 'id="statcards"', 'id="power-table"'):
        assert main.index(later) > i, later
    before = re.sub(r"<svg.*?</svg>|<!--.*?-->", "", main[:main.rfind("<", 0, i)], flags=re.S)
    assert re.sub(r"<[^>]+>", " ", before).split() == ["What", "the", "test", "found"] and 'class="sr-only"' in before   # nothing visible earlier
    assert re.search(r'id="load-error"[^>]*hidden', before)
    js = (SITE / "js" / "index.js").read_text()
    assert js.count('getElementById("headline-text")') == 1 and 'getElementById("headline-text").textContent = site.headline.headline;' in js
    css = (SITE / "style.css").read_text()
    assert re.search(r"\.motif \{[^}]*position: absolute", css) and re.search(r"\.hero-band \{[^}]*padding: clamp\(", css)   # the motif takes no flow space
    assert 'class="motif"' in html and 'aria-hidden="true"' in html.split('class="motif"')[1].split(">")[0]


def test_decorative_motif_is_flat_or_alternating_and_symmetric():
    html = (SITE / "index.html").read_text()
    comment = [int(x) for x in re.search(r"motif closes: ([-\d ]+) \(", html).group(1).split()]
    candles = re.findall(r'<g data-close="(-?\d+)"><line[^>]*/><rect class="([a-z-]+)"', html)
    closes = [int(c) for c, _ in candles]
    assert closes == comment and len(closes) >= 7
    assert closes == closes[::-1]                                   # palindromic: symmetric about its start and end value
    assert closes[0] == closes[-1]                                  # no net trend
    opens = [closes[0]] + closes[:-1]
    for (c, cls), o in zip(candles, opens):
        assert cls == ("candle-up" if int(c) > o else "candle-down")
    ups = [b > a for a, b in zip(closes, closes[1:])]
    assert any(ups) and not all(ups)                                # alternates; never one rising run


def test_pair_chips_carry_text_and_every_pair_has_a_hue_class():
    chips = (SITE / "js" / "chips.js").read_text()
    for lab in ("BTC", "ETH", "SOL", "XRP", "BNB", "DOGE"):
        assert f'"{lab}"' in chips
    css = (SITE / "style.css").read_text()
    for cls in ("pair-btc", "pair-eth", "pair-sol", "pair-xrp", "pair-bnb", "pair-doge"):
        assert f".{cls} {{" in css
    assert "evidence.js" and "KL.chip(r.pair)" in (SITE / "js" / "evidence.js").read_text()


def test_motion_is_reduced_on_request_and_pages_have_no_external_fonts():
    css = (SITE / "style.css").read_text()
    for kw in ("animation", "transition"):
        assert kw in css
    assert "prefers-reduced-motion: reduce" in css and "animation: none !important" in css and "transition: none !important" in css
    assert "@font-face" not in css and "font-family" in css and "url(" not in css and "@import" not in css


# ---------------------------------------------------------------- Phase 7f
SCORE_TOKENS = ["you", "kronos", "coin"]


def test_scoreboard_hues_are_distinct_from_pairs_and_each_other():
    for theme, t in css_tokens().items():
        colours = {k: t[k] for k in PAIR_TOKENS + SCORE_TOKENS}
        d = C.distance_table(colours)
        assert len(d) == 36
        worst = min(d.items(), key=lambda kv: kv[1])
        assert worst[1] >= 15, f"{theme}: {worst[0]} = {worst[1]:.1f}"
        for k in SCORE_TOKENS:                                      # 10 degrees clear of the green and red guard ranges, and graphics contrast
            hue = C.hue_degrees(t[k])
            assert 30 <= hue <= 315 and not (70 <= hue <= 170), f"{theme} {k} hue {hue:.0f}"
            assert C.cr(t[k], t["bg"]) >= 3, f"{theme} {k}"
            tint = C.mix(t[k], t["card"], pct(t["tint-mix"]))
            assert C.cr_rgb(t["fg"], tint) >= 4.5, f"{theme} scoreboard text on {k}"


def test_no_content_is_hidden_by_default_in_css():
    css = re.sub(r"/\*.*?\*/", "", (SITE / "style.css").read_text(), flags=re.S)
    assert not re.search(r"opacity:\s*0\s*[;}!]", css), "opacity: 0 found (keyframes included)"
    assert "visibility: hidden" not in css and "visibility:hidden" not in css
    assert "IntersectionObserver" not in "".join(f.read_text() for f in site_text_files())
    for sel, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", css):
        if "max-height" in body and "max-height: none" not in body:
            assert sel.strip() in (".tablewrap",) and "overflow: auto" in body, sel          # only the scroll container may clip, and it scrolls
        if "display: none" in body:
            assert sel.strip().startswith(("#synthetic-banner[hidden]", ".warn[hidden]", ".toc", "nav, .row")) or "hidden" in sel, sel
    assert ".band {" in css and "transparent" not in css.split(".band {")[1].split("}")[0]     # section bands no longer fade out at the bottom


def test_script_lists_cover_every_global_each_page_script_uses():
    deps = {"common.js": ["config.js"], "text.js": ["common.js"], "index.js": ["common.js", "notes.js", "plot.js", "svg.js", "text.js"],
            "evidence.js": ["chips.js", "common.js", "svg.js", "text.js"], "game-ui.js": ["chips.js", "common.js", "game.js", "svg.js", "text.js"]}
    for page in PAGES:
        srcs = re.findall(r'<script[^>]*\ssrc="js/([^"]+)"', (SITE / page).read_text())
        for script, need in deps.items():
            if script in srcs:
                for n in need:
                    assert n in srcs and srcs.index(n) < srcs.index(script), f"{page}: {script} needs {n} loaded first"


def test_fan_strings_are_neutral_and_descriptive_only():
    t = (SITE / "js" / "text.js").read_text()
    block = t[t.index("  fan: {"):t.index("  verdict: {")]
    bad = re.compile(r"\b(correct|wrong|right|miss|win|beat)\b", re.I)
    assert "sentence:" in block
    for lit in js_strings(block):
        assert not bad.search(lit), lit
    ev = (SITE / "js" / "evidence.js").read_text()
    assert "correct" not in ev.split("fan chart")[1].split("running score")[0].lower()


def test_recorded_deviations_text_equals_deviations_md_modulo_whitespace_and_markers():
    site_json = json.loads((ROOT / "site" / "data" / "site.json").read_text())
    raw = (ROOT / "DEVIATIONS.md").read_text()
    sections = re.split(r"^## ", raw, flags=re.M)[1:]
    assert len(sections) == len(site_json["deviations"]) >= 2
    for sec, d in zip(sections, site_json["deviations"]):
        head, _, body = sec.partition("\n")
        assert d["date"] + ": " + d["title"] == head.strip()
        want = " ".join(re.sub(r"^\s*[-*] ", "", ln) for ln in body.splitlines() if ln.strip()).split()
        got = []
        for b in d["blocks"]:
            got += b["text"].split() if b["type"] == "p" else [w for it in b["items"] for w in it.split()]
        assert got == want, d["date"]
        assert " ".join(got) == d["text"]
    assert any(b["type"] == "ul" and len(b["items"]) == 6 for d in site_json["deviations"] for b in d["blocks"])


def test_serve_script_sends_no_store():
    import threading
    import urllib.request
    spec = importlib.util.spec_from_file_location("serve_site", ROOT / "scripts" / "serve_site.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    srv = m.make_server("127.0.0.1", 0)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        r = urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/index.html", timeout=5)
        assert r.status == 200 and "no-store" in r.headers["Cache-Control"]
    finally:
        srv.shutdown()
        srv.server_close()


# ---------------------------------------------------------------- Phase 10: the site must work under a sub-path (/kronos-lab/)
def test_no_root_absolute_urls_in_site_files():
    pat = re.compile(r"""(?:(?:href|src|action)=["']/(?!/)|fetch\(\s*["'`]/|url\(\s*["']?/(?!/)|=["']//|location\.(?:origin|pathname|host))""")
    for f in site_text_files() + [SITE / "style.css"]:
        for m in pat.finditer(f.read_text()):
            raise AssertionError(f"{f.name}: root-absolute URL or location use: {m.group(0)!r}")
    for f in sorted((SITE / "js").glob("*.js")):
        for lit in js_strings(f.read_text()):
            assert not re.match(r"^/(style\.css|js/|data/|index\.html)", lit), f"{f.name}: {lit!r}"
    for p in PAGES:
        html = (SITE / p).read_text()
        for ref in re.findall(r'(?:href|src)="([^"#]*)"', html):
            assert not ref.startswith("/"), f"{p}: {ref}"
