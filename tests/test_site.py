"""Static-site tests. site.json is built from SYNTHETIC data only; no test opens results/runs, data/processed or data/raw."""
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

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
    r = subprocess.run([node, "--test", str(ROOT / "tests" / "node" / "game.test.js"), str(ROOT / "tests" / "node" / "svg.test.js"), str(ROOT / "tests" / "node" / "notes.test.js"), str(ROOT / "tests" / "node" / "plot.test.js")], capture_output=True, text=True, cwd=ROOT)
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
