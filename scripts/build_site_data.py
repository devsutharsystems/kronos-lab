"""Build site/data/site.json for the static site.  stdlib + numpy (+ kronos_lab.analysis).

  python scripts/build_site_data.py --synthetic --out site/data       SYNTHETIC data (the Phase 4 generator)
  python scripts/build_site_data.py --root . --out site/data          REAL mode: uses analysis.load_real_inputs ONLY
                                                                      (refuses unless results/runs/DONE exists)
                                                                      and reads results/final/results.json

Selection rules (fixed by seed, never by outcome) are stated inside site.json.
Numbers are rounded to 4 significant digits. Total output must stay <= 2 MB.
"""
import argparse
import json
import re
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # needed under `python -I`

from kronos_lab import analysis as A  # noqa: E402
from kronos_lab import data as D  # noqa: E402

FEATURED_N, FEATURED_SEED = 12, 20261108
GAME_N, GAME_SEED = 40, 20261109
COIN_SEED = 20261110
MAX_POINTS = 300
MAX_BYTES = 2 * 1024 * 1024
HORIZON = 24


def r4(o):
    """Round every float to 4 significant digits; leave ints/bools/str alone."""
    if isinstance(o, dict):
        return {k: r4(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [r4(v) for v in o]
    if isinstance(o, np.ndarray):
        return r4(o.tolist())
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return float(f"{f:.4g}") if np.isfinite(f) else None
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def day_str(d: int) -> str:
    return (A.WINDOW_START + timedelta(days=int(d))).isoformat()


# ---------------------------------------------------------------- text taken from PREREGISTRATION.md
def prereg_sections(text: str) -> dict:
    """{section number: [ {text, level} ]} where level -1 = paragraph, 0 = bullet, 1 = sub-bullet. Tables dropped."""
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^## (\d+)\.", line)
        if m:
            cur = int(m.group(1)); out[cur] = []; continue
        if cur is None or not line.strip() or line.lstrip().startswith("|"):
            continue
        b = re.match(r"^(\s*)- (.*)$", line)
        if b:
            level, body = (1 if len(b.group(1)) >= 2 else 0), b.group(2)
        else:
            level, body = -1, line.strip()
        body = body.replace("`", "").replace("**", "")
        out[cur].append({"text": body, "level": level})
    return out


# ---------------------------------------------------------------- site.json
def results_table(inp, derived) -> list:
    rows = []
    pairs = [p for p in A.PAIRS_DEFAULT if p in set(inp.pair.tolist())] or sorted(set(inp.pair.tolist()))
    for pair in pairs + ["ALL"]:
        sel = np.ones(len(inp), bool) if pair == "ALL" else (inp.pair == pair)
        for j, h in enumerate(A.HORIZONS):
            d = derived[h]
            m = d["use"] & sel
            n = int(m.sum())
            acc = float((d["label"][m] == d["signal"][m]).mean()) if n else None
            with np.errstate(invalid="ignore"):
                psig = np.sign(inp.last_close - inp.ctx_tail[:, -1 - h])
            pm = d["valid"] & (d["label"] != 0) & (psig != 0) & sel
            pacc = float((d["label"][pm] == psig[pm]).mean()) if pm.any() else None
            rows.append({"pair": pair, "horizon": h, "n": n, "kronos_accuracy": acc, "persistence_accuracy": pacc,
                         "primary": bool(pair == "ALL" and h == HORIZON)})
    return rows


def running_score(inp, derived, res) -> dict:
    d = derived[HORIZON]
    idx = np.nonzero(d["use"])[0]
    pair_rank = {p: i for i, p in enumerate(A.PAIRS_DEFAULT)}
    order = sorted(idx, key=lambda i: (int(inp.day[i]), pair_rank.get(inp.pair[i], 99), str(inp.pair[i])))
    correct = (d["label"][order] == d["signal"][order]).astype(float)
    N = len(order)
    if N == 0:
        return {"n": [], "kronos": [], "band_lo": [], "band_median": [], "band_hi": [], "order": "forecast day, then pair"}
    cum = np.cumsum(correct) / np.arange(1, N + 1)
    pts = np.unique(np.linspace(0, N - 1, min(MAX_POINTS, N)).round().astype(int))
    band = A.coin_flip_band(N)
    return {"n": (pts + 1).tolist(), "kronos": cum[pts], "band_lo": band["lo_2_5"][pts], "band_median": band["median"][pts],
            "band_hi": band["hi_97_5"][pts], "order": "forecast day, then pair",
            "band": f"{band['n_paths']} simulated fair-coin paths, seed {band['seed']}; 2.5 / 50 / 97.5 percentiles; illustration only"}


def pick(rng_seed: int, pool: np.ndarray, k: int) -> np.ndarray:
    k = min(k, len(pool))
    return np.random.default_rng(rng_seed).choice(pool, size=k, replace=False)


def build_site_json(inp, res, synthetic: bool, prereg_text: str, meta: dict | None = None) -> dict:
    assert inp.path is not None and inp.ctx_ohlc is not None, "inputs lack path / ctx_ohlc"
    d = A.derive(inp)
    d24 = d[HORIZON]
    avail = np.isfinite(inp.path).all(axis=1) & np.isfinite(inp.ctx_ohlc).all(axis=(1, 2))   # data availability only
    pool = np.nonzero(d24["use"] & avail)[0]
    feat_idx = pick(FEATURED_SEED, pool, FEATURED_N)
    game_idx = pick(GAME_SEED, pool, GAME_N)
    coins = np.random.default_rng(COIN_SEED).choice([-1, 1], size=len(game_idx))

    featured = []
    for i in feat_idx:
        last = float(inp.last_close[i])
        pct = lambda a: (np.asarray(a) / last - 1.0) * 100.0
        samples = pct(inp.closes[i])
        featured.append({"pair": str(inp.pair[i]), "date": day_str(inp.day[i]), "last_close": last,
                         "samples": samples, "mean": samples.mean(axis=0), "actual": pct(inp.path[i]),
                         "signal_24": int(d24["signal"][i]), "label_24": int(d24["label"][i])})
    game = []
    for w, i in enumerate(game_idx):
        last = float(inp.last_close[i])
        game.append({"context": inp.ctx_ohlc[i] / last * 100.0,            # OHLC, last close = 100; no absolute levels
                     "kronos_call": int(d24["signal"][i]), "coin_flip": int(coins[w]),
                     "actual": inp.path[i] / last * 100.0,
                     "reveal": {"pair": str(inp.pair[i]), "date": day_str(inp.day[i])}})

    sections = prereg_sections(prereg_text)
    prim = res["primary"]
    site = {
        "synthetic": bool(synthetic),
        "synthetic_meta": meta if synthetic else None,
        "protocol": {"lookback": D.LOOKBACK, "horizons": list(A.HORIZONS), "primary_horizon": HORIZON, "samples": A.N_SAMPLES,
                     "pred_len": A.PRED_LEN, "window_start": A.WINDOW_START.isoformat(), "window_end": day_str(A.N_DAYS - 1),
                     "days": A.N_DAYS, "pairs": list(A.PAIRS_DEFAULT), "origins_total": A.N_DAYS * len(A.PAIRS_DEFAULT),
                     "context_bars_shown": A.CTX_BARS_SHOWN, "underpowered_below_n": A.UNDERPOWERED_N, "alpha": A.ALPHA,
                     "bootstrap_B": A.B_BOOT, "game_windows": len(game), "featured_origins": len(featured)},
        "headline": {"decision_h1": prim["decision_h1"], "decision_h2": prim["decision_h2"], "headline": prim["headline"],
                     "underpowered": prim["underpowered"], "n": prim["n"], "D": prim["kronos_down_calls_D"],
                     "largest_edge_not_ruled_out_h1": prim["largest_edge_not_ruled_out_h1"],
                     "largest_gain_vs_always_up_not_ruled_out_h2": prim["largest_gain_vs_always_up_not_ruled_out_h2"]},
        "primary": {k: prim[k] for k in ("n", "n_days", "k_correct", "accuracy", "ci_accuracy", "always_up_accuracy", "accuracy_diff",
                                         "ci_diff", "p_h1_raw", "p_h2_raw", "p_h1_holm", "p_h2_holm",
                                         "discordant_kronos_right_alwaysup_wrong", "discordant_kronos_wrong_alwaysup_right",
                                         "kronos_down_calls_D", "share_correct_down_calls") if k in prim},
        "power": {"rows": res["power"]["rows"], "k": res["power"]["k"], "z_sum": res["power"]["z_sum"], "D": res["power"]["D"],
                  "min_detectable_shift_down_calls_pp": res["power"]["min_detectable_shift_down_calls_pp"]},
        "results_table": results_table(inp, d),
        "running_score": running_score(inp, d, res),
        "featured": featured,
        "game": game,
        "selection": {
            "pool": "h=24 analysis set (status ok, label 0 and signal 0 excluded) with complete price data; chosen by seed, never by outcome",
            "featured": {"n": len(featured), "seed": FEATURED_SEED, "rule": "numpy default_rng(seed).choice(pool, size, replace=False)"},
            "game": {"n": len(game), "seed": GAME_SEED, "rule": "numpy default_rng(seed).choice(pool, size, replace=False)"},
            "coin_flips": {"seed": COIN_SEED, "rule": "numpy default_rng(seed).choice([-1, 1], size=windows), one per window in order"},
            "reveal_note": "pair and date are stored in each game window's reveal field; the UI hides them until the answer is given, but a reader of this file can see them"},
        "disclosures": [x["text"] for x in sections.get(2, [])],
        "limits": [x["text"] for x in sections.get(11, [])],
        "method": {str(n): sections.get(n, []) for n in (3, 4, 5, 6, 7, 8, 9, 10)},
    }
    return r4(site)


# ---------------------------------------------------------------- CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--out", required=True)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--skill", type=float, default=0.1)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out = (out if out.is_absolute() else Path.cwd() / out).resolve()
    forbidden = [(ROOT / "results" / "final").resolve(), (ROOT / "results" / "runs").resolve()]
    if any(out == f or f in out.parents for f in forbidden):
        print(f"REFUSED: output may not go to {out}", file=sys.stderr)
        return 3
    prereg = (ROOT / "PREREGISTRATION.md").read_text()
    if a.synthetic:
        inp = A.synthetic_inputs(seed=a.seed, skill=a.skill, rho=0.5)
        res = A.run_analysis(inp)
        meta = {"seed": a.seed, "skill": a.skill, "rho": 0.5, "label": "SYNTHETIC DEMO DATA, NOT KRONOS RESULTS"}
    else:
        inp, _ = A.load_real_inputs(a.root)                       # raises unless results/runs/DONE exists
        res = json.loads((Path(a.root) / "results" / "final" / "results.json").read_text())
        meta = None
    site = build_site_json(inp, res, a.synthetic, prereg, meta)
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(site, separators=(",", ":"), allow_nan=False)
    assert len(text.encode()) <= MAX_BYTES, f"site.json is {len(text)} bytes"
    (out / "site.json").write_text(text)
    label = "SYNTHETIC" if a.synthetic else "REAL"
    print(f"{label}: wrote {out / 'site.json'} ({len(text.encode())} bytes); featured={len(site['featured'])} game={len(site['game'])} "
          f"points={len(site['running_score']['n'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
