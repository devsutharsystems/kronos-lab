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
                         "featured", "game", "selection", "disclosures", "limits", "method"}
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
    rs = site["running_score"]
    n = len(rs["n"])
    assert 0 < n <= 300 and all(len(rs[k]) == n for k in ("kronos", "band_lo", "band_median", "band_hi"))
    assert all(lo <= m <= hi for lo, m, hi in zip(rs["band_lo"], rs["band_median"], rs["band_hi"]))
    rows = site["results_table"]
    assert sum(r["primary"] for r in rows) == 1 and len(rows) == 7 * 3
    assert [r for r in rows if r["primary"]][0]["pair"] == "ALL" and [r for r in rows if r["primary"]][0]["horizon"] == 24
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
        assert json.loads((ROOT / "site" / "data" / "site.json").read_text())["synthetic"] is False


def test_site_data_is_gitignored():
    assert "site/data/" in (ROOT / ".gitignore").read_text().split()


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
    assert not any(x["text"].lstrip().startswith("|") for v in m.values() for x in v)        # table rows dropped (a "|" inside the seed formula is fine)
    assert any("|" in x["text"] for v in m.values() for x in v)                              # and the seed formula text is kept


# e. size -----------------------------------------------------------------------------------------------------
def test_site_size_excluding_data_is_small():
    total = sum(f.stat().st_size for f in SITE.rglob("*") if f.is_file() and "data" not in f.relative_to(SITE).parts[:1])
    assert total <= 300 * 1024, total


# f. node tests ---------------------------------------------------------------------------------------------
def test_game_logic_node_tests():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "--test", str(ROOT / "tests" / "node" / "game.test.js")], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-1000:]
