"""Analysis tests. SYNTHETIC data only. No test touches the real results/runs, data/processed or data/raw:
`load_real_inputs` is only ever called with a tmp_path root.
"""
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from kronos_lab import analysis as A
from kronos_lab import data as D

N_SAMPLES = A.N_SAMPLES


def tiny_inputs(last, pred24, actual24, ks=None, pair=None, day=None, stage=None):
    """Hand-built SYNTHETIC inputs: every horizon uses the same numbers (h=1,4,24).

    pred24: (n,) predicted close shared by all 11 samples, unless ks (n,) is given: then ks[i] samples are
    above last_close (last+1) and the rest below (last-1).
    """
    last, actual24 = np.asarray(last, float), np.asarray(actual24, float)
    n = len(last)
    if ks is not None:
        closes = np.empty((n, N_SAMPLES, A.PRED_LEN))
        for i, k in enumerate(ks):
            closes[i, :k] = last[i] + 1
            closes[i, k:] = last[i] - 1
    else:
        closes = np.broadcast_to(np.asarray(pred24, float)[:, None, None], (n, N_SAMPLES, A.PRED_LEN)).copy()
    return A.Inputs(pair=np.array(pair or ["BTCUSDT"] * n, dtype=object),
                    day=np.asarray(day if day is not None else np.arange(n)),
                    stage=np.asarray(stage if stage is not None else np.full(n, 1)),
                    status=np.array(["ok"] * n, dtype=object), last_close=last, closes=closes,
                    actual=np.tile(actual24[:, None], (1, 3)), ctx_tail=np.tile(last[:, None], (1, 25)))


# a. perfect predictor ------------------------------------------------------------------
def test_perfect_predictor_is_edge_detected():
    inp = A.synthetic_inputs(seed=3, skill=0.0)
    last = inp.last_close[:, None]
    inp.closes = np.broadcast_to(last[:, :, None], inp.closes.shape).copy()
    for j, h in enumerate(A.HORIZONS):
        inp.closes[:, :, h - 1] = inp.actual[:, j][:, None]
    res = A.run_analysis(inp, B=500)
    p = res["primary"]
    assert p["accuracy"] == 1.0 and p["n"] == len(inp)
    assert p["p_h1_raw"] < 1e-10 and p["p_h1_holm"] < 1e-10
    assert p["decision_h1"] == "edge detected vs coin flip"
    assert p["decision_h2"] == "beats always-up"
    assert not p["underpowered"]
    assert res["exploratory_accuracy_by_horizon"]["h1"]["accuracy"] == 1.0


# b. coin flip false positives ----------------------------------------------------------
# 2,000 datasets, N=1,000 (100 days x 10 origins), bootstrap B=200 (small on purpose; the real run uses 10,000).
SIMS, SIM_N, SIM_DAYS, SIM_B = 2000, 1000, 100, 200


def test_coin_flip_false_positive_rates():
    rng = np.random.default_rng(12345)
    day = np.repeat(np.arange(SIM_DAYS), SIM_N // SIM_DAYS)
    raw_reject = positive_claims = any_flag = 0
    for s in range(SIMS):
        label = rng.choice([-1.0, 1.0], SIM_N)
        signal = rng.choice([-1.0, 1.0], SIM_N)
        r = A.primary_core(label, signal, day, B=SIM_B, seed=s)
        raw_reject += r["p_h1_raw"] < 0.05
        positive_claims += (r["decision_h1"] == "edge detected vs coin flip") or (r["decision_h2"] == "beats always-up")
        any_flag += (r["decision_h1"] != "no detectable edge") or (r["decision_h2"] != "no detectable edge")
    raw_rate, pos_rate, any_rate = raw_reject / SIMS, positive_claims / SIMS, any_flag / SIMS
    print(f"SYNTHETIC false-positive rates over {SIMS} datasets, N={SIM_N}, B={SIM_B}: "
          f"raw exact H1 {raw_rate:.4f}; positive claims (edge/beats) {pos_rate:.4f}; any flag {any_rate:.4f}")
    # simulation SE at 5% is 0.49 pp; tolerance is +-3 SE around the nominal size (the exact test is slightly conservative)
    assert 0.034 <= raw_rate <= 0.066
    assert pos_rate <= 0.05
    assert any_rate <= 0.05 + 0.015


# c. always-up predictor ------------------------------------------------------------------
def test_always_up_predictor_has_no_down_calls_and_no_crash():
    inp = A.synthetic_inputs(seed=4, skill=0.0, n_days=60)
    inp.closes = (inp.last_close[:, None, None] * 1.01) * np.ones((1, N_SAMPLES, A.PRED_LEN))
    res = A.run_analysis(inp, B=300)
    p = res["primary"]
    assert p["kronos_down_calls_D"] == 0 and p["share_correct_down_calls"] is None
    assert p["discordant_kronos_right_alwaysup_wrong"] == 0 and p["discordant_kronos_wrong_alwaysup_right"] == 0
    assert p["p_h2_raw"] == 1.0
    assert p["accuracy_diff"] == 0.0 and p["ci_diff"] == [0.0, 0.0]
    assert p["decision_h2"] == "no detectable edge"
    assert res["power"]["min_detectable_shift_down_calls_pp"] is None


# d. Holm, McNemar, exclusions -----------------------------------------------------------------
def test_holm_known_values():
    assert A.holm_adjust([0.01, 0.04]) == pytest.approx([0.02, 0.04])
    assert A.holm_adjust([0.04, 0.01]) == pytest.approx([0.04, 0.02])
    assert A.holm_adjust([0.03, 0.03]) == pytest.approx([0.06, 0.06])
    assert A.holm_adjust([0.5, 0.001]) == pytest.approx([0.5, 0.002])
    assert A.holm_adjust([0.02, 0.011]) == pytest.approx([0.022, 0.022])   # monotone step-down
    assert A.holm_adjust([0.7, 0.9]) == pytest.approx([1.0, 1.0])          # 0.7 * 2 = 1.4, capped at 1


def test_mcnemar_hand_computed_case_and_exclusion_counts():
    # 8 origins: signal down, label down (Kronos right, always-up wrong)
    # 2 origins: signal down, label up   (Kronos wrong, always-up right)
    # 5 origins: signal up, label up; 3 origins: signal up, label down
    # plus 3 origins with label 0 (actual == last_close) and 2 with signal 0 (mean forecast == last_close)
    last, pred, actual = [], [], []
    def add(n, p, a):
        last.extend([100.0] * n); pred.extend([p] * n); actual.extend([a] * n)
    add(8, 99, 99); add(2, 99, 101); add(5, 101, 102); add(3, 101, 98)
    add(3, 101, 100)    # label 0
    add(2, 100, 101)    # signal 0
    inp = tiny_inputs(last, pred, actual)
    d = A.derive(inp)
    c = d[24]["counts"]
    assert c["label_zero_excluded"] == 3 and c["signal_zero_excluded"] == 2 and c["n_used"] == 18
    r = A.primary(d, inp, B=200)
    assert r["n"] == 18
    assert r["discordant_kronos_right_alwaysup_wrong"] == 8 and r["discordant_kronos_wrong_alwaysup_right"] == 2
    assert r["kronos_down_calls_D"] == 10
    assert r["p_h2_raw"] == pytest.approx(2 * (1 + 10 + 45) / 1024)   # 0.109375
    assert r["k_correct"] == 13 and r["accuracy"] == pytest.approx(13 / 18)
    assert r["share_correct_down_calls"] == pytest.approx(0.8)


def test_nan_status_origins_are_excluded_and_counted():
    inp = A.synthetic_inputs(seed=5, n_days=50, nan_frac=0.2)
    d = A.derive(inp)
    c = d[24]["counts"]
    assert c["n_status_not_ok"] == int((inp.status != "ok").sum()) > 0
    assert c["n_used"] <= c["n_status_ok"]


# e. clustering ---------------------------------------------------------------------------------
def test_day_block_ci_wider_than_naive_binomial_ci_under_cross_pair_correlation():
    rng = np.random.default_rng(7)
    days, pairs = 200, 6
    day = np.repeat(np.arange(days), pairs)
    correct_day = rng.random(days) < 0.55
    label = rng.choice([-1.0, 1.0], days * pairs)
    signal = np.where(correct_day[day], label, -label)         # all pairs share the day's outcome
    r = A.primary_core(label, signal, day, B=2000, seed=1)
    w_boot = r["ci_accuracy"][1] - r["ci_accuracy"][0]
    w_naive = r["naive_binomial_ci95"][1] - r["naive_binomial_ci95"][0]
    print(f"SYNTHETIC CI widths: day-block {w_boot:.4f} vs naive {w_naive:.4f}")
    assert w_boot > 1.5 * w_naive


# f. bootstrap determinism and coverage -------------------------------------------------------------
def test_bootstrap_deterministic_and_covers_true_accuracy():
    rng = np.random.default_rng(1)
    days, pairs = 150, 4
    day = np.repeat(np.arange(days), pairs)
    label = rng.choice([-1.0, 1.0], days * pairs)
    signal = np.where(rng.random(days * pairs) < 0.55, label, -label)      # true accuracy 0.55
    a = A.primary_core(label, signal, day, B=1000, seed=A.BOOT_SEED)
    b = A.primary_core(label, signal, day, B=1000, seed=A.BOOT_SEED)
    c = A.primary_core(label, signal, day, B=1000, seed=A.BOOT_SEED + 1)
    assert a["ci_accuracy"] == b["ci_accuracy"] and a["ci_diff"] == b["ci_diff"]
    assert a["ci_accuracy"] != c["ci_accuracy"]
    assert a["ci_accuracy"][0] < 0.55 < a["ci_accuracy"][1]
    assert a["boot_seed"] == 20261106 and A.B_BOOT == 10_000


def test_underpowered_flag_below_1188():
    r = A.primary_core(np.array([1.0] * 100), np.array([1.0] * 100), np.arange(100), B=100)
    assert r["underpowered"] and r["headline"].startswith("UNDERPOWERED")
    r2 = A.primary_core(np.ones(1188), np.ones(1188), np.arange(1188), B=50)
    assert not r2["underpowered"]


def test_worse_than_coin_flip_and_worse_than_always_up_wording():
    n, days = 400, 200
    day = np.repeat(np.arange(days), 2)
    label = np.where(np.arange(n) % 2 == 0, 1.0, -1.0)
    signal = -label                                             # always wrong
    r = A.primary_core(label, signal, day, B=200)
    assert r["decision_h1"] == "worse than a coin flip"
    assert r["decision_h2"] == "worse than always-up"


# g. power table -----------------------------------------------------------------------------------
def test_power_table_matches_preregistration():
    t = A.power_table()
    assert t["k"] == pytest.approx(1.5415, abs=5e-5) and t["z_sum"] == pytest.approx(3.0830, abs=5e-5)
    got = {r["n"]: round(r["min_detectable_edge_pp"], 2) for r in t["rows"]}
    assert got == {594: 6.32, 1188: 4.47, 2376: 3.16}
    assert A.power_table(D=400)["min_detectable_shift_down_calls_pp"] == pytest.approx(A.K_POWER / 20 * 100)


# h. Brier, calibration, break-even fee, band --------------------------------------------------------
def test_brier_calibration_and_breakeven_fee_hand_case():
    last = [100.0] * 4
    ks = [11, 0, 6, 3]
    actual = [102.0, 101.0, 97.0, 104.0]       # up, up, down, up
    inp = tiny_inputs(last, None, actual, ks=ks)
    res = A.run_analysis(inp, B=50)
    br = res["exploratory_brier"]["h24"]
    assert br["brier_p_up"] == pytest.approx((0 + 1 + (6 / 11) ** 2 + (8 / 11) ** 2) / 4)
    assert br["brier_constant_half"] == pytest.approx(0.25)
    cal = {c["k"]: c for c in res["exploratory_calibration_h24"]}
    assert len(cal) == 12 and cal[11]["frac_up"] == 1.0 and cal[6]["frac_up"] == 0.0 and cal[0]["frac_up"] == 1.0
    assert cal[3]["n"] == 1 and cal[1]["n"] == 0 and cal[1]["frac_up"] is None
    cc = res["exploratory_cost_check"]
    # positions +1,-1,+1,-1 ; gross = +0.02, -0.01, -0.03, -0.04 ; mean -0.015
    assert cc["mean_gross_return_bps"] == pytest.approx(-150.0)
    assert cc["breakeven_per_side_fee_bps"] == pytest.approx(-75.0)
    assert cc["grid_mean_net_return_bps"]["5"] == pytest.approx(-160.0)
    assert cc["grid_mean_net_return_bps"]["0"] == pytest.approx(-150.0)


def test_persistence_and_magnitude_error_hand_case():
    last = [100.0, 100.0]
    inp = tiny_inputs(last, [101.0, 99.0], [102.0, 98.0])
    inp.ctx_tail[:] = np.array([[95.0] * 25, [105.0] * 25])        # returns: up, down; ends set to last below
    inp.ctx_tail[:, -1] = 100.0
    res = A.run_analysis(inp, B=50)
    pers = res["exploratory_persistence_baseline"]["h24"]
    assert pers["n"] == 2 and pers["accuracy"] == 1.0
    mag = res["exploratory_naive_magnitude_error"]["h24"]
    assert mag["kronos_mean_abs_pct_error"] == pytest.approx((1 / 100 + 1 / 100) / 2)
    assert mag["naive_last_value_mean_abs_pct_error"] == pytest.approx(0.02)


def test_coin_flip_band_deterministic_and_ordered():
    a, b = A.coin_flip_band(300), A.coin_flip_band(300)
    for k in ("lo_2_5", "median", "hi_97_5"):
        np.testing.assert_array_equal(a[k], b[k])
    assert a["n_paths"] == 1000 and a["seed"] == A.BAND_SEED and len(a["n"]) == 300
    assert (a["lo_2_5"] <= a["median"]).all() and (a["median"] <= a["hi_97_5"]).all()
    assert 0.0 <= a["lo_2_5"].min() and a["hi_97_5"].max() <= 1.0
    assert a["lo_2_5"][-1] < 0.5 < a["hi_97_5"][-1]


def test_every_exploratory_key_is_prefixed_and_table_rows_are_labelled():
    inp = A.synthetic_inputs(seed=2, skill=0.1, n_days=40)
    res = A.run_analysis(inp, B=100)
    non_expl = {"primary", "exclusions", "power", "power_at_actual_N"}
    assert all(k.startswith("exploratory_") for k in res if k not in non_expl)
    rows = A.results_table(res, "SYNTHETIC")
    assert all(r["data_source"] == "SYNTHETIC" for r in rows)
    assert all(r["metric"].startswith("exploratory_") for r in rows if r["section"] == "exploratory")
    json.dumps(A.clean(res), allow_nan=False)        # JSON-safe, no NaN


def test_stage_rule_matches_data_module():
    assert [int(A.stage_of_index(i)) for i in range(396)] == [D.stage_of(i) for i in range(396)]


# i. load_real_inputs guard (tmp roots only) -----------------------------------------------------------
def test_load_real_inputs_raises_without_done(tmp_path):
    (tmp_path / "results" / "runs").mkdir(parents=True)
    (tmp_path / "results" / "runs" / "forecasts.jsonl").write_text("")
    with pytest.raises(RuntimeError, match="DONE"):
        A.load_real_inputs(tmp_path)


def test_load_real_inputs_parses_a_fake_finished_run(tmp_path):
    # SYNTHETIC prices in a temporary tree, not the project's
    start = D.to_ms(datetime(2025, 9, 1, tzinfo=timezone.utc))
    n = 14 * 31 * 24
    t = start + D.HOUR_MS * np.arange(n, dtype=np.int64)
    base = 100 + np.arange(n) * 0.01
    s = D.Series(t, base, base + 1, base - 1, base + 0.5, np.ones(n), np.ones(n))
    D.write_processed(s, tmp_path / "data" / "processed" / "BTCUSDT_1h.csv")
    runs = tmp_path / "results" / "runs"
    runs.mkdir(parents=True)
    day = date(2025, 10, 5)
    o = D.to_ms(D.origin_ts(day))
    k = int(np.searchsorted(s.open_time, o))
    rec = {"pair": "BTCUSDT", "date": day.isoformat(), "stage": 3, "origin_ts": D.iso(o), "last_close": float(s.close[k - 1]),
           "closes": [[float(s.close[k - 1]) + 1.0] * 24 for _ in range(11)], "status": "ok", "seconds": 1.0}
    bad = {"pair": "BTCUSDT", "date": "2025-10-06", "stage": 4, "origin_ts": "x", "last_close": None, "closes": None,
           "status": "excluded", "seconds": 0.0}
    (runs / "forecasts.jsonl").write_text(json.dumps(rec) + "\n" + json.dumps(bad) + "\n")
    (runs / "DONE").write_text(json.dumps({"reason": "all_complete", "done": 2, "total": 2}))
    inp, meta = A.load_real_inputs(tmp_path)
    assert len(inp) == 2 and meta["done"]["reason"] == "all_complete"
    assert inp.day.tolist() == [4, 5] and inp.status.tolist() == ["ok", "excluded"]
    assert inp.actual[0, 0] == s.close[k] and inp.actual[0, 1] == s.close[k + 3] and inp.actual[0, 2] == s.close[k + 23]
    assert inp.ctx_tail[0, -1] == s.close[k - 1] and inp.ctx_tail[0, 0] == s.close[k - 25]
    assert np.isnan(inp.closes[1]).all()


# ---- Phase 5, step 1a: analytic size of the exact two-sided binomial test --------------------------------
def test_exact_binomial_test_size_at_n1000_is_at_most_five_percent():
    from scipy.stats import binom
    n = 1000
    ks = np.arange(n + 1)
    pmf = binom.pmf(ks, n, 0.5)
    pvals = np.array([A.exact_binom_p(int(k), n) for k in ks])        # the very function the analysis uses
    size = float(pmf[pvals <= 0.05].sum())                            # P(reject) under the null, exactly
    print(f"ANALYTIC size of the two-sided exact binomial test, N={n}, p=0.5, alpha=0.05: {size:.6f}")
    assert size <= 0.05
    assert size > 0.03            # not absurdly conservative either


# ---- Phase 5, amendment 2: primary results unchanged by the additive Inputs change -----------------------
def assert_close(got, want, path="root"):
    """Recursive comparison for floats that numpy/scipy may compute differently in the last digits on another platform.
    Floats: math.isclose(rel_tol=1e-9, abs_tol=0), with abs_tol=1e-15 only when the expected value is exactly zero.
    Everything else (ints, bools, strings such as decisions and headlines, None, list lengths, dict keys) must match EXACTLY."""
    if isinstance(want, dict):
        assert isinstance(got, dict) and set(got) == set(want), f"{path}: keys differ"
        for k in want:
            assert_close(got[k], want[k], f"{path}.{k}")
    elif isinstance(want, (list, tuple)):
        assert isinstance(got, (list, tuple)) and len(got) == len(want), f"{path}: length differs"
        for i, (a, b) in enumerate(zip(got, want)):
            assert_close(a, b, f"{path}[{i}]")
    elif isinstance(want, float):
        assert type(got) is float, f"{path}: {got!r} is not a float"
        assert math.isclose(got, want, rel_tol=1e-9, abs_tol=1e-15 if want == 0.0 else 0.0), f"{path}: {got!r} != {want!r}"
    else:
        assert type(got) is type(want) and got == want, f"{path}: {got!r} != {want!r}"


def test_assert_close_comparator_self_test():
    base = {"p": 2.9822428956332436e-08, "ci": [0.5391076213158065, 0.25], "decision": "edge detected vs coin flip", "k": 7, "flag": True, "zero": 0.0, "none": None}
    assert_close(dict(base), base)
    near = dict(base, p=2.9822428956333005e-08, ci=[0.5391076213158063, 0.25])            # the last-digit differences seen on CI
    assert_close(near, base)
    assert_close(dict(base, zero=1e-16), base)                                                # abs_tol only for an exact expected zero
    for bad in (dict(base, p=base["p"] * (1 + 1e-6)),                                         # relative change of 1e-6
                dict(base, ci=[0.5391076213158065 * (1 + 1e-6), 0.25]),
                dict(base, decision="no detectable edge"),                                    # flipped decision string
                dict(base, k=8),                                                              # changed integer count
                dict(base, k=7.0),                                                            # int vs float is a different type
                dict(base, flag=False),
                dict(base, none=0.0),
                dict(base, zero=1e-12),
                dict(base, ci=[0.5391076213158065]),                                          # list length
                {k: v for k, v in base.items() if k != "k"},                                  # missing key
                dict(base, extra=1)):                                                         # extra key
        with pytest.raises(AssertionError):
            assert_close(bad, base)


def test_primary_results_identical_to_pre_phase5_golden():
    gold = json.loads((Path(__file__).parent / "golden" / "synthetic_primary_before_phase5.json").read_text())
    for name, g in gold.items():
        inp = A.synthetic_inputs(**g["kwargs"])
        res = A.run_analysis(inp, B=g["B"])
        got = A.clean({k: res["primary"][k] for k in g["primary"]})
        assert_close(got, g["primary"], name)
        assert A.clean(res["primary"]["exclusions_h24"]) == g["exclusions_h24"], name
        # the new optional fields exist, have the right shape, and end at last_close
        assert inp.path.shape == (len(inp), 24) and inp.ctx_ohlc.shape == (len(inp), 72, 4)
        np.testing.assert_array_equal(inp.ctx_ohlc[:, -1, 3], inp.last_close)
        np.testing.assert_array_equal(inp.path[:, [0, 3, 23]], inp.actual)
        assert (inp.ctx_ohlc[:, :, 1] >= np.maximum(inp.ctx_ohlc[:, :, 0], inp.ctx_ohlc[:, :, 3])).all()
        assert (inp.ctx_ohlc[:, :, 2] <= np.minimum(inp.ctx_ohlc[:, :, 0], inp.ctx_ohlc[:, :, 3])).all()
