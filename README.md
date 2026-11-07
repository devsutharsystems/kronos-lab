# Kronos Lab

A pre-registered test of whether the direction accuracy of the Kronos-small forecasting model, on 1-hour crypto candles, differs from a coin flip (H1) and from always predicting "up" (H2). The plan, the hashes and the code were fixed before the main run. This file is generated from the result files by `scripts/build_readme.py`; nothing in it is typed by hand.

## Result

Kronos-small was tested on forecast origins at 00:00 UTC for 396 days and 6 pairs, 2376 planned in total. The analysis set has 2028 origins (see below). At the primary horizon of 24 hours ahead, the pre-registered rule gave **H1 (versus a coin flip): no detectable edge** and **H2 (versus always-up): no detectable edge**.

Kronos direction accuracy was 51.0% (1035 of 2028), with a 95% day-block bootstrap interval of 47.9% to 54.2%. The largest edge over a coin flip that the interval does not rule out is +4.2 percentage points. Always-up accuracy was 47.3%; Kronos minus always-up was +3.7 percentage points (95% interval -1.7 to +9.0), and the largest gain over always-up not ruled out is +9.0 percentage points. This describes this window, this model size and this sample size; smaller effects than these intervals can show are not excluded.

**Note on H2.** The exact test's Holm-adjusted p-value versus always-up was 0.046, which is below 0.05 on its own. The pre-registered rule also requires the day-block interval for the accuracy difference to exclude zero; it runs from -1.7 to +9.0 percentage points, so no edge is declared. Both numbers are reported. The exact tests treat origins as independent, which is why the interval condition is part of the rule.

**Always-up baseline (descriptive, not pre-registered).** Always-up accuracy is the share of analysis-set origins that closed up. At 47.3% it is below one half: this window had more down days than up days, so always-up is a weak baseline here.

Exploratory figures (per pair, per horizon and others) are on the site's Evidence page and in `results/final/results.json`. They are labelled exploratory and are not part of this summary.

## Why the run stopped early

The pre-registered cutoff (2026-11-07T03:30:00Z) passed while the run was paused, so it stopped with 2031 of 2376 origins (345 never run). The runner was started 3 times: it was interrupted by SIGINT and resumed 2 times, as the restart log records. The analysis set is exactly the origins present in `forecasts.jsonl` at the cutoff; 2028 of them have a non-zero label and signal. Dates, counts and the file hash are in `DEVIATIONS.md`, whose entries are linked below. Nothing in the definitions, tests, seeds or thresholds changed.

## Who is this for, and what can you do with it

- **Curious readers** get a reality check on claims that AI models can predict prices: one model, one window, a result reported as it came out.
- **Students** get a worked template for a pre-registered evaluation: a plan committed before the run, a decision rule, a deviations log, and an analysis run once.
- **People who want to check the work** can verify the pre-registration commit, the file hashes and the code. The analysis can be rerun if the forecast file is obtained (its sha256 is in `DEVIATIONS.md`). Regenerating the forecasts needs Apple-silicon MPS and several hours, and bit-for-bit reproduction on other hardware is not claimed.

What this does not show: it covers one time window, one model size, and crypto pairs only. Small effects are not excluded. It is not a trading tool.

## The question, and what was fixed beforehand

Quoted from `PREREGISTRATION.md`:

- H1: Kronos direction accuracy at h=24 differs from 0.5.
- H2: Kronos direction accuracy at h=24 differs from the accuracy of always-up.
- Six spot pairs: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT, DOGEUSDT. Hourly bars, UTC, closed bars only.
- Forecast days: 2025-10-01 to 2026-10-31 UTC, 396 days per pair.
- Origin: 00:00 UTC of the forecast day. Context: the 512 closed bars ending 23:00 UTC of the previous day. Labels: the 24 bars of the forecast day.
- Weights: Kronos-small `model.safetensors` sha256 `b082dfcbd8e8c142a725c8bbb99781802f38fec81210e13479effb32b3c3e020`; Kronos-Tokenizer-base `model.safetensors` sha256 `59d85f6af76a2c3b8240ea06cb21db4213b4eeca053f246b23e29cf832fc6bee`. Both match the Hugging Face LFS hashes.
- Kronos code pin: `67b630e67f6a18c9e9be918d9b4337c960db1e9a`.
- `requirements-kronos.txt` sha256 `60788be9929a9ec55ce1bbf34f16c3222f67e3b9cf9d118963ca20ab5ea67b37`.

Data checks (`results/data_quality.json`): 6 pairs, interval 1h, 0 missing bars.

The pre-registration was committed before the main run: [`PREREGISTRATION.md` at commit 56fcbdee](https://github.com/devsutharsystems/kronos-lab/blob/56fcbdee4cb4055eb75669af5e411c45f845994b/PREREGISTRATION.md). Changes after that point are in [`DEVIATIONS.md`](DEVIATIONS.md): [run-critical file count](https://github.com/devsutharsystems/kronos-lab/commit/10bb92f7e97c51909255326142f652d5994c7340) and [run closed after the cutoff](https://github.com/devsutharsystems/kronos-lab/commit/2edd4ed8228b5e79be13abff8d2eede1030683a7).

## How to reproduce

The pieces that can be checked without the forecasts: the pre-registration commit, the expected hashes below, and the code. Commands, in order:

```bash
bash scripts/fetch_kronos.sh                                   # Kronos source at the pinned commit (online, once)
python3.12 -m venv .venv-kronos && .venv-kronos/bin/pip install -r requirements-kronos.txt
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
source scripts/env.sh && .venv-kronos/bin/python scripts/download_weights.py   # weights (online, once)
.venv/bin/python -I scripts/download_data.py fetch             # Binance Vision files, checksum-verified
.venv/bin/python -I scripts/download_data.py build             # processed CSVs and the data-quality report
caffeinate -dimsu bash scripts/launch_run.sh                   # the main run: Apple-silicon MPS only, several hours
.venv/bin/python scripts/analyze.py --root . --out results/final
.venv/bin/python scripts/build_export.py
.venv/bin/python scripts/build_site_data.py --root . --out site/data
python3 scripts/serve_site.py --port 8010
```

The run needs MPS: the runner refuses to start without it, and MPS and CPU outputs differ. `analyze.py` refuses to run until `results/runs/DONE` exists, and it copies that file's contents into `results.json`, so a rerun with its own `DONE` file will differ from the committed `results.json` in that timestamp.

Expected hashes (sha256):

| File | sha256 |
|---|---|
| Processed series BTCUSDT | `0c026fb0fc3d9b6861e932445e98d647ebd8b79a0d79cb3f7e414aed0afd8e06` |
| Processed series ETHUSDT | `eb2fcd78a8ae80d526176ac3bdd838bbec0f01f2e4f1ca1bd2b88ffabf2ac741` |
| Processed series SOLUSDT | `4afc02185b6cb92fd29c7582bcc28905bc6ddbb4d3804e3ff7c55202c723f265` |
| Processed series XRPUSDT | `da7a18eca084c6c58a76d668990cbae3dd1537870e63dddbd8e5f858593b46a1` |
| Processed series BNBUSDT | `a9722ca70861b4dbefc86c8c21ee3bff7085562dada3f53c4359d6c958c5b55e` |
| Processed series DOGEUSDT | `39cfe973f984b263b98dfb4c1c7c707f0c80262a6498de43b35b01f7a48ee82b` |
| Kronos-small weights (model.safetensors) | `b082dfcbd8e8c142a725c8bbb99781802f38fec81210e13479effb32b3c3e020` |
| Kronos-Tokenizer-base weights (model.safetensors) | `59d85f6af76a2c3b8240ea06cb21db4213b4eeca053f246b23e29cf832fc6bee` |
| requirements-kronos.txt | `60788be9929a9ec55ce1bbf34f16c3222f67e3b9cf9d118963ca20ab5ea67b37` |
| results/runs/forecasts.jsonl (not in the repository) | `e4018459424723023204b6a111c3fa6887e71057c9bc9578d95325623a56fc8b` |
| results/final/results.json | `1128954d9675066c90d9154f902e5e54332189dfbd12cc2c8eff518ecfe3c937` |

## Limits

Quoted from `PREREGISTRATION.md`, section 11:

- The stock `KronosPredictor` does not call `.eval()`. The authors' own tests (`tests/test_kronos_regression.py` lines 64-65 and `tests/data/generate_regression_output.py` lines 49-50) call `.eval()` on both objects before `predict()`, with `top_k=1, top_p=1.0` on CPU. Their examples do not.
- `clip=5` is applied twice (once in `predict`, once in `auto_regressive_inference`).
- 11 samples were chosen by compute budget, while the paper reports gains from more samples.
- The dates of the weight files are file dates, not the authors' training cutoff: `model.safetensors` last changed 2025-06-30T16:44:37Z (Kronos-small) and 2025-06-30T17:04:10Z (tokenizer); the window starts 2025-10-01. The training cutoff is unconfirmed (GitHub issue #265, unanswered as far as the author knows).
- One window, one model size, crypto only.
- Cross-pair correlation makes the effective sample smaller than N.
- Not financial advice.

Added for this summary: one time window; one model size; crypto pairs only; cross-pair correlation means the exact tests treat origins as more independent than they are (the day-block interval is the check); 11 samples per origin; and the weight-file dates are file dates, not the authors' training cutoff.

## Repository layout

- `PREREGISTRATION.md`, `DEVIATIONS.md`: the plan and the dated changes.
- `kronos_lab/`: runner, adapter, data and analysis code. `scripts/`: download, run, analysis, export, README and site builders, and `serve_site.py` for local viewing.
- `results/final/`: the analysis output, produced once. `results/export/`: a flat CSV copy of those figures with a data dictionary.
- `results/data_quality.json`, `results/data_manifest.json`: data checks and file records.
- `site/`: the static site (plain HTML, CSS and JavaScript, no external resources). `site/data/` holds the data it loads and the download files.
- `tests/`: Python and node tests. `docs/`: decisions log, product notes, provenance records.
- `third_party/`: the Kronos licence and the pin record; the Kronos source itself is fetched, not committed.

## Licences

- Code: MIT, see `LICENSE`. The Kronos code is MIT too; its notice is in `third_party/KRONOS_LICENSE`.
- Data sample, `results/` (including `results/export/`) and `site/data/`: CC BY-NC-SA 4.0, see `DATA_LICENSE.md`.
- Data: Binance Vision (data.binance.vision); not affiliated with or endorsed by Binance. This project is not affiliated with the Kronos authors.

Not financial advice.
