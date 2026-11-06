"""Binance Vision 1h klines: download, verify, parse, validate, and leak-free origin windows.

Standard library + numpy only (no pandas). Data: Binance Vision (data.binance.vision),
CC BY-NC-SA 4.0, not affiliated with Binance. Not financial advice.

This module never computes returns or any statistic on prices. Missing bars are never
interpolated or filled: an origin with a missing bar is invalid and gets excluded.
"""
from __future__ import annotations

import csv
import hashlib
import io
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"]
BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
INTERVAL = "1h"
MONTHS = [f"{y}-{m:02d}" for y, m in
          [(2025, m) for m in range(9, 13)] + [(2026, m) for m in range(1, 11)]]  # 2025-09 .. 2026-10 (14)

HOUR_MS = 3_600_000
LOOKBACK = 512
HORIZON = 24
WINDOW_START = date(2025, 10, 1)
N_DAYS = 396  # 2025-10-01 .. 2026-10-31 inclusive
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
DEADLINE_MS = int((datetime(2026, 11, 1, tzinfo=timezone.utc) - EPOCH).total_seconds() * 1000)

# Binance kline column order (data.binance.vision README)
COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_asset_volume", "number_of_trades", "taker_buy_base", "taker_buy_quote", "ignore"]


class DataError(Exception):
    pass


class DownloadError(DataError):
    pass


class ChecksumError(DataError):
    pass


class MissingBarError(DataError):
    pass


# ---------------------------------------------------------------- time helpers
def to_ms(ts) -> int:
    """Aware datetime (UTC) or int milliseconds -> int milliseconds since epoch."""
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            raise ValueError("naive datetime; use UTC-aware")
        return int((ts - EPOCH) // timedelta(milliseconds=1))
    return int(ts)


def from_ms(ms: int) -> datetime:
    return EPOCH + timedelta(milliseconds=int(ms))


def iso(ms: int) -> str:
    return from_ms(ms).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> int:
    return to_ms(datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc))


def detect_unit(value) -> str:
    """'ms' for 13-digit, 'us' for 16-digit epoch values (Binance spot switched to microseconds in 2025)."""
    n = len(str(abs(int(value))))
    if n == 13:
        return "ms"
    if n == 16:
        return "us"
    raise DataError(f"unrecognised timestamp unit: {value} ({n} digits)")


def normalize_ts(value, unit: str | None = None) -> int:
    unit = unit or detect_unit(value)
    v = int(value)
    return v if unit == "ms" else v // 1000


# ---------------------------------------------------------------- stages / origins
def origin_days() -> list[date]:
    return [WINDOW_START + timedelta(days=i) for i in range(N_DAYS)]


def origin_ts(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def stage_of(day_index: int) -> int:
    if not 0 <= day_index < N_DAYS:
        raise ValueError(day_index)
    if day_index % 8 == 0:
        return 1
    if day_index % 4 == 0:
        return 2
    if day_index % 2 == 0:
        return 3
    return 4


# ---------------------------------------------------------------- URLs, checksums, download
def file_name(sym: str, ym: str, ext: str = "zip") -> str:
    return f"{sym}-{INTERVAL}-{ym}.{ext}"


def url_for(sym: str, ym: str, ext: str = "zip") -> str:
    return f"{BASE_URL}/{sym}/{INTERVAL}/{file_name(sym, ym, ext)}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_checksum_file(path: Path) -> tuple[str, str | None]:
    """Binance .CHECKSUM content: '<sha256>  <filename>'. Returns (hex, filename or None)."""
    parts = Path(path).read_text().split()
    if not parts or len(parts[0]) != 64:
        raise ChecksumError(f"unparseable checksum file: {path}")
    return parts[0].lower(), (parts[1].lstrip("*") if len(parts) > 1 else None)


def verify_checksum(zip_path: Path, checksum_path: Path) -> bool:
    """True if the zip's sha256 equals the checksum file; raises ChecksumError otherwise."""
    expected, name = read_checksum_file(checksum_path)
    if name is not None and name != Path(zip_path).name:
        raise ChecksumError(f"checksum file names {name}, expected {Path(zip_path).name}")
    actual = sha256_file(zip_path)
    if actual != expected:
        raise ChecksumError(f"sha256 mismatch for {zip_path}: expected {expected}, got {actual}")
    return True


def _http_get(url: str, timeout: int = 120, retries: int = 2) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "kronos-lab-research/0.1"})
    last = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status != 200:
                    raise DownloadError(f"{url} -> HTTP {r.status}")
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500:  # 4xx: no retry, caller stops
                raise DownloadError(f"{url} -> HTTP {e.code}") from e
            last = e
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
        time.sleep(1.0)
    raise DownloadError(f"{url} failed after {retries} retries: {last}")


def fetch_all(raw_dir: Path = RAW_DIR, pairs=PAIRS, months=MONTHS, pause: float = 0.5, log=print) -> list[dict]:
    """Sequential download of every monthly zip + .CHECKSUM, verified with sha256.

    Skips files already verified. Stops (raises) on the first non-200, missing file, or checksum failure;
    no other source is ever tried.
    """
    manifest = []
    for sym in pairs:
        d = Path(raw_dir) / sym
        d.mkdir(parents=True, exist_ok=True)
        for ym in months:
            zp, cp = d / file_name(sym, ym), d / file_name(sym, ym, "zip.CHECKSUM")
            status = "skipped_verified"
            try:
                if not (zp.exists() and cp.exists() and verify_checksum(zp, cp)):
                    raise ChecksumError("absent")
            except (ChecksumError, FileNotFoundError):
                status = "downloaded"
                cdata = _http_get(url_for(sym, ym, "zip.CHECKSUM"))
                time.sleep(pause)
                zdata = _http_get(url_for(sym, ym))
                time.sleep(pause)
                tz, tc = zp.with_suffix(".zip.part"), cp.with_suffix(".CHECKSUM.part")
                tz.write_bytes(zdata); tc.write_bytes(cdata)
                try:
                    verify_checksum(tz.rename(zp), tc.rename(cp))  # name check uses final zip name
                except ChecksumError:
                    zp.unlink(missing_ok=True); cp.unlink(missing_ok=True)
                    raise
            manifest.append({"file": f"{sym}/{zp.name}", "bytes": zp.stat().st_size,
                             "sha256": sha256_file(zp), "checksum_ok": True, "status": status})
            log(f"{status:17s} {sym}/{zp.name} {zp.stat().st_size} B")
    return manifest


# ---------------------------------------------------------------- parsing
FIELDS = ["open", "high", "low", "close", "volume", "amount"]


def parse_klines_text(text: str) -> dict:
    """Parse Binance kline CSV text. Unit (ms/us) detected from the first row, asserted for every row."""
    rows = [r for r in csv.reader(io.StringIO(text)) if r]
    if rows and not rows[0][0].strip().lstrip("-").isdigit():
        rows = rows[1:]  # header row, if any
    if not rows:
        raise DataError("no kline rows")
    unit = detect_unit(rows[0][0])
    for r in rows:
        if len(r) != len(COLS):
            raise DataError(f"expected {len(COLS)} columns, got {len(r)}")
        if detect_unit(r[0]) != unit or detect_unit(r[6]) != unit:
            raise DataError("mixed timestamp units within one file")
    out = {"unit": unit,
           "open_time": np.array([normalize_ts(r[0], unit) for r in rows], dtype=np.int64),
           "close_time": np.array([normalize_ts(r[6], unit) for r in rows], dtype=np.int64)}
    for name, idx in zip(FIELDS, (1, 2, 3, 4, 5, 7)):  # amount = quote asset volume
        out[name] = np.array([float(r[idx]) for r in rows], dtype=np.float64)
    return out


def parse_klines_zip(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise DataError(f"{path}: expected exactly one csv, found {names}")
        return parse_klines_text(z.read(names[0]).decode("utf-8"))


# ---------------------------------------------------------------- validation
def validate_arrays(open_time, open_, high, low, close, volume) -> dict:
    """Health report only: counts and timestamps, no returns or accuracy figures."""
    t = np.asarray(open_time, dtype=np.int64)
    n = len(t)
    d = np.diff(t)
    gaps = []
    for i in np.nonzero(d > HOUR_MS)[0]:
        missing = int(d[i] // HOUR_MS) - 1
        gaps.append({"first_missing": iso(int(t[i]) + HOUR_MS), "last_missing": iso(int(t[i + 1]) - HOUR_MS),
                     "missing_bars": missing, "aligned": bool(d[i] % HOUR_MS == 0)})
    arrs = [np.asarray(a, dtype=np.float64) for a in (open_, high, low, close, volume)]
    o, h, l, c, v = arrs
    with np.errstate(invalid="ignore"):
        rep = {
            "rows": int(n),
            "first_bar": iso(int(t[0])) if n else None,
            "last_bar": iso(int(t[-1])) if n else None,
            "duplicates": int((d == 0).sum()),
            "duplicate_timestamps": [iso(int(x)) for x in t[1:][d == 0]],
            "out_of_order": int((d < 0).sum()),
            "misaligned_open_times": int((t % HOUR_MS != 0).sum()),
            "gaps": gaps,
            "missing_bars_total": int(sum(g["missing_bars"] for g in gaps)),
            "high_below_max_open_close": int((h < np.maximum(o, c)).sum()),
            "low_above_min_open_close": int((l > np.minimum(o, c)).sum()),
            "high_below_low": int((h < l).sum()),
            "negative_volume": int((v < 0).sum()),
            "nan_values": int(sum(np.isnan(a).sum() for a in arrs)),
            "last_bar_closes_by_2026-11-01": bool(n > 0 and int(t[-1]) + HOUR_MS <= DEADLINE_MS),
        }
    rep["ok"] = (rep["duplicates"] == 0 and rep["out_of_order"] == 0 and rep["misaligned_open_times"] == 0
                 and not gaps and rep["high_below_max_open_close"] == 0 and rep["low_above_min_open_close"] == 0
                 and rep["high_below_low"] == 0 and rep["negative_volume"] == 0 and rep["nan_values"] == 0
                 and rep["last_bar_closes_by_2026-11-01"])
    return rep


# ---------------------------------------------------------------- series + windows
@dataclass
class Series:
    open_time: np.ndarray  # int64 ms, bar open
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    amount: np.ndarray

    @property
    def close_time(self) -> np.ndarray:
        """Binance convention: open + 1h - 1 ms."""
        return self.open_time + HOUR_MS - 1

    def __len__(self) -> int:
        return len(self.open_time)

    def slice(self, i: int, j: int) -> "Series":
        return Series(*(getattr(self, f)[i:j] for f in ["open_time"] + FIELDS))

    def copy(self) -> "Series":
        return Series(*(getattr(self, f).copy() for f in ["open_time"] + FIELDS))


def _contiguous(series: Series, start_ms: int, n: int) -> int | None:
    """Index of the first bar if exactly n consecutive hourly bars start at start_ms, else None."""
    t = series.open_time
    i = int(np.searchsorted(t, start_ms, side="left"))
    if i + n > len(t) or t[i] != start_ms:
        return None
    if not np.array_equal(t[i:i + n], start_ms + HOUR_MS * np.arange(n, dtype=np.int64)):
        return None
    return i


def build_context(series: Series, origin, lookback: int = LOOKBACK) -> Series:
    """The `lookback` bars with close_time <= origin, which must be consecutive hourly bars ending at origin-1h.

    Never returns a stretched or partial context: raises MissingBarError instead.
    """
    o = to_ms(origin)
    n_closed = int(np.searchsorted(series.close_time, o, side="right"))  # bars with close_time <= o
    i = _contiguous(series, o - lookback * HOUR_MS, lookback)
    if i is None or i + lookback != n_closed:
        raise MissingBarError(f"context for {iso(o)} is not {lookback} consecutive closed hourly bars")
    ctx = series.slice(i, i + lookback)
    assert len(ctx) == lookback and ctx.close_time.max() <= o
    return ctx


def label_bars(series: Series, origin, h: int = HORIZON) -> Series:
    """The h consecutive hourly bars opening at origin .. origin+(h-1)h."""
    o = to_ms(origin)
    i = _contiguous(series, o, h)
    if i is None:
        raise MissingBarError(f"labels for {iso(o)} are not {h} consecutive hourly bars")
    return series.slice(i, i + h)


def origin_is_valid(series: Series, origin) -> bool:
    try:
        build_context(series, origin)
        label_bars(series, origin)
        return True
    except MissingBarError:
        return False


def origin_failure_reason(series: Series, origin) -> str | None:
    """None if valid, else 'context', 'labels' or 'context+labels' (for per-pair exclusion counts)."""
    bad = []
    for name, fn in (("context", build_context), ("labels", label_bars)):
        try:
            fn(series, origin)
        except MissingBarError:
            bad.append(name)
    return "+".join(bad) or None


# ---------------------------------------------------------------- processed CSV I/O
def write_processed(series: Series, path: Path, rows: slice | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    s = series if rows is None else series.slice(rows.start or 0, rows.stop)
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["timestamps", "open", "high", "low", "close", "volume", "amount"])
        for k in range(len(s)):
            w.writerow([iso(int(s.open_time[k]))] + [repr(float(getattr(s, n)[k])) for n in FIELDS])


def load_csv(path: Path) -> Series:
    with open(path, newline="") as f:
        r = csv.reader(f)
        header = next(r)
        assert header == ["timestamps", "open", "high", "low", "close", "volume", "amount"], header
        rows = list(r)
    cols = {n: np.array([float(x[1 + i]) for x in rows]) for i, n in enumerate(FIELDS)}
    return Series(np.array([parse_iso(x[0]) for x in rows], dtype=np.int64), **cols)


def load_series(pair: str, processed_dir: Path = PROCESSED_DIR) -> Series:
    return load_csv(Path(processed_dir) / f"{pair}_1h.csv")


def build_series(pair: str, raw_dir: Path = RAW_DIR, months=MONTHS) -> tuple[Series, dict]:
    """Concatenate verified monthly zips in month order. Returns (series, {unit per file})."""
    parts, units = [], {}
    for ym in months:
        p = parse_klines_zip(Path(raw_dir) / pair / file_name(pair, ym))
        units[ym] = p["unit"]
        parts.append(p)
    cat = lambda k: np.concatenate([p[k] for p in parts])
    return Series(cat("open_time"), *(cat(n) for n in FIELDS)), units
