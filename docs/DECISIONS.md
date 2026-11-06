# Decisions locked after the Phase 1 spike

Recorded before any market data is downloaded. No new choices beyond what the spike report supports.

1. **Mode:** `model.eval()` on Kronos and on the tokenizer.
2. **Device:** MPS for the entire run, never mixed with CPU (outputs differ by device). If MPS fails mid-run, resume only on MPS; no CPU fallback for primary results.
3. **Sampling:** official `KronosPredictor.predict()` only, `verbose=False`, `T=1.0`, `top_p=0.9`, `top_k=0`, all other arguments at defaults, lookback 512, pred_len 24, **11 independent `sample_count=1` calls per origin**. `kronos_lab/sampling.py` is NOT used by the run.
4. **Seeds:** `torch.manual_seed(s)` before every call. `s` is a 32-bit value from `hashlib.sha256` over the UTF-8 string `"KRONOS-LAB-v1|<PAIR>|<YYYY-MM-DD>|<k>"` (k = 0..10 is the call index within the origin). Derivation: `s = int.from_bytes(digest[:4], "big")` (first four digest bytes, big-endian). Never Python's built-in `hash()` (salted per process).
5. **Window:** forecast days 2025-10-01..2026-10-31 UTC = 396 days per pair. Origin = 00:00 UTC of the forecast day. Context = the 512 closed bars ending 23:00 UTC of the previous day. Labels = the 24 bars of the forecast day.
6. **Stages by day index i (0..395):** stage 1: `i%8==0` (50 per pair); stage 2: `i%4==0` and not stage 1 (49); stage 3: `i%2==0` and not stages 1-2 (99); stage 4: the odd i (198). Cumulative 50/99/198/396. Ordering within a stage and the clock cutoff are fixed in PREREGISTRATION.md (Phase 3).
7. **Exclusion rule:** any origin with a missing bar in its context or labels is excluded and counted per pair. Never interpolate or fill.
8. **Spike facts** (copied from docs/spike_report.md, generated from results/spike/spike_raw.jsonl):

## Timing and memory (lookback 512, pred_len 24, T=1.0, top_p=0.9, 1 warm-up excluded + 3 repeats, median)

| device | config | sample_count | batch | shape/NaN ok | warm-up s | timed s | median s/call | median s/origin | peak RSS (time -l) GB | peak footprint GB | note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cpu | S1 | 1 | 1 | True/True | 1.22 | 1.23, 1.17, 1.17 | 1.17 | 1.17 | 0.453 | 0.340 |  |
| cpu | S5 | 5 | 1 | True/True | 6.05 | 5.81, 5.87, 5.95 | 5.87 | 5.87 | 0.514 | 0.451 |  |
| cpu | S11 | 11 | 1 | True/True | 13.65 | 14.39, 15.94, 19.62 | 15.94 | 15.94 | 0.651 | 0.653 |  |
| cpu | S21 | 21 | 1 | True/True | 72.51 | 55.17, 43.70, 59.76 | 55.17 | 55.17 | 0.832 | 0.931 |  |
| cpu | IND11 | 1 | 1 | True/True | 2.04 | 23.36, 19.71, 18.54 | 19.71 | 19.71 | 0.431 | 0.334 |  |
| cpu | B1S11 | 11 | 1 | True/True | 18.40 | 18.56, 20.62, 18.60 | 18.60 | 18.60 | 0.645 | 0.625 |  |
| cpu | B4S11 | 11 | 4 | True/True | 108.79 | 116.04, 170.59 | 143.32 | 35.83 | 1.423 | 1.543 | repeat 2 took 170.6s > 120.0s |
| cpu | B8S11 | 11 | 8 | True/True | 259.25 |  | NA | NA | 2.046 | 2.868 | warm-up took 259.2s > 120.0s |
| mps | S1 | 1 | 1 | True/True | 2.58 | 0.69, 0.74, 0.81 | 0.74 | 0.74 | 0.485 | 0.508 |  |
| mps | S5 | 5 | 1 | True/True | 6.04 | 6.59, 6.63, 5.89 | 6.59 | 6.59 | 0.553 | 1.667 |  |
| mps | S11 | 11 | 1 | True/True | 15.91 | 16.21, 16.38, 16.08 | 16.21 | 16.21 | 0.530 | 1.675 |  |
| mps | S21 | 21 | 1 | True/True | 25.90 | 30.00, 30.47, 28.80 | 30.00 | 30.00 | 0.478 | 1.587 |  |
| mps | IND11 | 1 | 1 | True/True | 1.37 | 12.70, 13.87, 11.76 | 12.70 | 12.70 | 0.496 | 0.506 |  |
| mps | B1S11 | 11 | 1 | True/True | 13.14 | 15.20, 14.70, 13.99 | 14.70 | 14.70 | 0.521 | 1.661 |  |
| mps | B4S11 | 11 | 4 | True/True | 55.39 | 63.81, 56.37, 61.01 | 61.01 | 15.25 | 0.508 | 2.663 |  |
| mps | B8S11 | 11 | 8 | True/True | 164.32 |  | NA | NA | 0.523 | 4.155 | warm-up took 164.3s > 120.0s |

   Weight-file last-change dates: Kronos-small `model.safetensors` 2025-06-30T16:44:37Z; Kronos-Tokenizer-base `model.safetensors` 2025-06-30T17:04:10Z. These are **file dates in the Hugging Face repos, not the authors' training cutoff**.
   After `from_pretrained` both objects reported `training=True`. In eval mode MPS runs; in train mode MPS fails (`scaled_dot_product_attention for MPS does not support dropout`).
9. **Known limits to carry to the README:**
   - The stock `KronosPredictor` does not call `.eval()`.
   - `clip=5` is applied twice (in `predict` and in `auto_regressive_inference`).
   - S=11 was chosen by compute budget, while the paper reports gains from more samples.
