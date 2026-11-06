# Kronos Lab PRD

## Kickoff
1. **What:** A pre-registered test of whether Kronos-small predicts 1-hour crypto candle direction better than a coin flip and trivial baselines, plus a static GitHub Pages site.
2. **Why:** Foundation-model forecasting claims are rarely tested out of sample with fixed hypotheses and honest costs.
3. **How it works:** Hourly spot klines (BTC, ETH, SOL, XRP, BNB, DOGE vs USDT) feed Kronos-small. Predicted direction is scored against baselines with pre-specified tests.
4. **How we build:** Phased. Phase 0 is scaffold and guardrails. Pre-registration is committed before any test-window metric. Tests come before pipeline code.
5. **Where:** Local on a MacBook M2 (8 GB); output is a static site on GitHub Pages with no external CDN.
6. **Resources:** Kronos (MIT, pinned commit), HF weights NeoQuasar/Kronos-small, Binance Vision public data (CC BY-NC-SA 4.0).

## Requirements traceability

| ID | Requirement | Testable acceptance criterion | Phase | Evidence path |
|---|---|---|---|---|
| REQ-P1 | PENDING: spec not pasted yet | PENDING | PENDING | PENDING |
| REQ-P2 | PENDING: spec not pasted yet | PENDING | PENDING | PENDING |
| REQ-P3 | PENDING: spec not pasted yet | PENDING | PENDING | PENDING |
| REQ-M1 | Pre-registration committed before the test run | PREREGISTRATION.md commit timestamp precedes the first commit of any test-window metric output | TBD | PREREGISTRATION.md, git log |
| REQ-M2 | Leakage unit test | A test fails if any input feature at time t uses data from t+1 or later | TBD | tests/test_leakage.py |
| REQ-M3 | Baselines: coin flip, always-up, persistence, naive last-value | Each baseline has a function and a unit test on a hand-built series | TBD | tests/test_baselines.py, results/ |
| REQ-M4 | Exact binomial test vs 0.5 | Matches scipy.stats.binomtest on fixed fixtures | TBD | tests/test_stats.py, results/ |
| REQ-M5 | Paired McNemar test vs always-up | Matches a hand-computed 2x2 fixture | TBD | tests/test_stats.py, results/ |
| REQ-M6 | Block-bootstrap CI, resampling days across all pairs | CI function resamples whole days jointly across pairs; seed fixed; unit-tested | TBD | tests/test_stats.py, results/ |
| REQ-M7 | Holm correction across the 2 co-primary tests | Adjusted p-values match a hand-computed example | TBD | tests/test_stats.py, results/ |
| REQ-M8 | Cost-aware fee break-even | Break-even fee is computed from results files and unit-tested | TBD | results/ |
| REQ-M9 | Site pages: fan chart, running score band, results table, game, methodology, limits | Each page exists, renders offline, loads no external scripts or fonts | TBD | site/ |
| REQ-M10 | "Not financial advice" line | Present on every site page and in README | TBD | site/, README.md |
| REQ-M11 | Licence split: MIT code, CC BY-NC-SA data | LICENSE and DATA_LICENSE.md exist; README states MIT covers code only | 0 | LICENSE, DATA_LICENSE.md, README.md |
| REQ-M12 | Every number on README/site comes from results/ | A test scans for numeric literals not backed by a results file | TBD | tests/ |

## Open questions (unverified after steps 1-4)
- REQ-P* rows are empty until Prateek's spec is pasted.
- Python is 3.15.0, newer than the Kronos-pinned dependencies assume. Torch wheel availability for 3.15 on Apple Silicon is unverified (torch not installed in this phase).
- The Kronos requirements pin pandas==2.2.2; the dev venv has pandas 3.1.1. Compatibility is unverified.
- Kronos source has not been read; only file sizes (model/kronos.py 662 lines, model/module.py 570) are known.
- Binance: HEAD returned 200 for all 24 URLs, but file contents, checksums, column format and gaps are unverified (nothing downloaded).
- Binance Vision licence: the CC BY-NC-SA 4.0 assignment comes from the task brief. Not verified against the Terms of Use PDF, which was not read.
- HF: the commits API lists no changed files. The tree endpoint with expand=true reports model.safetensors last changed in commit ac5c409a (2025-06-30T16:44:37Z, "add model"). The weights themselves are not downloaded or hash-verified; LFS oid is in docs/provenance.
- HF API returns license: null for Kronos-small; the model licence is unverified (README.md on HF not read).
- Free disk 66Gi; RAM 8589934592 bytes. Model memory spike is unmeasured.
