"""Real-format rehearsal, entirely inside tmp_path (SYNTHETIC prices, stub adapter).

A COPY of the kronos_lab/ package is placed in tmp_path, so the copy's own defaults (ROOT = parent of the package)
resolve to tmp_path. A subprocess runs it with cwd=tmp_path under a BLOCKING audit hook, installed before kronos_lab
is imported: any open / mkdir / rename / remove / listdir / scandir whose resolved path is under the REAL project root
raises PermissionError, except read-only access under <real root>/.venv. The test asserts the hook never fired.

Flow in the subprocess, using the runner's OWN code: processed CSVs written by data.write_processed -> runner.main()
(header, atomic forecasts.jsonl lines, health, restarts.log, DONE) with a stub adapter -> analysis.load_real_inputs
-> analysis.run_analysis.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TIME_LIMIT_S = 120

SCRIPT = r'''
import os, sys, json, time, threading

REAL = os.path.realpath(os.environ["REHEARSE_REAL_ROOT"])
TMP = os.path.realpath(os.environ["REHEARSE_TMP"])
VENV = os.path.join(REAL, ".venv")
FIRED, TOUCHED, _g = [], [], threading.local()
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC

def under(p, base):
    return p == base or p.startswith(base + os.sep)

def hook(event, args):
    if getattr(_g, "on", False):
        return
    _g.on = True
    try:
        items = []                      # (path, is_write)
        if event == "open":
            p, mode, flags = args
            if isinstance(p, int):
                return
            w = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (isinstance(flags, int) and bool(flags & WRITE_FLAGS))
            items = [(p, w)]
        elif event in ("os.mkdir", "os.remove", "os.rmdir"):
            items = [(args[0], True)]
        elif event == "os.rename":
            items = [(args[0], True), (args[1], True)]
        elif event in ("os.listdir", "os.scandir"):
            items = [(args[0] if args[0] is not None else ".", False)]
        for p, w in items:
            if not isinstance(p, (str, bytes, os.PathLike)):
                continue
            rp = os.path.realpath(os.fsdecode(p))
            TOUCHED.append((event, rp, w))
            if under(rp, REAL) and not (under(rp, VENV) and not w and event in ("open", "os.listdir", "os.scandir")):
                FIRED.append((event, rp, w))
                raise PermissionError(f"BLOCKED by rehearsal hook: {event} {rp}")
    finally:
        _g.on = False

sys.addaudithook(hook)

# self-test of the hook on a harmless file under the real root (the hook raises before the open happens)
selftest_blocked = False
try:
    open(os.path.join(REAL, "LICENSE"), "rb")
except PermissionError:
    selftest_blocked = True
selftest_fired = len(FIRED)
del FIRED[:]
del TOUCHED[:]

from pathlib import Path
sys.path.insert(0, TMP)
import numpy as np
from kronos_lab import analysis as A, data as D, runner as R

assert Path(R.ROOT) == Path(TMP) and Path(D.ROOT) == Path(TMP), (R.ROOT, D.ROOT, TMP)
assert os.getcwd() == TMP

# SYNTHETIC processed series for all 6 pairs, written the way data.py writes them
from datetime import date, datetime, timezone
start = D.to_ms(datetime(2025, 9, 1, tzinfo=timezone.utc))
n_bars = 426 * 24                        # 2025-09-01 .. 2026-10-31 inclusive
for i, pair in enumerate(D.PAIRS):
    rng = np.random.default_rng(100 + i)
    t = start + D.HOUR_MS * np.arange(n_bars, dtype=np.int64)
    close = 100 * np.exp(np.cumsum(0.004 * rng.standard_normal(n_bars)))
    op = np.concatenate([[close[0]], close[:-1]])
    hi = np.maximum(op, close) * (1 + 0.002 * rng.random(n_bars))
    lo = np.minimum(op, close) * (1 - 0.002 * rng.random(n_bars))
    vol = 1 + rng.random(n_bars)
    D.write_processed(D.Series(t, op, hi, lo, close, vol, vol * close), Path(TMP) / "data" / "processed" / f"{pair}_1h.csv")

class Stub:
    def __init__(self): self.calls = 0
    def predict_one(self, inputs, seed):
        self.calls += 1
        base = float(inputs["x"][-1, 3])
        return [base * (1 + (((seed + 7 * h) % 2001) - 1000) / 40000.0) for h in range(24)]
    def describe(self):
        return {"device": "stub", "weights_sha256": {"Kronos-small": "stub", "Kronos-Tokenizer-base": "stub"}}

stub = Stub()
t0 = time.perf_counter()
rc = R.main(["--out", os.path.join(TMP, "results", "runs"), "--cutoff", "2099-01-01T00:00:00Z"], adapter=stub)
elapsed = time.perf_counter() - t0

runs = Path(TMP) / "results" / "runs"
lines = [json.loads(l) for l in (runs / "forecasts.jsonl").read_text().splitlines()]
hdr = json.loads((runs / "run_header.json").read_text())
done = json.loads((runs / "DONE").read_text())
inp, meta = A.load_real_inputs(TMP)
res = A.run_analysis(inp, B=300)
p = res["primary"]
series = {pr: D.load_series(pr, Path(TMP) / "data" / "processed") for pr in D.PAIRS}
mism = 0
for i in np.random.default_rng(0).choice(len(inp), 60, replace=False):
    s = series[str(inp.pair[i])]
    o = D.to_ms(D.origin_ts(date.fromisoformat(lines[i]["date"])))
    k = int(np.searchsorted(s.open_time, o))
    mism += int(not (inp.last_close[i] == s.close[k - 1] and inp.actual[i, 2] == s.close[k + 23] and inp.path[i, 23] == s.close[k + 23]
                     and inp.ctx_ohlc[i, -1, 3] == s.close[k - 1]))

def count(pred):
    return sum(1 for e in TOUCHED if pred(e))
writes_outside_tmp = sorted({p for (ev, p, w) in TOUCHED if w and not under(p, TMP) and not p.startswith("/dev/")})
reads_under_real = sorted({p for (ev, p, w) in TOUCHED if (not w) and under(p, REAL) and not under(p, VENV)})
summary = {
    "rc": rc, "elapsed_s": round(elapsed, 2), "stub_calls": stub.calls, "selftest_blocked": selftest_blocked,
    "selftest_fired": selftest_fired, "fired": FIRED, "n_touched": len(TOUCHED),
    "touched_by_event": {ev: count(lambda e, ev=ev: e[0] == ev) for ev in sorted({e[0] for e in TOUCHED})},
    "writes_outside_tmp": writes_outside_tmp, "reads_under_real_root_outside_venv": reads_under_real,
    "reads_under_venv": count(lambda e: (not e[2]) and under(e[1], VENV)),
    "touched_inside_tmp": count(lambda e: under(e[1], TMP)),
    "lines": len(lines), "unique": len({(r["pair"], r["date"]) for r in lines}), "statuses": sorted({r["status"] for r in lines}),
    "stage_counts": {str(s): sum(1 for r in lines if r["stage"] == s) for s in (1, 2, 3, 4)},
    "done": done, "header_head_len": len(hdr["git_head"] or ""), "header_critical_missing": [k for k, v in hdr["critical_files"].items() if v is None],
    "header_data_hashes": len(hdr["data_sha256"]), "restarts_log_lines": len((runs / "restarts.log").read_text().splitlines()),
    "health_lines": len((runs / "health.jsonl").read_text().splitlines()),
    "loaded": len(inp), "loaded_stage_counts": {str(s): int((inp.stage == s).sum()) for s in (1, 2, 3, 4)},
    "actual_finite": bool(np.isfinite(inp.actual).all()), "path_finite": bool(np.isfinite(inp.path).all()),
    "ctx_ohlc_finite": bool(np.isfinite(inp.ctx_ohlc).all()), "tail_finite": bool(np.isfinite(inp.ctx_tail).all()),
    "price_mismatches_in_60_spot_checks": mism,
    "analysis": {"n": p["n"], "D": p["kronos_down_calls_D"], "headline": p["headline"], "exclusions": p["exclusions_h24"]},
}
print("REHEARSAL_RESULT " + json.dumps(summary, default=str))
'''


def run_git(cwd, env, *args):
    r = subprocess.run(["git", "-c", "user.name=rehearsal", "-c", "user.email=rehearsal@example.invalid", "-c", "commit.gpgsign=false",
                        "-C", str(cwd), *args], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_real_format_rehearsal_inside_tmp_path(tmp_path):
    tmp = Path(os.path.realpath(tmp_path))
    assert not str(tmp).startswith(str(ROOT)), "tmp_path must be outside the project"
    # a COPY of the package, so its defaults resolve to tmp
    shutil.copytree(ROOT / "kronos_lab", tmp / "kronos_lab", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp / "scripts").mkdir()
    (tmp / "docs").mkdir()
    shutil.copy(ROOT / "scripts" / "launch_run.sh", tmp / "scripts" / "launch_run.sh")
    shutil.copy(ROOT / "docs" / "DECISIONS.md", tmp / "docs" / "DECISIONS.md")
    (tmp / ".gitignore").write_text("results/runs/\ndata/processed/\n__pycache__/\nrehearse.py\n")
    (tmp / "rehearse.py").write_text(SCRIPT)
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(tmp.parent), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
           "PYTHONDONTWRITEBYTECODE": "1", "REHEARSE_REAL_ROOT": str(ROOT), "REHEARSE_TMP": str(tmp)}
    env.pop("GIT_DIR", None)
    run_git(tmp, env, "init", "-q")
    run_git(tmp, env, "add", "-A")
    run_git(tmp, env, "commit", "-q", "-m", "rehearsal tree")
    assert run_git(tmp, env, "rev-parse", "--show-toplevel").strip() == str(tmp)      # git found the temp repo, not the real one

    r = subprocess.run([sys.executable, "-I", "-B", str(tmp / "rehearse.py")], cwd=tmp, env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (r.stdout[-1500:], r.stderr[-3000:])
    line = [l for l in r.stdout.splitlines() if l.startswith("REHEARSAL_RESULT ")][-1]
    s = json.loads(line[len("REHEARSAL_RESULT "):])
    print("REHEARSAL (SYNTHETIC prices, stub adapter):", json.dumps({k: s[k] for k in (
        "rc", "elapsed_s", "stub_calls", "lines", "unique", "statuses", "stage_counts", "done", "loaded", "analysis",
        "n_touched", "touched_inside_tmp", "reads_under_venv", "touched_by_event", "fired", "selftest_blocked",
        "writes_outside_tmp", "reads_under_real_root_outside_venv", "price_mismatches_in_60_spot_checks")}, default=str))

    # the hook works, and never fired during the rehearsal
    assert s["selftest_blocked"] is True and s["selftest_fired"] == 1
    assert s["fired"] == []
    assert s["writes_outside_tmp"] == [] and s["reads_under_real_root_outside_venv"] == []
    assert s["touched_inside_tmp"] > 1000 and s["n_touched"] >= s["touched_inside_tmp"]
    # the run itself: all 2376 origins, via the runner's own code path
    assert s["rc"] == 0 and s["elapsed_s"] < TIME_LIMIT_S
    assert s["lines"] == s["unique"] == s["loaded"] == 2376 and s["statuses"] == ["ok"]
    assert s["stage_counts"] == s["loaded_stage_counts"] == {"1": 300, "2": 294, "3": 594, "4": 1188}
    assert s["done"]["reason"] == "all_complete" and s["done"]["done"] == 2376
    assert s["stub_calls"] == 2376 * 11
    assert s["header_head_len"] == 40 and s["header_critical_missing"] == [] and s["header_data_hashes"] == 6
    assert s["restarts_log_lines"] == 1 and s["health_lines"] >= 1
    # the loader reproduced the label prices and context from the processed CSVs
    assert s["actual_finite"] and s["path_finite"] and s["ctx_ohlc_finite"] and s["tail_finite"]
    assert s["price_mismatches_in_60_spot_checks"] == 0
    assert 0 < s["analysis"]["n"] <= 2376
