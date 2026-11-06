"""Resumable Kronos forecast runner. Follows docs/DECISIONS.md exactly.

Imports only stdlib + numpy + kronos_lab.data (no torch, no pandas). The Kronos adapter is injected
(kronos_lab.kronos_adapter.KronosAdapter in real runs, a stub in tests).

The runner passes the adapter ONLY the 512-bar context and calendar timestamps. It never reads label
prices and never computes returns, labels or accuracy.

Output (per --out DIR):
  forecasts.jsonl  one atomic line per origin (single os.write + fsync)
  health.jsonl     every 25 origins (counts, timing, memory; nothing about accuracy)
  run_header.json  provenance (written once; restarts verify the run-critical parts only)
  restarts.log     one line per start
  DONE             written when finished (all complete, or cutoff reached)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import statistics
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from kronos_lab import data as D

ROOT = Path(__file__).resolve().parent.parent
NS = "KRONOS-LAB-v1"
N_SAMPLES = 11
PRED_LEN = 24
LOOKBACK = 512
HEALTH_EVERY = 25
EMPTY_CACHE_EVERY = 50
FEATURES = ["open", "high", "low", "close", "volume", "amount"]

# A change to any of these (or to the weights / processed CSVs) invalidates a restart.
# Everything else in the tree (tests, analysis code, docs) may change during a run.
CRITICAL_FILES = [
    "kronos_lab/runner.py",
    "kronos_lab/kronos_adapter.py",
    "kronos_lab/data.py",
    "scripts/launch_run.sh",
    "docs/DECISIONS.md",
]
RESTART_CHECK_KEYS = ["critical_files", "weights_sha256", "data_sha256"]  # HEAD is provenance only


class RefusalError(Exception):
    """Refuse to start/resume (exit code 3)."""


# ------------------------------------------------------------------ seeds and ordering
def seed_for(pair: str, day, k: int) -> int:
    d = day.isoformat() if isinstance(day, date) else str(day)
    return int.from_bytes(hashlib.sha256(f"{NS}|{pair}|{d}|{k}".encode()).digest()[:4], "big")


def order_key(stage: int, pair: str, day) -> str:
    d = day.isoformat() if isinstance(day, date) else str(day)
    return hashlib.sha256(f"{NS}|order|{stage}|{pair}|{d}".encode()).hexdigest()


def work_list(pairs=None) -> list[tuple[str, date, int]]:
    """All (pair, day, stage) for pairs x 396 days, stage 1->4, hash-ordered within a stage."""
    pairs = pairs or D.PAIRS
    items = [(p, day, D.stage_of(i)) for p in pairs for i, day in enumerate(D.origin_days())]
    items.sort(key=lambda it: (it[2], order_key(it[2], it[0], it[1])))
    return items


def smoke_work_list() -> list[tuple[str, date, int]]:
    items = [(p, date(2025, 9, d), 0) for p in ("BTCUSDT", "ETHUSDT") for d in (24, 25, 26)]
    items.sort(key=lambda it: order_key(0, it[0], it[1]))
    return items


def work_list_hash(items=None) -> str:
    items = work_list() if items is None else items
    return hashlib.sha256("\n".join(f"{p}|{d.isoformat()}|{s}" for p, d, s in items).encode()).hexdigest()


# ------------------------------------------------------------------ inputs (context + calendar only)
def make_inputs(series: D.Series, pair: str, day: date) -> dict:
    o = D.origin_ts(day)
    ctx = D.build_context(series, o, LOOKBACK)  # raises MissingBarError on any missing bar
    naive = lambda ms: D.from_ms(int(ms)).replace(tzinfo=None)  # naive datetimes representing UTC
    o_naive = o.replace(tzinfo=None)
    return {
        "pair": pair,
        "x": np.column_stack([getattr(ctx, f) for f in FEATURES]),
        "x_times": [naive(ms) for ms in ctx.open_time],
        "y_times": [o_naive + timedelta(hours=h) for h in range(PRED_LEN)],  # calendar only
        "last_close": float(ctx.close[-1]),
    }


# ------------------------------------------------------------------ run-critical hashes, git, header
def critical_hashes(root: Path = ROOT, files=None) -> dict:
    files = CRITICAL_FILES if files is None else files
    return {f: (D.sha256_file(Path(root) / f) if (Path(root) / f).is_file() else None) for f in files}


def _git(root: Path, *args) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RefusalError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def git_head(root: Path = ROOT) -> str:
    return _git(root, "rev-parse", "HEAD").strip()


def dirty_critical(root: Path = ROOT, files=None) -> list[str]:
    """`git status --porcelain` limited to the run-critical files (ignored paths never appear)."""
    files = CRITICAL_FILES if files is None else files
    out = _git(root, "status", "--porcelain", "--", *files)
    return [l for l in out.splitlines() if l.strip()]


def data_hashes(processed_dir: Path, pairs=None) -> dict:
    return {p: D.sha256_file(Path(processed_dir) / f"{p}_1h.csv") for p in (pairs or D.PAIRS)}


def build_header(adapter, root: Path, processed_dir: Path, smoke: bool) -> dict:
    desc = adapter.describe() if hasattr(adapter, "describe") else {}
    try:
        head = git_head(root)
        dirty = _git(root, "status", "--porcelain").splitlines()
    except RefusalError:
        head, dirty = None, None
    return {
        "smoke": smoke,
        "git_head": head,                       # provenance only; never compared on restart
        "git_dirty_whole_tree": bool(dirty) if dirty is not None else None,
        "numpy": np.__version__,
        **{k: v for k, v in desc.items() if k != "weights_sha256"},
        "weights_sha256": desc.get("weights_sha256", {}),
        "critical_files": critical_hashes(root),
        "data_sha256": data_hashes(processed_dir),
        "protocol": {"namespace": NS, "samples": N_SAMPLES, "pred_len": PRED_LEN, "lookback": LOOKBACK,
                     "T": 1.0, "top_p": 0.9, "work_list_sha256": work_list_hash(smoke_work_list() if smoke else None)},
    }


def prepare(out_dir: Path, header: dict, *, enforce: bool, root: Path, files=None) -> str:
    """Dirty-tree refusal + restart check, both limited to run-critical files / weights / data hashes."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if enforce:
        missing = [f for f, h in header["critical_files"].items() if h is None]
        if missing:
            raise RefusalError(f"run-critical files missing: {missing}")
        dirty = dirty_critical(root, files)
        if dirty:
            raise RefusalError("run-critical files are modified/untracked (commit them first):\n" + "\n".join(dirty))
    hp = out_dir / "run_header.json"
    if hp.exists():
        old = json.loads(hp.read_text())
        diffs = [k for k in RESTART_CHECK_KEYS if old.get(k) != header.get(k)]
        if diffs:
            raise RefusalError("restart check failed, changed since the first start: " + ", ".join(
                f"{k}" + (f" ({', '.join(sorted(f for f in set(old[k]) | set(header[k]) if old[k].get(f) != header[k].get(f)))})"
                          if isinstance(old.get(k), dict) and isinstance(header.get(k), dict) else "") for k in diffs))
        return "verified"
    hp.write_text(json.dumps(header, indent=1, sort_keys=True) + "\n")
    return "new"


# ------------------------------------------------------------------ forecasts file
def _append_line(path: Path, obj: dict) -> None:
    data = (json.dumps(obj, separators=(",", ":"), allow_nan=False) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        n = os.write(fd, data)  # one write call per origin
        assert n == len(data)
        os.fsync(fd)
    finally:
        os.close(fd)


def load_done(path: Path) -> dict:
    """Read forecasts.jsonl; drop (truncate away) a truncated/invalid final line. Returns {(pair,date): record}."""
    path = Path(path)
    if not path.exists():
        return {}
    raw = path.read_bytes()
    keep = len(raw)
    if raw and not raw.endswith(b"\n"):
        keep = raw.rfind(b"\n") + 1
    else:  # complete last line that does not parse is also dropped
        lines = raw.split(b"\n")[:-1]
        if lines:
            try:
                json.loads(lines[-1])
            except ValueError:
                keep = len(raw) - len(lines[-1]) - 1
    if keep != len(raw):
        with open(path, "r+b") as f:
            f.truncate(keep)
        raw = raw[:keep]
    done = {}
    for ln in raw.split(b"\n"):
        if ln.strip():
            r = json.loads(ln)
            done[(r["pair"], r["date"])] = r
    return done


def _finite_row(row) -> bool:
    return all(v is not None and np.isfinite(v) for v in row)


# ------------------------------------------------------------------ main loop
def run(out_dir, adapter, series_by_pair, work, *, cutoff_ts=None, max_origins=None, now=time.time, log=print) -> int:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fpath, hpath = out_dir / "forecasts.jsonl", out_dir / "health.jsonl"
    done = load_done(fpath)
    total = len(work)
    new_secs: list[float] = []
    processed_now = 0
    stage_of_item = {(p, d.isoformat()): s for p, d, s in work}

    def write_done(reason):
        (out_dir / "DONE").write_text(json.dumps({"reason": reason, "done": len(done), "total": total,
                                                   "time_utc": datetime.now(timezone.utc).isoformat()}) + "\n")

    def health():
        by_stage = {}
        for (p, d), r in done.items():
            by_stage[str(r["stage"])] = by_stage.get(str(r["stage"]), 0) + 1
        mem = adapter.memory_stats() if hasattr(adapter, "memory_stats") else {}
        _append_line(hpath, {"time_utc": datetime.now(timezone.utc).isoformat(), "done": len(done), "total": total,
                             "done_by_stage": by_stage,
                             "median_seconds_last25": statistics.median(new_secs[-HEALTH_EVERY:]) if new_secs else None,
                             "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,  # peak, bytes on macOS
                             **mem, "nan_count": sum(1 for r in done.values() if r["status"] == "nan")})

    for pair, day, stage in work:
        key = (pair, day.isoformat())
        if key in done:
            continue
        if cutoff_ts is not None and now() >= cutoff_ts:
            write_done("cutoff"); log(f"cutoff reached; done={len(done)}/{total}")
            return 0
        if max_origins is not None and processed_now >= max_origins:
            return 0
        t0 = time.perf_counter()
        try:
            inputs = make_inputs(series_by_pair[pair], pair, day)
        except D.MissingBarError as e:
            rec = {"pair": pair, "date": key[1], "stage": stage, "origin_ts": D.iso(D.to_ms(D.origin_ts(day))),
                   "last_close": None, "closes": None, "status": "excluded", "reason": str(e), "seconds": 0.0}
        else:
            closes = []
            for k in range(N_SAMPLES):
                row = [float(v) for v in adapter.predict_one(inputs, seed_for(pair, day, k))]
                if len(row) != PRED_LEN:
                    raise RuntimeError(f"adapter returned {len(row)} values, expected {PRED_LEN}")
                closes.append(row)
            ok = all(_finite_row(r) for r in closes)
            secs = time.perf_counter() - t0
            rec = {"pair": pair, "date": key[1], "stage": stage, "origin_ts": D.iso(D.to_ms(D.origin_ts(day))),
                   "last_close": inputs["last_close"],
                   "closes": [[(v if np.isfinite(v) else None) for v in r] for r in closes],
                   "status": "ok" if ok else "nan", "seconds": round(secs, 3)}
            new_secs.append(secs)
        _append_line(fpath, rec)
        done[key] = rec
        processed_now += 1
        if processed_now % HEALTH_EVERY == 0:
            health()
        if processed_now % EMPTY_CACHE_EVERY == 0 and hasattr(adapter, "empty_cache"):
            adapter.empty_cache()
        log(f"[{len(done)}/{total}] {pair} {key[1]} stage {stage} {rec['status']} {rec['seconds']}s")
    health()
    write_done("all_complete")
    log(f"all complete: {len(done)}/{total}")
    return 0


# ------------------------------------------------------------------ CLI
def parse_cutoff(s: str) -> float:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def main(argv=None, *, adapter=None, series_by_pair=None, root: Path = ROOT, processed_dir=None, now=time.time) -> int:
    ap = argparse.ArgumentParser(prog="kronos_lab.runner")
    ap.add_argument("--out")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--max-origins", type=int)
    ap.add_argument("--cutoff", help="ISO UTC, e.g. 2026-11-07T03:30:00Z (required for the main run)")
    a = ap.parse_args(argv)
    if not a.smoke and not a.cutoff:
        ap.error("--cutoff is required for the main run")
    if not a.smoke and not a.out:
        ap.error("--out is required for the main run")
    out_dir = Path(a.out) if a.out else root / "results" / "smoke"
    processed_dir = Path(processed_dir) if processed_dir else root / "data" / "processed"
    work = smoke_work_list() if a.smoke else work_list()
    try:
        if adapter is None:
            from kronos_lab.kronos_adapter import KronosAdapter  # lazy: needs torch + pandas
            adapter = KronosAdapter()
        header = build_header(adapter, root, processed_dir, a.smoke)
        state = prepare(out_dir, header, enforce=not a.smoke, root=root)
        if series_by_pair is None:
            series_by_pair = {p: D.load_series(p, processed_dir) for p in {w[0] for w in work}}
        n_done = len(load_done(out_dir / "forecasts.jsonl"))
        with open(out_dir / "restarts.log", "a") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} start head={header['git_head']} resumed_done={n_done} header={state}\n")
        return run(out_dir, adapter, series_by_pair, work,
                   cutoff_ts=parse_cutoff(a.cutoff) if a.cutoff else None, max_origins=a.max_origins, now=now)
    except RefusalError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
