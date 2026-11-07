# Kronos Lab: results export

These files are a flat copy of the figures in `results/final/results.json`. Nothing here is a new
statistic: every figure is read from that file by the key path in the `source_key` column.

- `results_summary.csv`: one row per reported figure. Full precision in `value`, `ci_low`, `ci_high`, `p_raw`
  and `p_holm`; `display` is rounded once for reading.
- `data_dictionary.csv`: one row per column, per `test_id` and per `metric`, quoting the wording of
  `PREREGISTRATION.md` sections 6 and 7 where it applies.

All rows except the primary block are exploratory (see the `status` column). The coin-flip band series in
`results.json` is not exported: it is a drawing aid, not a table of figures.

## Provenance

- `results/final/results.json` sha256: `1128954d9675066c90d9154f902e5e54332189dfbd12cc2c8eff518ecfe3c937`
- Pre-registration commit: `56fcbdee4cb4055eb75669af5e411c45f845994b`
- Analysis run once on the origins in `forecasts.jsonl` at the cutoff (see `DEVIATIONS.md`).

## Licence

CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/).
Data: Binance Vision (data.binance.vision); not affiliated with or endorsed by Binance.

Not financial advice.
