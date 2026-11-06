"""Runner tests: stub adapter, synthetic series, temporary git repos. No torch, no network, no real prices."""
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from kronos_lab import data as D
from kronos_lab import runner as R

ROOT = Path(__file__).resolve().parent.parent
START = D.to_ms(datetime(2025, 9, 1, tzinfo=timezone.utc))
N_BARS = 14 * 31 * 24


def synth(seed=0) -> D.Series:
    rng = np.random.default_rng(seed)
    n = N_BARS
    t = START + D.HOUR_MS * np.arange(n, dtype=np.int64)
    base = 100 + rng.random(n)
    return D.Series(t, base, base + 1, base - 1, base + 0.5, rng.random(n) + 1, rng.random(n) + 1)


def all_series():
    return {p: synth(i) for i, p in enumerate(D.PAIRS)}


class Stub:
    """Deterministic function of (inputs, seed). Counts calls. Optional NaN injection."""

    def __init__(self, nan_for_seed=None, weights="w1"):
        self.calls = 0
        self.nan_for_seed = nan_for_seed
        self.weights = weights

    def predict_one(self, inputs, seed):
        self.calls += 1
        base = float(inputs["x"][-1, 3]) + float(inputs["x"][:, 0].mean()) * 1e-3
        out = [base + ((seed % 1000) / 1000.0) * (h + 1) * 0.01 for h in range(24)]
        if self.nan_for_seed is not None and seed == self.nan_for_seed:
            out[5] = float("nan")
        return out

    def describe(self):
        return {"device": "stub", "weights_sha256": {"Kronos-small": self.weights}}


# a. work list ------------------------------------------------------------
def test_work_list_size_stages_and_cross_process_order():
    w = R.work_list()
    assert len(w) == 2376 and len({(p, d) for p, d, _ in w}) == 2376
    stages = [s for _, _, s in w]
    assert stages == sorted(stages)
    assert [stages.count(k) for k in (1, 2, 3, 4)] == [300, 294, 594, 1188]
    assert np.cumsum([stages.count(k) for k in (1, 2, 3, 4)]).tolist() == [300, 594, 1188, 2376]
    here = R.work_list_hash(w)
    outs = []
    for hs in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": hs, "PYTHONPATH": str(ROOT)}
        r = subprocess.run([sys.executable, "-c", "from kronos_lab import runner; print(runner.work_list_hash())"],
                           cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        outs.append(r.stdout.strip())
    assert outs[0] == outs[1] == here


# b. seeds -----------------------------------------------------------------
def test_seeds_deterministic_distinct_32bit_and_known_value():
    seeds = [R.seed_for("BTCUSDT", date(2025, 10, 1), k) for k in range(11)]
    assert len(set(seeds)) == 11 and all(0 <= s < 2 ** 32 for s in seeds)
    # expectations computed independently with hashlib outside this module
    assert seeds[0] == 854730421
    assert R.seed_for("ETHUSDT", date(2026, 10, 31), 10) == 1372727745
    s = "KRONOS-LAB-v1|BTCUSDT|2025-10-01|0"
    assert seeds[0] == int.from_bytes(hashlib.sha256(s.encode()).digest()[:4], "big")
    env = {**os.environ, "PYTHONHASHSEED": "7", "PYTHONPATH": str(ROOT)}
    r = subprocess.run([sys.executable, "-c",
                        "from kronos_lab import runner as R; from datetime import date; print(R.seed_for('BTCUSDT', date(2025,10,1), 0))"],
                       cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    assert int(r.stdout) == 854730421


# c. no label access --------------------------------------------------------
def test_stub_output_unchanged_when_everything_from_origin_on_is_garbage(tmp_path):
    day = date(2026, 3, 15)
    o = D.to_ms(D.origin_ts(day))
    clean = synth()
    poisoned = clean.copy()
    m = poisoned.open_time >= o
    rng = np.random.default_rng(1)
    for f in D.FIELDS:
        getattr(poisoned, f)[m] = rng.random(int(m.sum())) * 1e9
    a, b = R.make_inputs(clean, "BTCUSDT", day), R.make_inputs(poisoned, "BTCUSDT", day)
    np.testing.assert_array_equal(a["x"], b["x"])
    assert a["x_times"] == b["x_times"] and a["y_times"] == b["y_times"] and a["last_close"] == b["last_close"]
    s1, s2 = Stub(), Stub()
    assert [s1.predict_one(a, k) for k in range(3)] == [s2.predict_one(b, k) for k in range(3)]
    # y_times are calendar-only, naive, hourly from the origin
    assert a["y_times"][0] == datetime(2026, 3, 15, 0) and a["y_times"][-1] == datetime(2026, 3, 15, 23)
    assert a["x_times"][-1] == datetime(2026, 3, 14, 23) and len(a["x_times"]) == 512 and a["x"].shape == (512, 6)
    # and through the runner: identical forecast lines for clean vs poisoned series
    out = {}
    for name, ser in (("c", clean), ("p", poisoned)):
        sers = {p: ser for p in D.PAIRS}
        R.run(tmp_path / name, Stub(), sers, [("BTCUSDT", day, 3)], log=lambda *_: None)
        out[name] = json.loads((tmp_path / name / "forecasts.jsonl").read_text())
    out["c"].pop("seconds"); out["p"].pop("seconds")
    assert out["c"] == out["p"]


# d. resume -----------------------------------------------------------------
def test_resume_drops_truncated_line_and_skips_complete_ones(tmp_path):
    work = R.smoke_work_list()
    sers = all_series()
    out = tmp_path / "o"
    R.run(out, Stub(), sers, work, max_origins=6, log=lambda *_: None)
    lines = (out / "forecasts.jsonl").read_text().splitlines()
    assert len(lines) == 6
    sixth = lines[5]
    (out / "forecasts.jsonl").write_text("\n".join(lines[:5]) + "\n" + sixth[: len(sixth) // 2])  # truncated 6th
    stub = Stub()
    R.run(out, stub, sers, work, log=lambda *_: None)
    got = [json.loads(l) for l in (out / "forecasts.jsonl").read_text().splitlines()]
    assert len(got) == 6 and len({(r["pair"], r["date"]) for r in got}) == 6
    assert stub.calls == 11  # only the 6th origin was redone
    assert [json.loads(l)["date"] for l in lines[:5]] == [r["date"] for r in got[:5]]
    assert (out / "DONE").exists()
    # a complete-but-unparseable last line is also dropped
    (out / "forecasts.jsonl").write_text("\n".join(lines[:5]) + "\n{not json}\n")
    assert len(R.load_done(out / "forecasts.jsonl")) == 5


# e. refusals, NaN, cutoff ------------------------------------------------------
def git(root, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false",
                           "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    for f in R.CRITICAL_FILES + ["tests/test_x.py"]:
        p = root / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {f}\n")
    (root / ".gitignore").write_text("results/runs/\n")
    pd_ = root / "data" / "processed"
    pd_.mkdir(parents=True)
    for p in D.PAIRS:
        (pd_ / f"{p}_1h.csv").write_text(f"fake {p}\n")
    git(root, "init", "-q"); git(root, "add", "-A"); git(root, "commit", "-q", "-m", "init")
    return root


def run_main(root, out, extra=(), stub=None, now=None):
    stub = stub or Stub()
    rc = R.main(["--out", str(out), "--cutoff", "2099-01-01T00:00:00Z", "--max-origins", "2", *extra],
                adapter=stub, series_by_pair=all_series(), root=root, processed_dir=root / "data" / "processed",
                **({"now": now} if now else {}))
    return rc, stub


def n_lines(out):
    return len((Path(out) / "forecasts.jsonl").read_text().splitlines())


def test_restart_ignores_tests_and_new_modules_but_not_runner_edits(repo, tmp_path):
    out = repo / "results" / "runs"
    rc, _ = run_main(repo, out)
    assert rc == 0 and n_lines(out) == 2
    # modify a test and add a brand-new module (both uncommitted): restart still allowed
    (repo / "tests" / "test_x.py").write_text("# changed\n")
    (repo / "kronos_lab" / "analysis.py").write_text("# new analysis module\n")
    assert D.sha256_file(repo / "tests" / "test_x.py")
    rc, _ = run_main(repo, out)
    assert rc == 0 and n_lines(out) == 4
    # editing a run-critical file blocks the restart (dirty)
    (repo / "kronos_lab" / "runner.py").write_text("# edited\n")
    rc, _ = run_main(repo, out)
    assert rc == 3 and n_lines(out) == 4
    # ... and still blocks after committing it (hash differs from the first start)
    git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "edit runner")
    rc, _ = run_main(repo, out)
    assert rc == 3 and n_lines(out) == 4
    # HEAD changed along the way but is provenance only
    hdr = json.loads((out / "run_header.json").read_text())
    assert hdr["git_head"] != git(repo, "rev-parse", "HEAD").strip()


def test_dirty_run_critical_file_refuses_fresh_main_run_but_not_smoke(repo):
    (repo / "docs" / "DECISIONS.md").write_text("changed\n")
    rc, stub = run_main(repo, repo / "results" / "runs")
    assert rc == 3 and stub.calls == 0
    rc, stub = run_main(repo, repo / "results" / "smk", extra=["--smoke"])  # smoke records dirt, does not refuse
    assert rc == 0 and stub.calls > 0


def test_weights_hash_change_blocks_restart(repo):
    out = repo / "results" / "runs"
    assert run_main(repo, out, stub=Stub(weights="A"))[0] == 0
    assert run_main(repo, out, stub=Stub(weights="B"))[0] == 3


def test_missing_run_critical_file_refuses_main_run(repo):
    (repo / "scripts" / "launch_run.sh").unlink()
    git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "rm")
    assert run_main(repo, repo / "results" / "runs")[0] == 3


def test_nan_output_is_status_nan_and_never_retried(tmp_path):
    day = date(2026, 1, 5)
    seed = R.seed_for("BTCUSDT", day, 3)
    out = tmp_path / "o"
    stub = Stub(nan_for_seed=seed)
    R.run(out, stub, all_series(), [("BTCUSDT", day, 2)], log=lambda *_: None)
    rec = json.loads((out / "forecasts.jsonl").read_text())
    assert rec["status"] == "nan" and rec["closes"][3][5] is None and len(rec["closes"]) == 11
    n = stub.calls
    R.run(out, stub, all_series(), [("BTCUSDT", day, 2)], log=lambda *_: None)
    assert stub.calls == n and n_lines(out) == 1


def test_cutoff_required_for_main_run_and_stops_after_cutoff(tmp_path, repo):
    with pytest.raises(SystemExit) as e:
        R.main(["--out", str(tmp_path / "x")], adapter=Stub(), series_by_pair={}, root=repo)
    assert e.value.code == 2
    out = repo / "results" / "runs"
    rc = R.main(["--out", str(out), "--cutoff", "2026-11-07T03:30:00Z"], adapter=Stub(), series_by_pair=all_series(),
                root=repo, processed_dir=repo / "data" / "processed", now=lambda: R.parse_cutoff("2026-11-07T03:30:00Z"))
    assert rc == 0
    assert json.loads((out / "DONE").read_text())["reason"] == "cutoff"
    assert not (out / "forecasts.jsonl").exists()


def test_cutoff_checked_between_origins(tmp_path):
    ticks = iter([0, 0, 10])  # third check is past the cutoff
    work = R.smoke_work_list()
    stub = Stub()
    R.run(tmp_path / "o", stub, all_series(), work, cutoff_ts=5, now=lambda: next(ticks), log=lambda *_: None)
    assert n_lines(tmp_path / "o") == 2
    assert json.loads((tmp_path / "o" / "DONE").read_text())["reason"] == "cutoff"


# f. check_health ---------------------------------------------------------------
def load_check_health():
    spec = importlib.util.spec_from_file_location("check_health", ROOT / "scripts" / "check_health.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_check_health_reads_only_run_files(tmp_path, monkeypatch):
    out = tmp_path / "o"
    R.run(out, Stub(nan_for_seed=R.seed_for("BTCUSDT", date(2025, 9, 24), 0)), all_series(), R.smoke_work_list(), log=lambda *_: None)
    ch = load_check_health()
    assert "processed" not in (ROOT / "scripts" / "check_health.py").read_text()
    opened = []
    real_io_open, real_open = io.open, open

    def spy(real):
        def f(file, *a, **k):
            opened.append(str(file))
            assert "processed" not in str(file) and "data" + os.sep not in str(file)
            return real(file, *a, **k)
        return f

    monkeypatch.setattr(io, "open", spy(real_io_open))
    monkeypatch.setattr("builtins.open", spy(real_open))
    rep = ch.check(out)
    assert rep["lines"] == 6 and rep["unique_origins"] == 6 and rep["nan_count"] == 1
    assert rep["all_shapes_ok"] and rep["done_per_stage"] == {0: 6}
    assert rep["origins_with_nonfinite"] == 1 and rep["median_seconds_per_origin"] is not None
    assert all(Path(p).name in ("forecasts.jsonl", "health.jsonl") for p in opened)
