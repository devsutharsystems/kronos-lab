"""Leakage, window, stage, parsing, validation and checksum tests. Synthetic data only; no network, no torch."""
import random
from datetime import date, datetime, timezone

import numpy as np
import pytest

from kronos_lab import data as D

START = D.to_ms(datetime(2025, 9, 1, tzinfo=timezone.utc))
N_BARS = 14 * 31 * 24  # covers 2025-09-01 .. well past 2026-10-31


def synth(n=N_BARS, start=START, seed=0) -> D.Series:
    rng = np.random.default_rng(seed)
    t = start + D.HOUR_MS * np.arange(n, dtype=np.int64)
    base = 100 + rng.random(n)
    return D.Series(t, base, base + 1, base - 1, base + 0.5, rng.random(n) + 1, rng.random(n) + 1)


def origin(i):
    return D.origin_ts(D.origin_days()[i])


# a. leakage ---------------------------------------------------------------
def pick_origins():
    r = random.Random(7)
    return sorted({0, D.N_DAYS - 1, *r.sample(range(D.N_DAYS), 48)})


def test_context_closed_before_origin_and_length():
    s = synth()
    idxs = pick_origins()
    assert len(idxs) == 50
    for i in idxs:
        o = D.to_ms(origin(i))
        ctx = D.build_context(s, origin(i))
        assert len(ctx) == 512
        assert (ctx.close_time <= o).all()
        assert ctx.open_time[-1] == o - D.HOUR_MS  # ends 23:00 of the previous day
        assert ctx.open_time[0] == o - 512 * D.HOUR_MS


def test_nan_overwrite_of_future_leaves_context_unchanged():
    s = synth()
    for i in pick_origins():
        o = D.to_ms(origin(i))
        before = D.build_context(s, origin(i))
        poisoned = s.copy()
        m = poisoned.open_time >= o
        for f in D.FIELDS:
            getattr(poisoned, f)[m] = np.nan
        after = D.build_context(poisoned, origin(i))
        for f in ["open_time"] + D.FIELDS:
            np.testing.assert_array_equal(getattr(before, f), getattr(after, f))
        assert not np.isnan(after.close).any()


def test_first_origin_needs_only_september():
    # first context bar is 2025-09-09 16:00 UTC
    ctx = D.build_context(synth(), origin(0))
    assert D.iso(int(ctx.open_time[0])) == "2025-09-09T16:00:00Z"


# b. labels ----------------------------------------------------------------
def test_labels_do_not_overlap_context_and_are_disjoint_across_origins():
    s = synth()
    seen = set()
    for i in range(D.N_DAYS):
        ctx, lab = D.build_context(s, origin(i)), D.label_bars(s, origin(i))
        assert len(lab) == 24
        assert ctx.open_time.max() < lab.open_time.min()
        assert lab.open_time.min() == D.to_ms(origin(i)) and lab.close_time.max() < D.to_ms(origin(i)) + 24 * D.HOUR_MS
        ids = set(lab.open_time.tolist())
        assert not (ids & seen)
        seen |= ids
    assert len(seen) == D.N_DAYS * 24


def test_missing_bar_invalidates_origin_never_fills():
    s = synth()
    k = int(np.searchsorted(s.open_time, D.to_ms(origin(10))))
    gap_ctx = s.slice(0, k - 5).copy()
    keep = np.r_[np.arange(0, k - 5), np.arange(k - 4, len(s))]  # drop one context bar
    s_ctx = D.Series(*(getattr(s, f)[keep] for f in ["open_time"] + D.FIELDS))
    assert not D.origin_is_valid(s_ctx, origin(10))
    assert D.origin_failure_reason(s_ctx, origin(10)) == "context"
    keep2 = np.delete(np.arange(len(s)), k + 3)  # drop one label bar
    s_lab = D.Series(*(getattr(s, f)[keep2] for f in ["open_time"] + D.FIELDS))
    assert D.origin_failure_reason(s_lab, origin(10)) == "labels"
    assert D.origin_is_valid(s, origin(10)) and gap_ctx is not None


# c. unit parsing ----------------------------------------------------------
def test_ms_and_us_rows_parse_to_same_utc_time():
    ms, us = 1759276800000, 1759276800000000  # 2025-10-01 00:00:00 UTC
    row = lambda t, c: f"{t},1,2,0.5,1.5,10,{c},15,3,5,7,0"
    a = D.parse_klines_text(row(ms, ms + 3599999))
    b = D.parse_klines_text(row(us, us + 3599999999))
    assert a["unit"] == "ms" and b["unit"] == "us"
    assert a["open_time"][0] == b["open_time"][0] == ms
    assert D.iso(int(b["open_time"][0])) == "2025-10-01T00:00:00Z"
    assert b["amount"][0] == 15.0
    with pytest.raises(D.DataError):  # mixed units inside one file are rejected
        D.parse_klines_text(row(ms, ms + 3599999) + "\n" + row(us, us + 3599999999))


# d. window and stages -----------------------------------------------------
def test_origin_days_and_stage_sizes():
    days = D.origin_days()
    assert len(days) == 396 and days[0] == date(2025, 10, 1) and days[-1] == date(2026, 10, 31)
    assert (days[-1] - days[0]).days + 1 == 396
    stages = [D.stage_of(i) for i in range(396)]
    sizes = [stages.count(k) for k in (1, 2, 3, 4)]
    assert sizes == [50, 49, 99, 198]
    assert np.cumsum(sizes).tolist() == [50, 99, 198, 396]
    assert all(D.stage_of(i) == 4 for i in range(1, 396, 2))
    # last origin's labels end 2026-10-31 23:00 UTC (inside the window)
    assert D.iso(D.to_ms(origin(395)) + 23 * D.HOUR_MS) == "2026-10-31T23:00:00Z"


# e. validator -------------------------------------------------------------
def _validate(s):
    return D.validate_arrays(s.open_time, s.open, s.high, s.low, s.close, s.volume)


def test_validator_catches_gap_duplicate_and_high_below_low():
    s = synth(48, start=D.to_ms(datetime(2026, 10, 30, tzinfo=timezone.utc)))
    assert _validate(s)["ok"]
    gap = D.Series(*(getattr(s, f)[np.r_[0:10, 13:48]] for f in ["open_time"] + D.FIELDS))
    r = _validate(gap)
    assert not r["ok"] and r["gaps"] == [{"first_missing": "2026-10-30T10:00:00Z", "last_missing": "2026-10-30T12:00:00Z",
                                           "missing_bars": 3, "aligned": True}]
    dup = D.Series(*(getattr(s, f)[np.r_[0:10, 10, 10:48]] for f in ["open_time"] + D.FIELDS))
    r = _validate(dup)
    assert r["duplicates"] == 1 and not r["ok"]
    bad = s.copy(); bad.high[5] = bad.low[5] - 1
    r = _validate(bad)
    assert r["high_below_low"] == 1 and not r["ok"]
    nan = s.copy(); nan.close[3] = np.nan
    assert _validate(nan)["nan_values"] == 1
    neg = s.copy(); neg.volume[2] = -1
    assert _validate(neg)["negative_volume"] == 1


# f. checksum --------------------------------------------------------------
def test_checksum_verification_rejects_corrupted_file(tmp_path):
    z = tmp_path / "BTCUSDT-1h-2025-09.zip"
    c = tmp_path / "BTCUSDT-1h-2025-09.zip.CHECKSUM"
    z.write_bytes(b"PK-fake-zip-content" * 100)
    c.write_text(f"{D.sha256_file(z)}  {z.name}\n")
    assert D.verify_checksum(z, c)
    z.write_bytes(z.read_bytes()[:-1] + b"X")  # corrupt one byte
    with pytest.raises(D.ChecksumError):
        D.verify_checksum(z, c)
    c.write_text(f"{D.sha256_file(z)}  other.zip\n")  # wrong file name in checksum
    with pytest.raises(D.ChecksumError):
        D.verify_checksum(z, c)
