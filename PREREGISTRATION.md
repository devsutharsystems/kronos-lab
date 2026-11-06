# Kronos Lab: Pre-registration

## 1. Status and timing

This file is written before the main run. The commit hash of this file is its timestamp. After that commit this file is never edited. Any change goes into `DEVIATIONS.md` with the date, the reason, and whether results had been seen at that point.

## 2. Disclosures

- Price files for the test window were downloaded and checked only for gaps, NaNs and OHLC consistency (`results/data_quality.json`). No returns or labels were computed.
- A 168-row sample of BTCUSDT (2025-10-01 to 2025-10-07) was written to `data/sample/` and its first rows were displayed during development. No analysis was done on it.
- No model forecast exists for any day in the test window.
- The Phase 1 spike used only the example CSV shipped in the Kronos repository (5-minute stock bars).
- The smoke test used the pre-window days 2025-09-24, 2025-09-25 and 2025-09-26 for BTCUSDT and ETHUSDT. It compared nothing with prices.
- The author is aware in general terms of the direction of crypto markets in this period. The pairs, the 24-bar primary horizon and the window were fixed from liquidity, the official demo and data availability, not from outcomes.

## 3. Hypotheses

- **H1:** Kronos direction accuracy at h=24 differs from 0.5.
- **H2:** Kronos direction accuracy at h=24 differs from the accuracy of always-up.

## 4. Data and window

- Six spot pairs: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT, DOGEUSDT. Hourly bars, UTC, closed bars only.
- Source: Binance Vision monthly klines (data.binance.vision), licence CC BY-NC-SA 4.0. All 84 monthly zips were verified against their `.CHECKSUM` files (`results/data_manifest.json`).
- Forecast days: 2025-10-01 to 2026-10-31 UTC, 396 days per pair.
- Origin: 00:00 UTC of the forecast day. Context: the 512 closed bars ending 23:00 UTC of the previous day. Labels: the 24 bars of the forecast day.
- Exclusion rule: any origin with a missing bar in its context or labels is excluded and counted per pair. Nothing is interpolated or filled.

sha256 of the processed series (`data/processed/<PAIR>_1h.csv`):

| pair | sha256 |
|---|---|
| BTCUSDT | `0c026fb0fc3d9b6861e932445e98d647ebd8b79a0d79cb3f7e414aed0afd8e06` |
| ETHUSDT | `eb2fcd78a8ae80d526176ac3bdd838bbec0f01f2e4f1ca1bd2b88ffabf2ac741` |
| SOLUSDT | `4afc02185b6cb92fd29c7582bcc28905bc6ddbb4d3804e3ff7c55202c723f265` |
| XRPUSDT | `da7a18eca084c6c58a76d668990cbae3dd1537870e63dddbd8e5f858593b46a1` |
| BNBUSDT | `a9722ca70861b4dbefc86c8c21ee3bff7085562dada3f53c4359d6c958c5b55e` |
| DOGEUSDT | `39cfe973f984b263b98dfb4c1c7c707f0c80262a6498de43b35b01f7a48ee82b` |

## 5. Model and inference

- Weights: Kronos-small `model.safetensors` sha256 `b082dfcbd8e8c142a725c8bbb99781802f38fec81210e13479effb32b3c3e020`; Kronos-Tokenizer-base `model.safetensors` sha256 `59d85f6af76a2c3b8240ea06cb21db4213b4eeca053f246b23e29cf832fc6bee`. Both match the Hugging Face LFS hashes.
- Kronos code pin: `67b630e67f6a18c9e9be918d9b4337c960db1e9a`.
- `requirements-kronos.txt` sha256 `60788be9929a9ec55ce1bbf34f16c3222f67e3b9cf9d118963ca20ab5ea67b37`.
- Mode: `eval()` on model and tokenizer. Device: MPS only, no CPU fallback.
- Settings: T=1.0, top_p=0.9, top_k at its default (0), lookback 512, pred_len 24, 11 independent `sample_count=1` calls per origin, official `predict()` with `verbose=False`.
- Seed for call k (0..10): `s = int.from_bytes(sha256("KRONOS-LAB-v1|<PAIR>|<YYYY-MM-DD>|<k>").digest()[:4], "big")`, then `torch.manual_seed(s)` before the call.
- Decisions commit: `7676585a6e61928ca811f2bbf2fddf1ac6b89af3` (`docs/DECISIONS.md`). Runner commit: `d2f0b0753781aae185d2b36e0d18abad2f52c1be` (Phase 3a).
- Run-critical files (a change to any of them, to the weights or to the processed CSVs blocks a restart):

| file | sha256 |
|---|---|
| `kronos_lab/runner.py` | `461d55ae750aefd2e7631e03f3105ed731bd2a75e225590d3daccf24f1f0c24e` |
| `kronos_lab/kronos_adapter.py` | `2182857eb7853d6c518333ce9709099c13744902e754ce3c0ce28601e0e6b480` |
| `kronos_lab/data.py` | `ad01e2f4834013996f3af1110317b8cfd8ee732bd1732e9cea90633e49d551b8` |
| `docs/DECISIONS.md` | `12bfbf7162232db998fa55a8caeb026b8b3683261eabea72b6f48636a62f8f68` |

`scripts/launch_run.sh` is the sixth run-critical file. It is committed after this file and only loops the runner command.

## 6. Definitions

- `last_close` is the close of the final context bar (the 23:00 bar of the previous day).
- Forecast bar h opens at (h-1):00 UTC of the forecast day. For h in {1, 4, 24}: `actual_h` is the real close of bar h; `label_h = sign(actual_h - last_close)`. Label 0 is excluded for that h and the count is reported.
- `m_h` is the mean over the 11 samples of the predicted close of bar h. `signal_h = sign(m_h - last_close)`; signal 0 is excluded.
- `p_up_h` is the number of samples with predicted close_h > last_close, divided by 11.

## 7. Primary analysis (h=24 only)

- **Analysis set N:** origins with status ok, label_24 != 0 and signal_24 != 0.
- **H1:** exact two-sided binomial test of the number of correct signals against 0.5.
- **H2:** always-up predicts up everywhere. Exact two-sided McNemar test on the discordant pairs. The two discordant counts are reported, together with the number of Kronos down-calls. Discordance can only occur where Kronos calls down: Kronos-right-and-always-up-wrong when signal and label are both down, and Kronos-wrong-and-always-up-right when the signal is down and the label is up.
- **Multiplicity:** Holm correction across H1 and H2 at family alpha 0.05.
- **Bootstrap:** B = 10,000 resamples of forecast days with replacement from the days present in the analysis set. For each drawn day all pairs' origins in the analysis set are taken. numpy `default_rng` seed 20261106. Percentile 95% confidence intervals for (a) Kronos accuracy and (b) Kronos accuracy minus always-up accuracy.
- **Decision rule:**
  - "Edge detected vs coin flip" only if the Holm-adjusted p for H1 is below 0.05 and the lower bound of the bootstrap interval for Kronos accuracy is above 0.5.
  - "Beats always-up" only if the Holm-adjusted p for H2 is below 0.05 and the lower bound of the interval for the difference is above 0.
  - Otherwise the result is reported as "no detectable edge", with the interval's upper bound stated as the largest edge not ruled out.
  - The exact tests treat origins as independent. Cross-pair correlation makes them optimistic, which is why the bootstrap condition is also required. Both are reported even when only one passes.
  - If the H1 Holm-adjusted p is below 0.05 and Kronos accuracy is below 0.5, report 'worse than a coin flip', not an edge. If the H2 Holm-adjusted p is below 0.05 and Kronos is worse than always-up, report 'worse than always-up'.

## 8. Power

Minimum detectable accuracy edge is about (z(1 - 0.025/2) + z(0.80)) x 0.5 / sqrt(N) = 1.5415 / sqrt(N), where the z-sum is 3.0830. This uses alpha 0.025 two-sided (the Holm worst case), 80% power and independent origins. Effective N is lower because of cross-pair correlation.

| N | minimum detectable edge | accuracy needed |
|---|---|---|
| 594 | 6.32 pp | 56.32% |
| 1188 | 4.47 pp | 54.47% |
| 2376 | 3.16 pp | 53.16% |

If the analysis set has fewer than 1188 origins, the headline must say "underpowered".

H2 draws its information only from Kronos down-calls (D). The final report states D and the smallest detectable shift in the share of correct down-calls, about 1.5415/sqrt(D), computed in code.

## 9. Exploratory only

Everything in this section is labelled "exploratory" wherever it is reported.

- Accuracy at h=1 and h=4.
- Results per pair and per stage.
- A persistence baseline at the same horizon (sign of the last h-bar return).
- Naive last-value magnitude error.
- Brier score of `p_up` against the constant 0.5, and a calibration table over the 12 levels k/11.
- Cost-aware check: position = +1 if `p_up_24` > 0.5 else -1; gross return = position x (actual_24 / last_close - 1); break-even per-side fee f* in basis points where the mean gross return equals 2 f*; and an illustrative grid of 0, 5, 10 and 20 bps. This is illustrative only. Spot cannot be shorted without margin, funding and slippage are ignored, and no fee schedule is cited.
- Site visuals only: the coin-flip band is drawn from 1,000 simulated fair-coin paths with a fixed seed. It is an illustration; inference is in section 7.

## 10. Run protocol

- Stage order and within-stage order are those of the runner: stages 1 to 4 by day index, and within a stage ascending hex of `sha256("KRONOS-LAB-v1|order|<stage>|<PAIR>|<YYYY-MM-DD>")`.
- The run stops at the cutoff 2026-11-07T03:30:00Z (09:00 IST) or when all 2376 origins are complete, whichever comes first.
- The analysis set is the origins in `forecasts.jsonl` at the cutoff with all 11 samples complete.
- No early stopping on results. No re-runs. NaN origins are excluded and counted.
- MPS only. Resume is allowed and every start is logged in `restarts.log`.
- The runner never reads label prices.
- Analysis code is run on real forecasts only after the run has stopped, meaning results/runs/DONE exists (cutoff passed or all 2376 origins complete). Before then it is run only on synthetic data. No accuracy figure is computed or viewed on real forecasts before that point.

## 11. Limits

- The stock `KronosPredictor` does not call `.eval()`. The authors' own tests (`tests/test_kronos_regression.py` lines 64-65 and `tests/data/generate_regression_output.py` lines 49-50) call `.eval()` on both objects before `predict()`, with `top_k=1, top_p=1.0` on CPU. Their examples do not.
- `clip=5` is applied twice (once in `predict`, once in `auto_regressive_inference`).
- 11 samples were chosen by compute budget, while the paper reports gains from more samples.
- The dates of the weight files are file dates, not the authors' training cutoff: `model.safetensors` last changed 2025-06-30T16:44:37Z (Kronos-small) and 2025-06-30T17:04:10Z (tokenizer); the window starts 2025-10-01. The training cutoff is unconfirmed (GitHub issue #265, unanswered as far as the author knows).
- One window, one model size, crypto only.
- Cross-pair correlation makes the effective sample smaller than N.
- Not financial advice.
