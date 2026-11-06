"""Phase 1 feasibility spike: one config per process. Run via scripts/run_spike.sh (under /usr/bin/time -l).

Input: ONLY the example CSV shipped in third_party/kronos. Prints timing/shape/NaN/determinism and
forecast-to-forecast differences. It never compares a forecast with realised prices.

SEED CONVENTION: torch.manual_seed(seed) is called immediately before EVERY forecast call
(seeds CPU and MPS generators). Spike: warm-up seed 0; timed repeat r (1..3) seed 1000 + r;
independent-call unit r uses seeds 1000 + 100*r + j (j = 0..10). Real run (proposal):
seed = 1_000_000 * pair_index + origin_index, one seed per origin (batch of origins: seed of its first origin).
"""
import argparse, hashlib, json, os, resource, statistics, sys, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("HF_HOME", str(ROOT / ".cache" / "huggingface"))
os.environ.setdefault("HF_HUB_CACHE", str(ROOT / ".cache" / "huggingface" / "hub"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "third_party" / "kronos"))

import numpy as np
import pandas as pd
import torch
from model import Kronos, KronosPredictor, KronosTokenizer

CSV = ROOT / "third_party" / "kronos" / "tests" / "data" / "regression_input.csv"
TOK = ("NeoQuasar/Kronos-Tokenizer-base", "0e0117387f39004a9016484a186a908917e22426")
MOD = ("NeoQuasar/Kronos-small", "901c26c1332695a2a8f243eb2f37243a37bea320")
LOOKBACK, PRED, T, TOP_P = 512, 24, 1.0, 0.9
RSS_LIMIT = 5_000_000_000
SLOW_S = 120.0


def emit(d):
    print("RESULT " + json.dumps(d), flush=True)


def watchdog(info):
    while True:
        time.sleep(0.25)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # bytes on macOS
        if rss > RSS_LIMIT:
            emit({**info, "aborted": "peak RSS > 5 GB", "rss_bytes": rss})
            os._exit(3)


def windows(n):
    d = pd.read_csv(CSV)
    d["timestamps"] = pd.to_datetime(d["timestamps"])
    out = []
    for k in range(n):
        a = k * PRED
        x = d.iloc[a:a + LOOKBACK].reset_index(drop=True)
        yt = d["timestamps"].iloc[a + LOOKBACK:a + LOOKBACK + PRED].reset_index(drop=True)
        out.append((x, x["timestamps"], yt))
    return out


def check(df_or_list, B):
    dfs = df_or_list if isinstance(df_or_list, list) else [df_or_list]
    ok = len(dfs) == B and all(d.shape == (PRED, 6) and np.isfinite(d.values).all() for d in dfs)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True)
    ap.add_argument("--cfg", required=True)  # S<n> | IND11 | B<b>S<s> | DET | MODECMP | PARITY
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--mode", default="eval", choices=["eval", "train"])
    a = ap.parse_args()
    info = {"device": a.device, "cfg": a.cfg, "torch": torch.__version__}
    threading.Thread(target=watchdog, args=(info,), daemon=True).start()

    if a.device == "mps":
        info["mps_available"] = bool(torch.backends.mps.is_available())
        print("mps available:", info["mps_available"], flush=True)
        if not info["mps_available"]:
            emit({**info, "error": "MPS not available"}); return

    try:
        tok = KronosTokenizer.from_pretrained(TOK[0], revision=TOK[1])
        mod = Kronos.from_pretrained(MOD[0], revision=MOD[1])
        print(f"after from_pretrained: model.training={mod.training} tokenizer.training={tok.training}", flush=True)
        info["training_after_load"] = {"model": mod.training, "tokenizer": tok.training}
        if a.mode == "eval":
            tok.eval(); mod.eval()
        else:
            tok.train(); mod.train()
        info["mode_used"] = a.mode
        pr = KronosPredictor(mod, tok, device=a.device, max_context=512)
        dev = a.device

        def sync():
            if dev == "mps":
                torch.mps.synchronize()

        def run_one(w, S, seed):
            torch.manual_seed(seed)
            return pr.predict(*w[:3], PRED, T=T, top_k=0, top_p=TOP_P, sample_count=S, verbose=False)

        def run_batch(ws, S, seed):
            torch.manual_seed(seed)
            return pr.predict_batch([w[0] for w in ws], [w[1] for w in ws], [w[2] for w in ws],
                                    PRED, T=T, top_k=0, top_p=TOP_P, sample_count=S, verbose=False)

        if a.cfg == "DET":
            w = windows(1)[0]
            outs = []
            for seed in (777, 777, 778):
                o = run_one(w, 5, seed); sync(); outs.append(o.values)
            same = bool(np.array_equal(outs[0], outs[1]))
            info.update(shape_ok=check(pd.DataFrame(outs[0]), 1) or outs[0].shape == (PRED, 6),
                        identical_same_seed=same,
                        max_abs_diff_same_seed=float(np.abs(outs[0] - outs[1]).max()),
                        differs_other_seed=bool(not np.array_equal(outs[0], outs[2])),
                        sha256_seed777=hashlib.sha256(outs[0].tobytes()).hexdigest()[:16],
                        nan_free=bool(np.isfinite(outs[0]).all()))
        elif a.cfg == "PARITY":
            from kronos_lab.sampling import predict_samples
            w = windows(1)[0]
            res = []
            for S, seed in ((1, 11), (5, 12)):
                o = run_one(w, S, seed)
                torch.manual_seed(seed)
                s = predict_samples(pr, [w[0]], [w[1]], [w[2]], PRED, T=T, top_k=0, top_p=TOP_P, sample_count=S)
                m = s.mean(axis=1)[0]
                res.append({"S": S, "max_abs": float(np.abs(m - o.values).max()),
                            "max_rel": float((np.abs(m - o.values) / (np.abs(o.values) + 1e-12)).max()),
                            "samples_shape": list(s.shape)})
            info["parity"] = res
        elif a.cfg == "MODECMP":
            w = windows(1)[0]
            res = {}
            for mode in ("eval", "train", "eval"):
                (tok.eval(), mod.eval()) if mode == "eval" else (tok.train(), mod.train())
                seed = 4242 if len(res) < 2 else 4243
                res[f"{mode}_{seed}"] = run_one(w, 1, seed)
            ev, tr, ev2 = res["eval_4242"], res["train_4242"], res["eval_4243"]
            ohlc = ["open", "high", "low", "close"]
            ref = float(w[0]["close"].mean())
            def mad(p, q, cols): return float(np.abs(p[cols].values - q[cols].values).mean())
            info.update(
                shapes_ok=check([ev, tr, ev2], 3), nan_free=all(np.isfinite(d.values).all() for d in (ev, tr, ev2)),
                ref_mean_close=ref,
                mean_abs_diff_ohlc_eval_vs_train_same_seed=mad(ev, tr, ohlc),
                mean_abs_diff_ohlc_eval_vs_eval_other_seed=mad(ev, ev2, ohlc),
                pct_of_mean_close_eval_vs_train=100 * mad(ev, tr, ohlc) / ref,
                pct_of_mean_close_eval_vs_eval_other_seed=100 * mad(ev, ev2, ohlc) / ref)
        else:
            if a.cfg == "IND11":
                S, B, kind = 1, 1, "ind11"
            elif a.cfg.startswith("S"):
                S, B, kind = int(a.cfg[1:]), 1, "single"
            else:  # B<b>S<s>
                b, s = a.cfg[1:].split("S"); B, S, kind = int(b), int(s), "batch"
            ws = windows(max(B, 1))
            info.update(sample_count=S, batch=B, kind=kind)

            def one_unit(r):  # r = 0 warm-up, else 1..repeats
                t0 = time.perf_counter()
                if kind == "single":
                    o = run_one(ws[0], S, 1000 + r if r else 0)
                elif kind == "batch":
                    o = run_batch(ws, S, 1000 + r if r else 0)
                else:  # 11 independent sample_count=1 calls (warm-up: a single call)
                    n = 11 if r else 1
                    o = [run_one(ws[0], 1, 1000 + 100 * r + j) for j in range(n)]
                sync()
                return time.perf_counter() - t0, o

            wt, o = one_unit(0)
            info["warmup_sec"] = wt
            info["shape_ok"] = check(o if kind != "ind11" else o, B)
            info["nan_free"] = all(np.isfinite(d.values).all() for d in (o if isinstance(o, list) else [o]))
            times = []
            if wt > SLOW_S:
                info["skipped_repeats"] = f"warm-up took {wt:.1f}s > {SLOW_S}s"
            else:
                for r in range(1, a.repeats + 1):
                    t, _ = one_unit(r); times.append(t)
                    if t > SLOW_S:
                        info["skipped_repeats"] = f"repeat {r} took {t:.1f}s > {SLOW_S}s"; break
            info["timed_sec"] = times
            if times:
                med = statistics.median(times)
                info["median_sec_per_call"] = med
                info["median_sec_per_origin"] = med / B
        info["maxrss_bytes_selfreported"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if a.device == "mps":
            info["mps_driver_allocated_bytes"] = torch.mps.driver_allocated_memory()
    except Exception as e:  # record the exact error, no workaround
        info["error"] = f"{type(e).__name__}: {e}"
    emit(info)


if __name__ == "__main__":
    main()
