"""Build the CSV export from results/final/results.json ONLY. Presentation, no new statistics.

  python3 -I scripts/build_export.py [--root .] [--out results/export]

Writes results_summary.csv, data_dictionary.csv and README.md. Every number in the CSV is read from
results.json by a key path stored in the row's `source_key` column; the value/ci/p columns carry full
precision (Python repr), and `display` is the only rounded text. Row order is fixed in this file, so two
builds are byte-identical. Never opens results/runs, data/processed or data/raw.
"""
import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREREG_COMMIT = "56fcbdee4cb4055eb75669af5e411c45f845994b"
COLUMNS = ["section", "test_id", "label", "scope", "pair", "horizon_bars", "metric", "n", "value", "ci_low", "ci_high",
           "p_raw", "p_holm", "decision", "status", "display", "source_key"]
PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"]
SRC_COLS = ["value", "n", "ci_low", "ci_high", "p_raw", "p_holm", "decision"]


# ---------------------------------------------------------------- key paths
def get(res, path: str):
    """Resolve 'a.b.c' or 'a.b[1]' inside results.json. Keys are strings (e.g. 'h24', '0')."""
    cur = res
    for part in path.split("."):
        m = re.fullmatch(r"([^\[\]]+)((?:\[\d+\])*)", part)
        cur = cur[m.group(1)]
        for idx in re.findall(r"\[(\d+)\]", m.group(2)):
            cur = cur[int(idx)]
    return cur


def fmt_full(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    return str(v)


KINDS = {
    "pct": lambda v: f"{v * 100:.2f} %",
    "pp_frac": lambda v: f"{v * 100:+.2f} pp",
    "pp": lambda v: f"{v:.3f} pp",
    "p": lambda v: f"{v:.4g}",
    "int": lambda v: str(int(v)),
    "num": lambda v: f"{v:.4f}",
    "bps": lambda v: f"{v:.2f} bps",
    "pctnum": lambda v: f"{v:.3f} %",
    "bool": lambda v: "true" if v else "false",
    "text": lambda v: str(v),
}


def display(kind, value, lo=None, hi=None, p_raw=None, p_holm=None, decision=None) -> str:
    f = KINDS[kind]
    parts = [f(value)] if value is not None else []
    if lo is not None and hi is not None:
        parts.append(f"[{f(lo)}, {f(hi)}]")
    if p_raw is not None:
        parts.append(f"p={KINDS['p'](p_raw)}")
    if p_holm is not None:
        parts.append(f"Holm p={KINDS['p'](p_holm)}")
    if decision is not None:
        parts.append(decision)
    return " ".join(parts)


# ---------------------------------------------------------------- row specs (fixed order)
def spec(section, test_id, label, metric, kind, value=None, *, scope="all pairs", pair="", horizon="", n=None, ci=None, p_raw=None,
         p_holm=None, decision=None):
    return dict(section=section, test_id=test_id, label=label, scope=scope, pair=pair, horizon=horizon, metric=metric, kind=kind,
                paths={"value": value, "n": n, "ci_low": ci[0] if ci else None, "ci_high": ci[1] if ci else None,
                       "p_raw": p_raw, "p_holm": p_holm, "decision": decision})


def specs() -> list:
    P, E = "primary", "exploratory"
    s = []
    # ---- primary block (pre-registered, h=24, all pairs)
    s += [
        spec(P, "kronos_accuracy", "Kronos accuracy at 24 bars, all pairs; day-block bootstrap interval", "accuracy", "pct", "primary.accuracy",
             horizon=24, n="primary.n", ci=("primary.ci_accuracy[0]", "primary.ci_accuracy[1]")),
        spec(P, "kronos_accuracy_naive_interval", "Kronos accuracy at 24 bars, naive binomial interval (ignores clustering)", "accuracy", "pct",
             "primary.accuracy", horizon=24, n="primary.n", ci=("primary.naive_binomial_ci95[0]", "primary.naive_binomial_ci95[1]")),
        spec(P, "kronos_correct_calls", "Number of correct Kronos calls at 24 bars", "k_correct", "int", "primary.k_correct", horizon=24, n="primary.n"),
        spec(P, "forecast_days", "Number of forecast days in the analysis set", "n_days", "int", "primary.n_days", horizon=24),
        spec(P, "always_up_accuracy", "Always-up accuracy at 24 bars (share of analysis-set origins whose label is up)", "accuracy", "pct",
             "primary.always_up_accuracy", horizon=24, n="primary.n"),
        spec(P, "accuracy_difference", "Kronos accuracy minus always-up accuracy; day-block bootstrap interval", "accuracy_difference", "pp_frac",
             "primary.accuracy_diff", horizon=24, n="primary.n", ci=("primary.ci_diff[0]", "primary.ci_diff[1]")),
        spec(P, "H1_vs_coin_flip", "H1: Kronos accuracy against a coin flip (exact two-sided binomial test)", "accuracy", "pct", "primary.accuracy",
             horizon=24, n="primary.n", p_raw="primary.p_h1_raw", p_holm="primary.p_h1_holm", decision="primary.decision_h1"),
        spec(P, "H1_largest_edge_not_ruled_out", "H1: largest edge over a coin flip not ruled out (upper end of the interval)", "edge_fraction",
             "pp_frac", "primary.largest_edge_not_ruled_out_h1", horizon=24, n="primary.n"),
        spec(P, "H2_vs_always_up", "H2: Kronos against always-up (exact two-sided McNemar test)", "accuracy_difference", "pp_frac",
             "primary.accuracy_diff", horizon=24, n="primary.n", p_raw="primary.p_h2_raw", p_holm="primary.p_h2_holm", decision="primary.decision_h2"),
        spec(P, "H2_largest_gain_not_ruled_out", "H2: largest gain over always-up not ruled out (upper end of the interval)", "gain_fraction",
             "pp_frac", "primary.largest_gain_vs_always_up_not_ruled_out_h2", horizon=24, n="primary.n"),
        spec(P, "headline", "Pre-registered decision lines", "decision_text", "text", None, horizon=24, n="primary.n", decision="primary.headline"),
        spec(P, "underpowered", "Underpowered flag (analysis set smaller than the pre-registered threshold)", "underpowered", "bool",
             "primary.underpowered", horizon=24, n="primary.n"),
        spec(P, "kronos_down_calls", "Number of Kronos down-calls", "count", "int", "primary.kronos_down_calls_D", horizon=24, n="primary.n"),
        spec(P, "down_calls_correct", "Down-calls that were correct", "count", "int", "primary.down_calls_correct", horizon=24,
             n="primary.kronos_down_calls_D"),
        spec(P, "down_calls_share_correct", "Share of Kronos down-calls that were correct", "share", "pct", "primary.share_correct_down_calls",
             horizon=24, n="primary.kronos_down_calls_D"),
        spec(P, "discordant_kronos_right", "Discordant pairs: Kronos right, always-up wrong", "count", "int",
             "primary.discordant_kronos_right_alwaysup_wrong", horizon=24),
        spec(P, "discordant_kronos_wrong", "Discordant pairs: Kronos wrong, always-up right", "count", "int",
             "primary.discordant_kronos_wrong_alwaysup_right", horizon=24),
        spec(P, "bootstrap_resamples", "Bootstrap resamples of forecast days", "count", "int", "primary.boot_B", horizon=24),
        spec(P, "bootstrap_seed", "Bootstrap random seed", "seed", "int", "primary.boot_seed", horizon=24),
    ]
    for key, text in (("n_total", "Origins in forecasts.jsonl"), ("n_status_ok", "Origins with status ok"),
                      ("n_status_not_ok", "Origins with a status other than ok"),
                      ("n_missing_actual_among_ok", "Origins with a missing actual price among status ok"),
                      ("label_zero_excluded", "Origins excluded because the label is 0"),
                      ("signal_zero_excluded", "Origins excluded because the signal is 0"), ("n_used", "Origins in the analysis set")):
        s.append(spec(P, f"exclusions_h24_{key}", f"Exclusions at 24 bars: {text}", "count", "int", f"primary.exclusions_h24.{key}", horizon=24))
    for i in range(3):
        base = f"power.rows[{i}]"
        s.append(spec(P, f"power_row{i + 1}_min_edge", "Power table: smallest detectable edge at the planned analysis-set size", "min_detectable_edge_pp",
                      "pp", f"{base}.min_detectable_edge_pp", horizon=24, n=f"{base}.n"))
        s.append(spec(P, f"power_row{i + 1}_accuracy_needed", "Power table: accuracy needed at the planned analysis-set size", "accuracy_needed",
                      "pct", f"{base}.accuracy_needed", horizon=24, n=f"{base}.n"))
    s.append(spec(P, "power_down_calls_min_shift", "Smallest detectable shift in the share of correct down-calls", "min_detectable_shift_pp", "pp",
                  "power.min_detectable_shift_down_calls_pp", horizon=24, n="power.D"))
    # ---- exploratory
    s.append(spec(E, "power_at_scored_n_min_edge", "Power at the analysis-set size actually scored: smallest detectable edge", "min_detectable_edge_pp",
                  "pp", "power_at_actual_N.rows[0].min_detectable_edge_pp", horizon=24, n="power_at_actual_N.rows[0].n"))
    s.append(spec(E, "power_at_scored_n_accuracy_needed", "Power at the analysis-set size actually scored: accuracy needed", "accuracy_needed", "pct",
                  "power_at_actual_N.rows[0].accuracy_needed", horizon=24, n="power_at_actual_N.rows[0].n"))
    for h in (1, 4):
        k = f"h{h}"
        base = f"exploratory_accuracy_by_horizon.{k}"
        s += [spec(E, f"accuracy_h{h}", f"Kronos accuracy at {h} bar{'s' if h > 1 else ''}, all pairs", "accuracy", "pct", f"{base}.accuracy", horizon=h, n=f"{base}.n"),
              spec(E, f"correct_calls_h{h}", f"Correct Kronos calls at {h} bar{'s' if h > 1 else ''}", "k_correct", "int", f"{base}.k_correct", horizon=h, n=f"{base}.n"),
              spec(E, f"label_zero_h{h}", f"Origins excluded at {h} bar{'s' if h > 1 else ''} because the label is 0", "count", "int",
                   f"{base}.label_zero_excluded", horizon=h), spec(E, f"signal_zero_h{h}", f"Origins excluded at {h} bar{'s' if h > 1 else ''} because the signal is 0",
                   "count", "int", f"{base}.signal_zero_excluded", horizon=h)]
        for key, text in (("n_total", "Origins in forecasts.jsonl"), ("n_status_ok", "Origins with status ok"),
                          ("n_status_not_ok", "Origins with a status other than ok"),
                          ("n_missing_actual_among_ok", "Origins with a missing actual price among status ok"),
                          ("label_zero_excluded", "Origins excluded because the label is 0"),
                          ("signal_zero_excluded", "Origins excluded because the signal is 0"), ("n_used", "Origins in the analysis set")):
            s.append(spec(E, f"exclusions_h{h}_{key}", f"Exclusions at {h} bar{'s' if h > 1 else ''}: {text}", "count", "int", f"exclusions.{k}.{key}", horizon=h))
    for p in PAIRS:
        base = f"exploratory_by_pair.{p}"
        s += [spec(E, f"accuracy_pair_{p}", f"Kronos accuracy at 24 bars for {p}", "accuracy", "pct", f"{base}.accuracy", scope="pair", pair=p, horizon=24, n=f"{base}.n"),
              spec(E, f"correct_calls_pair_{p}", f"Correct Kronos calls at 24 bars for {p}", "k_correct", "int", f"{base}.k_correct", scope="pair", pair=p, horizon=24, n=f"{base}.n")]
    for st in (1, 2, 3, 4):
        base = f"exploratory_by_stage.{st}"
        s += [spec(E, f"accuracy_stage_{st}", f"Kronos accuracy at 24 bars for stage {st} origins, all pairs", "accuracy", "pct", f"{base}.accuracy", horizon=24, n=f"{base}.n"),
              spec(E, f"correct_calls_stage_{st}", f"Correct Kronos calls at 24 bars for stage {st} origins, all pairs", "k_correct", "int", f"{base}.k_correct", horizon=24, n=f"{base}.n")]
    for h in (1, 4, 24):
        base = f"exploratory_persistence_baseline.h{h}"
        s += [spec(E, f"persistence_accuracy_h{h}", f"Persistence baseline accuracy at {h} bar{'s' if h > 1 else ''} (sign of the last {h}-bar return), all pairs",
                   "accuracy", "pct", f"{base}.accuracy", horizon=h, n=f"{base}.n"),
              spec(E, f"persistence_correct_h{h}", f"Correct persistence calls at {h} bar{'s' if h > 1 else ''}", "k_correct", "int", f"{base}.k_correct", horizon=h, n=f"{base}.n")]
    for h in (1, 4, 24):
        base = f"exploratory_naive_magnitude_error.h{h}"
        s += [spec(E, f"magnitude_error_kronos_h{h}", f"Kronos mean absolute percentage error of the mean forecast at {h} bar{'s' if h > 1 else ''}", "mean_abs_pct_error", "pctnum",
                   f"{base}.kronos_mean_abs_pct_error", horizon=h, n=f"{base}.n"),
              spec(E, f"magnitude_error_last_value_h{h}", f"Naive last-value mean absolute percentage error at {h} bar{'s' if h > 1 else ''}", "mean_abs_pct_error", "pctnum",
                   f"{base}.naive_last_value_mean_abs_pct_error", horizon=h, n=f"{base}.n")]
    for h in (1, 4, 24):
        base = f"exploratory_brier.h{h}"
        s += [spec(E, f"brier_kronos_h{h}", f"Brier score of p_up at {h} bar{'s' if h > 1 else ''}", "brier", "num", f"{base}.brier_p_up", horizon=h, n=f"{base}.n"),
              spec(E, f"brier_constant_h{h}", f"Brier score of the constant 0.5 forecast at {h} bar{'s' if h > 1 else ''}", "brier", "num", f"{base}.brier_constant_half", horizon=h, n=f"{base}.n"),
              spec(E, f"brier_difference_h{h}", f"Brier score difference at {h} bar{'s' if h > 1 else ''}, Kronos minus constant", "brier_difference", "num",
                   f"{base}.difference_kronos_minus_constant", horizon=h, n=f"{base}.n")]
    return s


def calibration_specs(res) -> list:
    out = []
    for i, row in enumerate(res["exploratory_calibration_h24"]):
        base = f"exploratory_calibration_h24[{i}]"
        out.append(spec("exploratory", f"calibration_h24_k{row['k']}",
                        f"Calibration at 24 bars: share of origins that closed up when {row['k']} of 11 samples closed above the last close",
                        "frac_up", "pct", f"{base}.frac_up", horizon=24, n=f"{base}.n"))
    return out


def cost_specs(res) -> list:
    base = "exploratory_cost_check"
    out = [spec("exploratory", "cost_mean_gross_return", "Cost-aware check: mean gross return per trade (position +1 if p_up_24 above 0.5, else -1)", "mean_gross_return_bps", "bps",
                f"{base}.mean_gross_return_bps", horizon=24, n=f"{base}.n"),
           spec("exploratory", "cost_breakeven_fee", "Cost-aware check: break-even per-side fee", "breakeven_per_side_fee_bps", "bps",
                f"{base}.breakeven_per_side_fee_bps", horizon=24, n=f"{base}.n")]
    for fee in res[base]["grid_mean_net_return_bps"]:
        out.append(spec("exploratory", f"cost_net_return_fee_{fee}", f"Cost-aware check: mean net return per trade with a per-side fee of {fee} bps",
                        "mean_net_return_bps", "bps", f"{base}.grid_mean_net_return_bps.{fee}", horizon=24, n=f"{base}.n"))
    return out


# ---------------------------------------------------------------- rows
def build_rows(res: dict) -> list:
    rows = []
    for sp in specs() + calibration_specs(res) + cost_specs(res):
        got = {k: (get(res, p) if p else None) for k, p in sp["paths"].items()}
        status = sp["section"]
        cols = {"section": sp["section"], "test_id": sp["test_id"], "label": sp["label"], "scope": sp["scope"], "pair": sp["pair"],
                "horizon_bars": sp["horizon"], "metric": sp["metric"], "n": "" if got["n"] is None else fmt_full(got["n"]),
                "value": "" if got["value"] is None else fmt_full(got["value"]),
                "ci_low": "" if got["ci_low"] is None else fmt_full(got["ci_low"]),
                "ci_high": "" if got["ci_high"] is None else fmt_full(got["ci_high"]),
                "p_raw": "" if got["p_raw"] is None else fmt_full(got["p_raw"]),
                "p_holm": "" if got["p_holm"] is None else fmt_full(got["p_holm"]),
                "decision": "" if got["decision"] is None else got["decision"], "status": status}
        cols["display"] = display(sp["kind"], got["value"], got["ci_low"], got["ci_high"], got["p_raw"], got["p_holm"],
                                  got["decision"] if sp["kind"] != "text" else None) if (got["value"] is not None or sp["kind"] == "text") else ""
        if sp["kind"] == "text":
            cols["display"] = got["decision"]
        cols["source_key"] = "; ".join(f"{k}={p}" for k, p in sp["paths"].items() if p)
        rows.append(cols)
    return rows


# ---------------------------------------------------------------- data dictionary (quotes taken from PREREGISTRATION.md)
def prereg_bullets(text: str, section: int) -> list:
    out, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^## (\d+)\.", line)
        if m:
            cur = int(m.group(1)); continue
        if cur == section and line.startswith("- "):
            out.append(line[2:].strip())
    return out


def find(bullets, start):
    hits = [b for b in bullets if b.replace("**", "").startswith(start)]
    assert len(hits) == 1, (start, hits)
    return hits[0]


COLUMN_DOC = [
    ("section", "primary for the pre-registered block, exploratory for everything else."),
    ("test_id", "Stable identifier of the figure."),
    ("label", "Plain-English description of the figure."),
    ("scope", "all pairs, or pair when the row is for one trading pair."),
    ("pair", "The trading pair when scope is pair; blank otherwise."),
    ("horizon_bars", "Forecast horizon in hourly bars, where it applies."),
    ("metric", "What the value measures."),
    ("n", "Number of origins (or calls) behind the figure, where it applies."),
    ("value", "The figure, at full precision as stored in results.json; blank where not applicable."),
    ("ci_low", "Lower end of the interval, full precision; blank where not applicable."),
    ("ci_high", "Upper end of the interval, full precision; blank where not applicable."),
    ("p_raw", "Raw p-value of the exact test, full precision; blank where not applicable."),
    ("p_holm", "Holm-adjusted p-value, full precision; blank where not applicable."),
    ("decision", "The pre-registered decision text, unchanged; blank where not applicable."),
    ("status", "primary or exploratory. Every row outside the primary block is exploratory."),
    ("display", "A human-readable string, rounded once for display. Use value, ci_low, ci_high, p_raw and p_holm for analysis."),
    ("source_key", "Where each column came from inside results.json, as name=key.path pairs separated by semicolons; [i] indexes a list."),
]


def dictionary_rows(prereg: str, res: dict, rows: list) -> list:
    s6, s7 = prereg_bullets(prereg, 6), prereg_bullets(prereg, 7)
    q_label = find(s6, "Forecast bar h opens at")
    q_signal = find(s6, "`m_h` is the mean")
    q_pup = find(s6, "`p_up_h` is")
    q_n = find(s7, "Analysis set N")
    q_h1, q_h2 = find(s7, "H1:"), find(s7, "H2:")
    q_boot = find(s7, "Bootstrap:")
    q_holm = find(s7, "Multiplicity:")
    q_rule = find(s7, "Decision rule:")
    S6, S7 = "PREREGISTRATION.md section 6", "PREREGISTRATION.md section 7"
    ex = "Exploratory; not pre-registered. Uses the definitions quoted here."
    meta = {
        "kronos_accuracy": (q_n + " | " + q_boot, S7), "kronos_accuracy_naive_interval": (q_boot + " The naive interval treats origins as independent: \"The exact tests treat origins as independent.\"", S7),
        "kronos_correct_calls": (q_signal + " | " + q_label, S6), "forecast_days": (q_boot, S7), "always_up_accuracy": (q_h2, S7),
        "accuracy_difference": (q_boot, S7), "H1_vs_coin_flip": (q_h1 + " | " + q_holm, S7), "H1_largest_edge_not_ruled_out": (q_rule, S7),
        "H2_vs_always_up": (q_h2 + " | " + q_holm, S7), "H2_largest_gain_not_ruled_out": (q_rule, S7), "headline": (q_rule, S7),
        "underpowered": ("see PREREGISTRATION.md section 8 (Power)", "PREREGISTRATION.md section 8"),
        "kronos_down_calls": (q_h2, S7), "down_calls_correct": (q_h2, S7), "down_calls_share_correct": (q_h2, S7),
        "discordant_kronos_right": (q_h2, S7), "discordant_kronos_wrong": (q_h2, S7), "bootstrap_resamples": (q_boot, S7), "bootstrap_seed": (q_boot, S7),
    }
    out = []
    for name, doc in COLUMN_DOC:
        out.append({"kind": "column", "name": name, "definition": doc, "quoted_from": ""})
    seen = {}
    for r in rows:
        tid = r["test_id"]
        if tid in seen:
            continue
        seen[tid] = True
        if tid in meta:
            quote, src = meta[tid]
        elif tid.startswith("exclusions_h24"):
            quote, src = q_n + " | " + q_label, f"{S7}; {S6}"
        elif tid.startswith("power"):
            quote, src = "Pre-registered power table; see PREREGISTRATION.md section 8.", "PREREGISTRATION.md section 8"
        elif tid.startswith("cost_"):
            note = res["exploratory_cost_check"]["note"]
            quote, src = ex + " results.json note: \"" + note + "\"", "PREREGISTRATION.md section 9; results.json"
        elif tid.startswith("calibration"):
            quote, src = ex + " " + q_pup, f"{S6}; PREREGISTRATION.md section 9"
        elif tid.startswith("brier"):
            quote, src = ex + " " + q_pup, f"{S6}; PREREGISTRATION.md section 9"
        else:
            quote, src = ex + " " + q_signal + " | " + q_label, f"{S6}; PREREGISTRATION.md section 9"
        out.append({"kind": "test_id", "name": tid, "definition": r["label"] + ". " + quote, "quoted_from": src})
    for metric in sorted({r["metric"] for r in rows}):
        out.append({"kind": "metric", "name": metric, "definition": "Value type used in the metric column; see the test_id rows for its definition.", "quoted_from": ""})
    return out


README = """# Kronos Lab: results export

These files are a flat copy of the figures in `results/final/results.json`. Nothing here is a new
statistic: every figure is read from that file by the key path in the `source_key` column.

- `results_summary.csv`: one row per reported figure. Full precision in `value`, `ci_low`, `ci_high`, `p_raw`
  and `p_holm`; `display` is rounded once for reading.
- `data_dictionary.csv`: one row per column, per `test_id` and per `metric`, quoting the wording of
  `PREREGISTRATION.md` sections 6 and 7 where it applies.

All rows except the primary block are exploratory (see the `status` column). The coin-flip band series in
`results.json` is not exported: it is a drawing aid, not a table of figures.

## Provenance

- `results/final/results.json` sha256: `{sha}`
- Pre-registration commit: `{commit}`
- Analysis run once on the origins in `forecasts.jsonl` at the cutoff (see `DEVIATIONS.md`).

## Licence

CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/).
Data: Binance Vision (data.binance.vision); not affiliated with or endorsed by Binance.

Not financial advice.
"""


def write_csv(path: Path, columns: list, rows: list):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for r in rows:
            w.writerow({c: r[c] for c in columns})


def build(root: Path, out: Path) -> dict:
    res_path = root / "results" / "final" / "results.json"
    res_bytes = res_path.read_bytes()
    res = json.loads(res_bytes)
    assert res["data_source"] == "REAL", "export is built from real results only"
    prereg = (root / "PREREGISTRATION.md").read_text()
    rows = build_rows(res)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "results_summary.csv", COLUMNS, rows)
    write_csv(out / "data_dictionary.csv", ["kind", "name", "definition", "quoted_from"], dictionary_rows(prereg, res, rows))
    (out / "README.md").write_text(README.format(sha=hashlib.sha256(res_bytes).hexdigest(), commit=PREREG_COMMIT), encoding="utf-8", newline="\n")
    return {"rows": len(rows)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--out", default="results/export")
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    out = Path(a.out)
    out = (out if out.is_absolute() else root / out).resolve()
    if out == (root / "results" / "final").resolve() or (root / "results" / "runs").resolve() in (out, *out.parents):
        print("REFUSED: output may not go to results/final or results/runs", file=sys.stderr)
        return 3
    info = build(root, out)
    print(f"wrote {info['rows']} rows to {out.relative_to(root) if root in out.parents else out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
