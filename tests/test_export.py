"""CSV export tests. They read only results/final/results.json, results/export/* and the committed PREREGISTRATION.md."""
import csv
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results" / "final" / "results.json"
EXPORT = ROOT / "results" / "export"


def load_exporter():
    spec = importlib.util.spec_from_file_location("build_export", ROOT / "scripts" / "build_export.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def ex():
    return load_exporter()


@pytest.fixture(scope="module")
def res():
    return json.loads(RES.read_text())


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def same(csv_text: str, want) -> bool:
    """Exact comparison of a CSV cell with the JSON value it was copied from."""
    if isinstance(want, bool):
        return csv_text == ("true" if want else "false")
    if isinstance(want, int):
        return csv_text == str(want)
    if isinstance(want, float):
        return float(csv_text) == want and csv_text == repr(want)
    return csv_text == str(want)


def test_every_figure_equals_results_json_exactly(ex, res):
    rows = read_rows(EXPORT / "results_summary.csv")
    assert len(rows) > 100
    checked = 0
    for r in rows:
        keys = dict(part.split("=", 1) for part in r["source_key"].split("; ") if part)
        assert keys, r["test_id"]
        for col, path in keys.items():
            assert col in r and col in ex.SRC_COLS, (r["test_id"], col)
            assert same(r[col], ex.get(res, path)), (r["test_id"], col, path)
            checked += 1
        for col in ("value", "ci_low", "ci_high", "p_raw", "p_holm", "n", "decision"):
            if col not in keys:
                assert r[col] == "", (r["test_id"], col)               # blank where not applicable
    assert checked > 200


def test_columns_label_status_and_exploratory_rule(ex):
    rows = read_rows(EXPORT / "results_summary.csv")
    assert list(rows[0].keys()) == ex.COLUMNS
    assert all(r["label"].strip() for r in rows)
    assert len({r["test_id"] for r in rows}) == len([r["test_id"] for r in rows]), "test_id must be unique"
    primary_ids = {r["test_id"] for r in rows if r["section"] == "primary"}
    assert "H1_vs_coin_flip" in primary_ids and "H2_vs_always_up" in primary_ids and "kronos_accuracy" in primary_ids
    for r in rows:
        assert r["section"] in ("primary", "exploratory") and r["status"] == r["section"], r["test_id"]
        if r["section"] != "primary":
            assert r["status"] == "exploratory", r["test_id"]            # every non-primary row says so
        assert r["scope"] in ("all pairs", "pair") and (r["pair"] != "") == (r["scope"] == "pair"), r["test_id"]
    # exploratory content that results.json holds is present
    ids = {r["test_id"] for r in rows}
    assert {"accuracy_h1", "accuracy_h4", "accuracy_pair_BTCUSDT", "accuracy_stage_4", "persistence_accuracy_h24", "brier_kronos_h24",
            "magnitude_error_kronos_h1", "calibration_h24_k0", "cost_breakeven_fee"} <= ids


def test_missing_exploratory_status_would_be_caught(ex, res):
    rows = ex.build_rows(res)
    bad = [dict(r, status="") for r in rows if r["section"] == "exploratory"][:1]
    assert bad and all(r["status"] != "exploratory" for r in bad)       # the check in the test above would fail on such a row


def test_two_builds_are_byte_identical(ex, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    ex.build(ROOT, a)
    ex.build(ROOT, b)
    for name in ("results_summary.csv", "data_dictionary.csv", "README.md"):
        assert (a / name).read_bytes() == (b / name).read_bytes() == (EXPORT / name).read_bytes(), name


def test_file_format_utf8_lf_header_quoting():
    for name in ("results_summary.csv", "data_dictionary.csv", "README.md"):
        raw = (EXPORT / name).read_bytes()
        raw.decode("utf-8")
        assert b"\r" not in raw and raw.endswith(b"\n")
    first = (EXPORT / "results_summary.csv").read_text().splitlines()[0]
    assert first.startswith("section,test_id,label,") and "index" not in first.split(",")
    for r in read_rows(EXPORT / "results_summary.csv"):
        assert len(r) == 17


def test_dictionary_covers_columns_and_test_ids_and_quotes_prereg(ex):
    d = read_rows(EXPORT / "data_dictionary.csv")
    names = {(x["kind"], x["name"]) for x in d}
    for c in ex.COLUMNS:
        assert ("column", c) in names
    for r in read_rows(EXPORT / "results_summary.csv"):
        assert ("test_id", r["test_id"]) in names and ("metric", r["metric"]) in names
    prereg = (ROOT / "PREREGISTRATION.md").read_text()
    h1 = [x for x in d if x["name"] == "H1_vs_coin_flip"][0]
    assert "exact two-sided binomial test" in h1["definition"] and h1["quoted_from"].startswith("PREREGISTRATION.md section 7")
    assert re.search(r"H1:\*\* exact two-sided binomial test of the number of correct signals against 0\.5", prereg)
    assert all(x["definition"].strip() for x in d)


def test_readme_provenance_and_notices():
    t = (EXPORT / "README.md").read_text()
    assert hashlib.sha256(RES.read_bytes()).hexdigest() in t
    assert "56fcbdee4cb4055eb75669af5e411c45f845994b" in t and "CC BY-NC-SA 4.0" in t
    assert "Data: Binance Vision (data.binance.vision); not affiliated with or endorsed by Binance." in t
    assert "Not financial advice." in t and "All rows except the primary block are exploratory" in t


def test_results_final_files_are_untouched():
    assert hashlib.sha256(RES.read_bytes()).hexdigest() == "1128954d9675066c90d9154f902e5e54332189dfbd12cc2c8eff518ecfe3c937"
    assert hashlib.sha256((ROOT / "results" / "final" / "results_table.csv").read_bytes()).hexdigest() == \
        "dc06b9069916618e518550fcb6f996b741f4a9cfedf8d1fc07e68c2fcb6f8ec3"


def test_export_refuses_forbidden_output_dirs(ex, tmp_path):
    assert ex.main(["--root", str(ROOT), "--out", str(ROOT / "results" / "final")]) == 3
