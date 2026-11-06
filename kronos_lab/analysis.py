"""Analysis per PREREGISTRATION.md sections 6-9. stdlib + numpy + scipy only.

Pure functions on in-memory arrays. The ONLY function that may open results/runs/ or data/processed/ is
`load_real_inputs`, and it raises unless <root>/results/runs/DONE exists. Everything else (including
`synthetic_inputs`) works on arrays that the caller supplies.

Primary analysis is h=24 only (section 7). Everything under section 9 returns keys prefixed
"exploratory_".
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from scipy.stats import binomtest, norm

HORIZONS = (1, 4, 24)
N_SAMPLES = 11
PRED_LEN = 24
B_BOOT = 10_000
BOOT_SEED = 20261106
BAND_SEED = 20261107          # separate stream for the site's coin-flip band
ALPHA = 0.05
UNDERPOWERED_N = 1188
WINDOW_START = date(2025, 10, 1)
N_DAYS = 396
PAIRS_DEFAULT = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"]
Z_SUM = float(norm.ppf(1 - 0.025 / 2) + norm.ppf(0.80))   # 3.0830
K_POWER = Z_SUM * 0.5                                        # 1.5415
FEE_GRID_BPS = (0, 5, 10, 20)
CTX_BARS_SHOWN = 72           # context bars shown in the site's game


# ---------------------------------------------------------------- inputs
@dataclass
class Inputs:
    pair: np.ndarray        # (n,) str
    day: np.ndarray         # (n,) int, forecast day index 0..395
    stage: np.ndarray       # (n,) int
    status: np.ndarray      # (n,) str: "ok", "nan", "excluded"
    last_close: np.ndarray  # (n,)
    closes: np.ndarray      # (n, 11, 24) predicted closes per sample (NaN where missing)
    actual: np.ndarray      # (n, 3) real closes of bars h=1,4,24 (NaN if unavailable)
    ctx_tail: np.ndarray    # (n, 25) last 25 context closes, ending at last_close
    # Optional, used only by the site builder (not by any statistic):
    path: np.ndarray | None = None       # (n, 24) real closes of the 24 forecast-day bars (NaN if unavailable)
    ctx_ohlc: np.ndarray | None = None   # (n, 72, 4) last 72 context bars: open, high, low, close

    def __post_init__(self):
        n = len(self.pair)
        assert self.closes.shape == (n, N_SAMPLES, PRED_LEN), self.closes.shape
        assert self.actual.shape == (n, 3) and self.ctx_tail.shape == (n, 25)
        if self.path is not None:
            assert self.path.shape == (n, PRED_LEN), self.path.shape
        if self.ctx_ohlc is not None:
            assert self.ctx_ohlc.shape == (n, CTX_BARS_SHOWN, 4), self.ctx_ohlc.shape
        for f in ("day", "stage", "status", "last_close"):
            assert len(getattr(self, f)) == n, f

    def __len__(self):
        return len(self.pair)


def stage_of_index(i):
    i = np.asarray(i)
    return np.where(i % 8 == 0, 1, np.where(i % 4 == 0, 2, np.where(i % 2 == 0, 3, 4)))


# ---------------------------------------------------------------- section 6: definitions
def derive(inp: Inputs) -> dict:
    """label_h, m_h, signal_h, p_up_h for h in (1, 4, 24), with exclusions counted per horizon."""
    out = {}
    ok = inp.status == "ok"
    last = inp.last_close.astype(float)
    for j, h in enumerate(HORIZONS):
        pred = inp.closes[:, :, h - 1]
        actual = inp.actual[:, j].astype(float)
        with np.errstate(invalid="ignore"):
            m = pred.mean(axis=1)
            label = np.sign(actual - last)
            signal = np.sign(m - last)
            p_up = (pred > last[:, None]).sum(axis=1) / N_SAMPLES
        finite = np.isfinite(actual) & np.isfinite(last) & np.isfinite(m)
        valid = ok & finite
        label_zero = valid & (label == 0)
        signal_zero = valid & (signal == 0)
        use = valid & (label != 0) & (signal != 0)
        out[h] = {
            "m": m, "label": label, "signal": signal, "p_up": p_up, "actual": actual, "valid": valid, "use": use,
            "counts": {"n_total": int(len(inp)), "n_status_ok": int(ok.sum()), "n_status_not_ok": int((~ok).sum()),
                       "n_missing_actual_among_ok": int((ok & ~finite).sum()),
                       "label_zero_excluded": int(label_zero.sum()), "signal_zero_excluded": int(signal_zero.sum()),
                       "n_used": int(use.sum())},
        }
    return out


# ---------------------------------------------------------------- section 7: primary analysis
def holm_adjust(pvals) -> list:
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    adj = np.empty(m)
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, (m - rank) * p[i])
        adj[i] = min(1.0, run)
    return adj.tolist()


def exact_binom_p(k: int, n: int) -> float:
    return 1.0 if n == 0 else float(binomtest(int(k), int(n), 0.5, alternative="two-sided").pvalue)


def decide(p1_holm, p2_holm, acc, diff, ci_acc, ci_diff, n) -> dict:
    """Section 7 decision rule, exactly."""
    if n == 0 or ci_acc is None:
        d1 = d2 = "no detectable edge"
        ub1 = ub2 = None
    else:
        if p1_holm < ALPHA and ci_acc[0] > 0.5:
            d1 = "edge detected vs coin flip"
        elif p1_holm < ALPHA and acc < 0.5:
            d1 = "worse than a coin flip"
        else:
            d1 = "no detectable edge"
        if p2_holm < ALPHA and ci_diff[0] > 0:
            d2 = "beats always-up"
        elif p2_holm < ALPHA and diff < 0:
            d2 = "worse than always-up"
        else:
            d2 = "no detectable edge"
        ub1 = ci_acc[1] - 0.5          # largest accuracy edge over a coin flip not ruled out
        ub2 = ci_diff[1]               # largest accuracy gain over always-up not ruled out
    under = n < UNDERPOWERED_N
    headline = ("UNDERPOWERED (N=%d < %d). " % (n, UNDERPOWERED_N) if under else "") + f"H1: {d1}. H2: {d2}."
    return {"decision_h1": d1, "decision_h2": d2, "largest_edge_not_ruled_out_h1": ub1,
            "largest_gain_vs_always_up_not_ruled_out_h2": ub2, "underpowered": bool(under), "headline": headline}


def primary_core(label, signal, day, B: int = B_BOOT, seed: int = BOOT_SEED) -> dict:
    """label/signal/day restricted to the analysis set (label != 0, signal != 0, status ok)."""
    label, signal, day = np.asarray(label), np.asarray(signal), np.asarray(day)
    n = int(len(label))
    kc = signal == label                  # Kronos correct
    ac = label == 1                       # always-up correct
    k = int(kc.sum())
    b = int((kc & ~ac).sum())             # Kronos right, always-up wrong
    c = int((~kc & ac).sum())             # Kronos wrong, always-up right
    D = int((signal == -1).sum())         # Kronos down-calls
    p1, p2 = exact_binom_p(k, n), exact_binom_p(b, b + c)
    p1h, p2h = holm_adjust([p1, p2])
    res = {"n": n, "k_correct": k, "accuracy": k / n if n else None,
           "always_up_accuracy": float(ac.mean()) if n else None,
           "accuracy_diff": (k - int(ac.sum())) / n if n else None,
           "discordant_kronos_right_alwaysup_wrong": b, "discordant_kronos_wrong_alwaysup_right": c,
           "kronos_down_calls_D": D, "down_calls_correct": b,
           "share_correct_down_calls": (b / D) if D else None,
           "p_h1_raw": p1, "p_h2_raw": p2, "p_h1_holm": p1h, "p_h2_holm": p2h,
           "naive_binomial_ci95": None, "boot_B": B, "boot_seed": seed, "ci_accuracy": None, "ci_diff": None}
    if n:
        ci = binomtest(k, n, 0.5).proportion_ci(confidence_level=0.95, method="exact")
        res["naive_binomial_ci95"] = [float(ci.low), float(ci.high)]
        days, inv = np.unique(day, return_inverse=True)
        nd = len(days)
        n_d = np.bincount(inv, minlength=nd).astype(np.int64)
        k_d = np.bincount(inv, weights=kc, minlength=nd).astype(np.int64)
        a_d = np.bincount(inv, weights=ac, minlength=nd).astype(np.int64)
        idx = np.random.default_rng(seed).integers(0, nd, size=(B, nd))   # resample forecast DAYS
        Nb, Kb, Ab = n_d[idx].sum(1), k_d[idx].sum(1), a_d[idx].sum(1)
        acc_b, diff_b = Kb / Nb, (Kb - Ab) / Nb
        res["ci_accuracy"] = np.percentile(acc_b, [2.5, 97.5]).tolist()
        res["ci_diff"] = np.percentile(diff_b, [2.5, 97.5]).tolist()
        res["n_days"] = int(nd)
    res.update(decide(p1h, p2h, res["accuracy"], res["accuracy_diff"], res["ci_accuracy"], res["ci_diff"], n))
    return res


def primary(derived: dict, inp: Inputs, B: int = B_BOOT, seed: int = BOOT_SEED) -> dict:
    d = derived[24]
    use = d["use"]
    res = primary_core(d["label"][use], d["signal"][use], inp.day[use], B, seed)
    res["exclusions_h24"] = d["counts"]
    return res


# ---------------------------------------------------------------- section 8: power
def power_table(ns=(594, 1188, 2376), D: int | None = None) -> dict:
    rows = [{"n": int(n), "min_detectable_edge_pp": K_POWER / math.sqrt(n) * 100,
             "accuracy_needed": 0.5 + K_POWER / math.sqrt(n)} for n in ns]
    out = {"z_sum": Z_SUM, "k": K_POWER, "rows": rows, "D": D}
    out["min_detectable_shift_down_calls_pp"] = (K_POWER / math.sqrt(D) * 100) if D else None
    return out


# ---------------------------------------------------------------- section 9: exploratory
def _acc(label, signal) -> dict:
    n = int(len(label))
    k = int((label == signal).sum())
    return {"n": n, "k_correct": k, "accuracy": (k / n) if n else None}


def exploratory(inp: Inputs, derived: dict) -> dict:
    out = {}
    # accuracy at h=1 and h=4
    out["exploratory_accuracy_by_horizon"] = {
        f"h{h}": {**_acc(derived[h]["label"][derived[h]["use"]], derived[h]["signal"][derived[h]["use"]]),
                  "label_zero_excluded": derived[h]["counts"]["label_zero_excluded"],
                  "signal_zero_excluded": derived[h]["counts"]["signal_zero_excluded"]} for h in (1, 4)}
    d24 = derived[24]
    use = d24["use"]
    # per pair / per stage (h=24 analysis set)
    out["exploratory_by_pair"] = {str(p): _acc(d24["label"][use & (inp.pair == p)], d24["signal"][use & (inp.pair == p)])
                                  for p in sorted(set(inp.pair.tolist()))}
    out["exploratory_by_stage"] = {str(s): _acc(d24["label"][use & (inp.stage == s)], d24["signal"][use & (inp.stage == s)])
                                   for s in sorted(set(inp.stage.tolist()))}
    pers, mag, brier = {}, {}, {}
    for j, h in enumerate(HORIZONS):
        d = derived[h]
        # persistence: sign of the last h-bar return, evaluated where label != 0 and persistence != 0
        with np.errstate(invalid="ignore"):
            psig = np.sign(inp.last_close - inp.ctx_tail[:, -1 - h])
        pm = d["valid"] & (d["label"] != 0) & (psig != 0)
        pers[f"h{h}"] = _acc(d["label"][pm], psig[pm])
        # naive last-value magnitude error vs Kronos mean forecast, as a fraction of last_close
        v = d["valid"]
        ek = np.abs(d["m"][v] - d["actual"][v]) / inp.last_close[v]
        en = np.abs(inp.last_close[v] - d["actual"][v]) / inp.last_close[v]
        mag[f"h{h}"] = {"n": int(v.sum()), "kronos_mean_abs_pct_error": float(ek.mean()) if v.any() else None,
                        "naive_last_value_mean_abs_pct_error": float(en.mean()) if v.any() else None}
        # Brier of p_up vs constant 0.5 (origins with label != 0)
        bm = d["valid"] & (d["label"] != 0)
        y = (d["label"][bm] == 1).astype(float)
        bk = float(((d["p_up"][bm] - y) ** 2).mean()) if bm.any() else None
        bc = float(((0.5 - y) ** 2).mean()) if bm.any() else None
        brier[f"h{h}"] = {"n": int(bm.sum()), "brier_p_up": bk, "brier_constant_half": bc,
                          "difference_kronos_minus_constant": (bk - bc) if bm.any() else None}
    out["exploratory_persistence_baseline"] = pers
    out["exploratory_naive_magnitude_error"] = mag
    out["exploratory_brier"] = brier
    # calibration over the 12 levels k/11 (h=24, label != 0)
    bm = d24["valid"] & (d24["label"] != 0)
    kup = np.rint(d24["p_up"][bm] * N_SAMPLES).astype(int)
    yup = (d24["label"][bm] == 1).astype(float)
    out["exploratory_calibration_h24"] = [
        {"k": k, "level": k / N_SAMPLES, "n": int((kup == k).sum()),
         "frac_up": float(yup[kup == k].mean()) if (kup == k).any() else None} for k in range(N_SAMPLES + 1)]
    # cost-aware check (status ok, finite actual): position +1 if p_up_24 > 0.5 else -1
    v = d24["valid"]
    pos = np.where(d24["p_up"][v] > 0.5, 1.0, -1.0)
    gross = pos * (d24["actual"][v] / inp.last_close[v] - 1.0)
    mg = float(gross.mean()) if v.any() else None
    out["exploratory_cost_check"] = {
        "n": int(v.sum()), "mean_gross_return_bps": None if mg is None else mg * 1e4,
        "breakeven_per_side_fee_bps": None if mg is None else mg / 2 * 1e4,
        "grid_mean_net_return_bps": {str(f): None if mg is None else (mg - 2 * f / 1e4) * 1e4 for f in FEE_GRID_BPS},
        "note": "illustrative only; spot cannot short without margin; funding and slippage ignored; no fee schedule cited"}
    return out


def coin_flip_band(n_max: int, n_paths: int = 1000, seed: int = BAND_SEED) -> dict:
    """Running share of 'correct' calls over 1..n_max origins for fair-coin paths (site illustration only)."""
    rng = np.random.default_rng(seed)
    steps = rng.integers(0, 2, size=(n_paths, n_max))
    running = np.cumsum(steps, axis=1) / np.arange(1, n_max + 1)
    lo, med, hi = np.percentile(running, [2.5, 50, 97.5], axis=0)
    return {"n_paths": n_paths, "seed": seed, "n": np.arange(1, n_max + 1), "lo_2_5": lo, "median": med, "hi_97_5": hi}


# ---------------------------------------------------------------- full pipeline
def run_analysis(inp: Inputs, B: int = B_BOOT) -> dict:
    d = derive(inp)
    prim = primary(d, inp, B)
    res = {"primary": prim,
           "exclusions": {f"h{h}": d[h]["counts"] for h in HORIZONS},
           "power": power_table(D=prim["kronos_down_calls_D"]),
           "power_at_actual_N": power_table(ns=(max(prim["n"], 1),)),
           **exploratory(inp, d),
           "exploratory_coin_flip_band": coin_flip_band(max(prim["n"], 1))}
    return res


def clean(o):
    """JSON-safe: numpy -> python, NaN/inf -> None."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return f if math.isfinite(f) else None
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def results_table(res: dict, data_source: str) -> list:
    """Flat rows: data_source, section, metric, value, ci_low, ci_high, p_raw, p_holm, n, note."""
    rows = []

    def add(section, metric, value=None, lo=None, hi=None, p_raw=None, p_holm=None, n=None, note=""):
        rows.append({"data_source": data_source, "section": section, "metric": metric, "value": value, "ci_low": lo,
                     "ci_high": hi, "p_raw": p_raw, "p_holm": p_holm, "n": n, "note": note})

    p = res["primary"]
    ca, cd = p["ci_accuracy"] or [None, None], p["ci_diff"] or [None, None]
    add("primary", "kronos_accuracy_h24", p["accuracy"], ca[0], ca[1], p["p_h1_raw"], p["p_h1_holm"], p["n"], "H1 exact binomial vs 0.5; CI = day-block bootstrap")
    add("primary", "always_up_accuracy_h24", p["always_up_accuracy"], n=p["n"])
    add("primary", "accuracy_minus_always_up_h24", p["accuracy_diff"], cd[0], cd[1], p["p_h2_raw"], p["p_h2_holm"], p["n"], "H2 exact McNemar; CI = day-block bootstrap")
    add("primary", "discordant_kronos_right_alwaysup_wrong", p["discordant_kronos_right_alwaysup_wrong"], n=p["n"])
    add("primary", "discordant_kronos_wrong_alwaysup_right", p["discordant_kronos_wrong_alwaysup_right"], n=p["n"])
    add("primary", "kronos_down_calls_D", p["kronos_down_calls_D"], n=p["n"])
    add("primary", "decision_h1", note=p["decision_h1"])
    add("primary", "decision_h2", note=p["decision_h2"])
    add("primary", "headline", note=p["headline"])
    for r in res["power"]["rows"]:
        add("power", f"min_detectable_edge_pp_N{r['n']}", r["min_detectable_edge_pp"], n=r["n"])
    add("power", "min_detectable_shift_down_calls_pp", res["power"]["min_detectable_shift_down_calls_pp"], n=res["power"]["D"], note="1.5415/sqrt(D)")
    for h, v in res["exploratory_accuracy_by_horizon"].items():
        add("exploratory", f"exploratory_accuracy_{h}", v["accuracy"], n=v["n"])
    for k, v in res["exploratory_by_pair"].items():
        add("exploratory", f"exploratory_accuracy_h24_pair_{k}", v["accuracy"], n=v["n"])
    for k, v in res["exploratory_by_stage"].items():
        add("exploratory", f"exploratory_accuracy_h24_stage_{k}", v["accuracy"], n=v["n"])
    for h, v in res["exploratory_persistence_baseline"].items():
        add("exploratory", f"exploratory_persistence_accuracy_{h}", v["accuracy"], n=v["n"])
    for h, v in res["exploratory_naive_magnitude_error"].items():
        add("exploratory", f"exploratory_kronos_mean_abs_pct_error_{h}", v["kronos_mean_abs_pct_error"], n=v["n"])
        add("exploratory", f"exploratory_naive_mean_abs_pct_error_{h}", v["naive_last_value_mean_abs_pct_error"], n=v["n"])
    for h, v in res["exploratory_brier"].items():
        add("exploratory", f"exploratory_brier_p_up_{h}", v["brier_p_up"], n=v["n"])
        add("exploratory", f"exploratory_brier_constant_half_{h}", v["brier_constant_half"], n=v["n"])
    for c in res["exploratory_calibration_h24"]:
        add("exploratory", f"exploratory_calibration_h24_level_{c['k']}/11", c["frac_up"], n=c["n"])
    cc = res["exploratory_cost_check"]
    add("exploratory", "exploratory_breakeven_per_side_fee_bps", cc["breakeven_per_side_fee_bps"], n=cc["n"], note=cc["note"])
    for f, v in cc["grid_mean_net_return_bps"].items():
        add("exploratory", f"exploratory_mean_net_return_bps_fee{f}", v, n=cc["n"])
    return rows


# ---------------------------------------------------------------- SYNTHETIC data (never real prices)
def synthetic_inputs(seed: int = 1, skill: float = 0.0, rho: float = 0.5, sigma: float = 0.02, nan_frac: float = 0.0,
                     n_days: int = N_DAYS, pairs=PAIRS_DEFAULT) -> Inputs:
    """SYNTHETIC dataset: random-walk prices with a shared daily factor (cross-pair correlation `rho`).

    `skill` scales how much the predicted closes follow the realised path (0 = pure noise).
    """
    rng = np.random.default_rng(seed)
    P = len(pairs)
    n = n_days * P
    day = np.repeat(np.arange(n_days), P)
    pair_i = np.tile(np.arange(P), n_days)
    f = rng.standard_normal((n_days, PRED_LEN))[day]
    e = rng.standard_normal((n, PRED_LEN))
    cum = np.cumsum(sigma / math.sqrt(PRED_LEN) * (rho * f + math.sqrt(1 - rho ** 2) * e), axis=1)
    last = (100.0 * np.exp(rng.normal(0, 1, P)))[pair_i]
    path = last[:, None] * np.exp(cum)
    ret = np.exp(cum) - 1
    zc = rng.standard_normal((n, 1, PRED_LEN))
    zs = rng.standard_normal((n, N_SAMPLES, PRED_LEN))
    closes = last[:, None, None] * (1 + skill * ret[:, None, :] + sigma * (0.5 * zc + 0.5 * zs))
    back = np.concatenate([np.zeros((n, 1)), np.cumsum(sigma / math.sqrt(PRED_LEN) * rng.standard_normal((n, 24)), axis=1)], axis=1)
    tail = last[:, None] * np.exp(-back[:, ::-1])
    status = np.array(["ok"] * n, dtype=object)
    if nan_frac > 0:
        bad = rng.random(n) < nan_frac
        status[bad] = "nan"
        closes[bad] = np.nan
    # Extras for the site (drawn AFTER everything above so earlier synthetic numbers are unchanged):
    step = sigma / math.sqrt(PRED_LEN)
    back72 = np.cumsum(step * rng.standard_normal((n, CTX_BARS_SHOWN)), axis=1)             # steps back from last_close
    cl = last[:, None] * np.exp(-np.concatenate([back72[:, ::-1][:, 1:], np.zeros((n, 1))], axis=1))  # closes, last = last_close
    op = np.concatenate([cl[:, :1] * np.exp(step * rng.standard_normal((n, 1))), cl[:, :-1]], axis=1)
    hi = np.maximum(op, cl) * (1 + 0.5 * step * np.abs(rng.standard_normal((n, CTX_BARS_SHOWN))))
    lo = np.minimum(op, cl) * (1 - 0.5 * step * np.abs(rng.standard_normal((n, CTX_BARS_SHOWN))))
    ctx_ohlc = np.stack([op, hi, lo, cl], axis=2)
    return Inputs(pair=np.array(pairs, dtype=object)[pair_i], day=day, stage=stage_of_index(day), status=status,
                  last_close=last, closes=closes, actual=path[:, [0, 3, 23]], ctx_tail=tail,
                  path=path, ctx_ohlc=ctx_ohlc)


# ---------------------------------------------------------------- REAL data: the only reader of results/runs and data/processed
def load_real_inputs(root) -> tuple[Inputs, dict]:
    """Load forecasts + label prices. Raises unless <root>/results/runs/DONE exists (run finished)."""
    from kronos_lab import data as D  # lazy; only needed here

    root = Path(root)
    done_path = root / "results" / "runs" / "DONE"
    if not done_path.exists():
        raise RuntimeError(f"refusing to load real inputs: {done_path} does not exist (the run has not stopped)")
    done = json.loads(done_path.read_text())
    recs = [json.loads(l) for l in (root / "results" / "runs" / "forecasts.jsonl").read_text().splitlines() if l.strip()]
    keys = [(r["pair"], r["date"]) for r in recs]
    assert len(keys) == len(set(keys)), "duplicate origins in forecasts.jsonl"
    series = {p: D.load_series(p, root / "data" / "processed") for p in sorted({r["pair"] for r in recs})}
    n = len(recs)
    closes = np.full((n, N_SAMPLES, PRED_LEN), np.nan)
    actual = np.full((n, 3), np.nan)
    tail = np.full((n, 25), np.nan)
    path = np.full((n, PRED_LEN), np.nan)
    ctx_ohlc = np.full((n, CTX_BARS_SHOWN, 4), np.nan)
    last = np.full(n, np.nan)
    day = np.zeros(n, dtype=int)
    for i, r in enumerate(recs):
        dd = date.fromisoformat(r["date"])
        day[i] = (dd - WINDOW_START).days
        if r.get("closes"):
            closes[i] = np.array([[np.nan if v is None else v for v in row] for row in r["closes"]], dtype=float)
        if r.get("last_close") is not None:
            last[i] = r["last_close"]
        s = series[r["pair"]]
        o = D.to_ms(D.origin_ts(dd))
        for j, h in enumerate(HORIZONS):
            t = o + (h - 1) * D.HOUR_MS          # bar h opens at (h-1):00 of the forecast day
            k = int(np.searchsorted(s.open_time, t))
            if k < len(s) and s.open_time[k] == t:
                actual[i, j] = s.close[k]
        k0 = int(np.searchsorted(s.open_time, o - 25 * D.HOUR_MS))
        want = o - 25 * D.HOUR_MS + D.HOUR_MS * np.arange(25)
        if k0 + 25 <= len(s) and np.array_equal(s.open_time[k0:k0 + 25], want):
            tail[i] = s.close[k0:k0 + 25]
        kp = int(np.searchsorted(s.open_time, o))                       # the 24 bars of the forecast day
        if kp + PRED_LEN <= len(s) and np.array_equal(s.open_time[kp:kp + PRED_LEN], o + D.HOUR_MS * np.arange(PRED_LEN)):
            path[i] = s.close[kp:kp + PRED_LEN]
        kc = int(np.searchsorted(s.open_time, o - CTX_BARS_SHOWN * D.HOUR_MS))   # the last 72 context bars
        if kc + CTX_BARS_SHOWN <= len(s) and np.array_equal(
                s.open_time[kc:kc + CTX_BARS_SHOWN], o - CTX_BARS_SHOWN * D.HOUR_MS + D.HOUR_MS * np.arange(CTX_BARS_SHOWN)):
            ctx_ohlc[i] = np.column_stack([s.open[kc:kc + CTX_BARS_SHOWN], s.high[kc:kc + CTX_BARS_SHOWN],
                                           s.low[kc:kc + CTX_BARS_SHOWN], s.close[kc:kc + CTX_BARS_SHOWN]])
    inp = Inputs(pair=np.array([r["pair"] for r in recs], dtype=object), day=day,
                 stage=np.array([r["stage"] for r in recs]), status=np.array([r["status"] for r in recs], dtype=object),
                 last_close=last, closes=closes, actual=actual, ctx_tail=tail, path=path, ctx_ohlc=ctx_ohlc)
    return inp, {"done": done, "n_forecast_lines": n}
