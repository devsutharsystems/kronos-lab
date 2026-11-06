"""Fetch/verify Binance Vision 1h klines and build processed series + data-quality report.

Usage (dev venv, isolated mode OK):  .venv/bin/python -I scripts/download_data.py fetch|build
Health checks only: row counts, gaps, duplicates, NaNs, OHLC sanity. No returns, no accuracy.
Stops on any non-200, missing file or checksum failure. No other source is ever used.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # needed under `python -I` (isolated mode drops the script dir)

from kronos_lab import data as D  # noqa: E402

SAMPLE_README = """# BTCUSDT 1h sample

`BTCUSDT_1h_sample.csv`: first 7 days of 2025-10 (2025-10-01 00:00 .. 2025-10-07 23:00 UTC), 168 hourly bars.
Columns: timestamps (UTC), open, high, low, close, volume, amount (= Binance quote asset volume).

Data: Binance Vision (data.binance.vision), licensed CC BY-NC-SA 4.0.
Terms: https://data.binance.vision/Binance_Vision-Terms_of_Use.pdf
Not affiliated with or endorsed by Binance. Not financial advice.
"""


def fetch():
    manifest = D.fetch_all()
    out = ROOT / "results" / "data_manifest.json"
    out.write_text(json.dumps({"files": manifest, "count": len(manifest) * 2,
                               "total_zip_bytes": sum(m["bytes"] for m in manifest),
                               "checksum_ok": sum(m["checksum_ok"] for m in manifest)}, indent=1) + "\n")
    print(f"zips: {len(manifest)}  total zip bytes: {sum(m['bytes'] for m in manifest)}  checksum_ok: {sum(m['checksum_ok'] for m in manifest)}")


def build():
    days = D.origin_days()
    report = {"months": D.MONTHS, "interval": D.INTERVAL, "pairs": {}}
    fatal = False
    series_by_pair = {}
    for pair in D.PAIRS:
        s, units = D.build_series(pair)
        rep = D.validate_arrays(s.open_time, s.open, s.high, s.low, s.close, s.volume)
        rep["amount_nan_values"] = int(__import__("numpy").isnan(s.amount).sum())
        rep["timestamp_units_by_month"] = units
        invalid = {}
        for idx, day in enumerate(days):
            why = D.origin_failure_reason(s, D.origin_ts(day))
            if why:
                invalid[day.isoformat()] = {"reason": why, "stage": D.stage_of(idx)}
        rep["invalid_origins"] = {"count": len(invalid), "of": len(days),
                                  "by_stage": {str(k): sum(1 for v in invalid.values() if v["stage"] == k) for k in (1, 2, 3, 4)},
                                  "days": invalid}
        report["pairs"][pair] = rep
        if rep["duplicates"] or rep["out_of_order"]:
            fatal = True  # report and stop: no silent dedup/sort
        series_by_pair[pair] = s
    (ROOT / "results" / "data_quality.json").write_text(json.dumps(report, indent=1) + "\n")
    if fatal:
        print("STOP: duplicates or out-of-order bars found; processed files NOT written. See results/data_quality.json")
        sys.exit(2)
    for pair, s in series_by_pair.items():
        D.write_processed(s, D.PROCESSED_DIR / f"{pair}_1h.csv")
    s = series_by_pair["BTCUSDT"]
    i = int(__import__("numpy").searchsorted(s.open_time, D.to_ms(D.origin_ts(D.WINDOW_START))))
    sample = s.slice(i, i + 168)
    assert D.iso(int(sample.open_time[0])) == "2025-10-01T00:00:00Z" and D.iso(int(sample.open_time[-1])) == "2025-10-07T23:00:00Z"
    D.write_processed(sample, ROOT / "data" / "sample" / "BTCUSDT_1h_sample.csv")
    (ROOT / "data" / "sample" / "README.md").write_text(SAMPLE_README)
    for pair, r in report["pairs"].items():
        print(pair, "rows", r["rows"], r["first_bar"], r["last_bar"], "gaps", len(r["gaps"]), "dups", r["duplicates"],
              "invalid_origins", r["invalid_origins"]["count"], "ok", r["ok"])


if __name__ == "__main__":
    {"fetch": fetch, "build": build}[sys.argv[1]]()
