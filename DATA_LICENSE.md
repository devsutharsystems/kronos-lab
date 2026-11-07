# Data License

The MIT license in `LICENSE` covers the code. The data and result files are covered as follows, group by group.

## Binance-derived data: CC BY-NC-SA 4.0

`data/sample/`, `results/final/`, `results/export/`, `results/data_quality.json`, `results/data_manifest.json` and `site/data/` (which holds the site data and copies of the export files) are derived from Binance Vision datasets. They are licensed under CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/).

Attribution: Data: Binance Vision (data.binance.vision)

Terms of use: https://data.binance.vision/Binance_Vision-Terms_of_Use.pdf

Not affiliated with or endorsed by Binance.

## Provenance records: `docs/provenance/`

Public metadata fetched from the Hugging Face API for the Kronos-small and Kronos-Tokenizer-base model repositories (model-card fields, file lists with sizes and hashes, commit messages), and `binance_head_status.txt`, the HTTP status codes returned by data.binance.vision for the monthly files. It contains no price data. The Hugging Face metadata describes upstream repositories and remains subject to their terms; it is kept as a record of what was checked.

## Spike measurements: `results/spike/` and `docs/spike_report.md`

Measurements from the Phase 1 timing spike: timings, memory figures, array shapes, pass/fail flags, output hashes, and a few aggregate figures (for example the mean absolute difference between two forecasts and the mean close of the input window). The input was the example CSV (5-minute stock bars) shipped in the Kronos repository, which is MIT licensed (`third_party/KRONOS_LICENSE`). These files contain no Binance data and store no price series or forecast series. They are released under the MIT license in `LICENSE`.

## Other

Not financial advice.
