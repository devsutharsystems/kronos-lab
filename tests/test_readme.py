"""README trace test: every number, hash and date in README.md must come from a result file, the pre-registration, the deviations log,
the restart count, or the small allowlist below. README.md must equal the output of scripts/build_readme.py."""
import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

# One explicit derived value: the accuracy of an always-down rule is 1 minus the always-up accuracy (every analysis-set origin has a
# non-zero label). A README number is accepted by this rule only if it equals 1 - primary.always_up_accuracy, as a percentage rounded to the
# decimals shown. It is not a general "1 minus anything" pass.
DERIVED_ALWAYS_DOWN = None

# Protocol constants and notation allowed to appear without a source file (one comment each).
ALLOWLIST = {
    "256": "the SHA-256 algorithm argument in the shasum command of the reproduce block",
    "3.12.16": "interpreter version of the run environment, as stated by the author (Phase 1 environment check; its output is not in the repo)",
    "3.12": "Python series of the run environment (same source as 3.12.16) and of CI",
    "3.13": "first Python series on which the Phase 1 dry-run failed to resolve torch and the Kronos pins (author's account)",
    "3.15": "last Python series in that failed range (author's account)",
    "8010": "local port used in the serve command",
    "0.5": "chance level for a two-way call (definition of a coin flip)",
}


def load_builder():
    spec = importlib.util.spec_from_file_location("build_readme", ROOT / "scripts" / "build_readme.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def leaves(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from leaves(v)
    elif isinstance(o, list):
        for v in o:
            yield from leaves(v)
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        yield o


HEX = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{8,64}\b")
URL = re.compile(r"https?://[^\s)>\]]+")
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}(?:T[0-9:]+Z?)?|\b\d{2}:\d{2}(?::\d{2})?\b")
SCI = re.compile(r"\b\d+e-\d+\b")          # e.g. a stated tolerance; must appear in tests/test_analysis.py
NUM = re.compile(r"(?<![A-Za-z0-9_.])[+-]?(\d+(?:\.\d+)?)(?![A-Za-z0-9_])")


def sources():
    res_bytes = (ROOT / "results" / "final" / "results.json").read_bytes()
    texts = [(ROOT / n).read_text() for n in ("PREREGISTRATION.md", "DEVIATIONS.md")]
    dq = (ROOT / "results" / "data_quality.json").read_text()
    res = json.loads(res_bytes)
    # exploratory blocks are excluded as trace sources: the README must not cite exploratory figures, and they would only match by coincidence
    nums = {c for k, v in res.items() if not k.startswith("exploratory_") for c in leaves(v)} | {c for c in leaves(json.loads(dq))}
    text_tokens = {m.group(1) for t in texts for m in NUM.finditer(t)}
    # counts derived from restarts.log are cross-checked against DEVIATIONS.md inside the builder; both give the start count
    starts = int(re.search(r"restarts\.log has (\d+) starts", texts[1]).group(1))
    derived = 1 - json.loads(res_bytes)["primary"]["always_up_accuracy"]       # the one explicit derived value (see DERIVED_ALWAYS_DOWN above)
    nums |= {starts, starts - 1}
    joined = "\n".join(texts) + "\n" + dq + "\n" + res_bytes.decode()
    return nums, text_tokens, joined, hashlib.sha256(res_bytes).hexdigest(), derived


def is_commit(h):
    return subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", h + "^{commit}"], capture_output=True).returncode == 0


def untraced(text: str, always_down=None) -> list:
    nums, tokens, joined, res_sha, derived = sources()
    derived = derived if always_down is None else always_down
    bad = []
    hexes = HEX.findall(text)
    for h in hexes:
        ok = h == res_sha or h in joined or is_commit(h) or any(len(h) < 40 and x.startswith(h) for x in HEX.findall(joined))
        if not ok:
            bad.append(h)
    rest = HEX.sub(" ", text)
    rest = URL.sub(" ", rest)
    tol_src = (ROOT / "tests" / "test_analysis.py").read_text()
    for sc in SCI.findall(rest):
        if sc not in tol_src:
            bad.append(sc)
    rest = SCI.sub(" ", rest)
    for st in STAMP.findall(rest):
        if st not in joined:
            bad.append(st)
    rest = STAMP.sub(" ", rest)
    for m in NUM.finditer(rest):
        tok = m.group(1)
        d = len(tok.split(".")[1]) if "." in tok else 0
        x = float(tok)
        if tok in ALLOWLIST or tok in tokens:
            continue
        if d == 0:
            if int(x) in nums:
                continue
        elif any(round(abs(c) * k, d) == x for c in nums for k in (1, 100)):
            continue
        elif round(derived * 100, d) == x:
            continue
        bad.append(tok)
    return bad


def test_readme_matches_the_generator_output():
    b = load_builder()
    assert README.read_text() == b.render(), "README.md is out of date: run python3 scripts/build_readme.py"


def test_every_number_hash_and_date_in_readme_is_traced():
    assert untraced(README.read_text()) == []


def test_the_trace_check_is_not_vacuous():
    t = README.read_text()
    assert untraced(t + "\nKronos accuracy was 77.7% in 98765 origins.") == ["77.7", "98765"]
    assert untraced(t + "\nsee deadbeef12345678.") == ["deadbeef12345678"]
    assert untraced(t + "\non 2031-01-01.") == ["2031-01-01"]


def test_the_always_down_rule_is_narrow():
    t = README.read_text()
    p = json.loads((ROOT / "results" / "final" / "results.json").read_text())["primary"]["always_up_accuracy"]
    shown = f"{(1 - p) * 100:.1f}"
    assert f"would have scored {shown}%" in t and "descriptive, not pre-registered; no test was run" in t
    assert untraced(t) == []
    # without the rule (derived value replaced by one that does not match) the always-down figure is the only thing flagged
    assert untraced(t, always_down=0.0) == [shown]


def test_readme_banned_wording_and_required_notices():
    t = README.read_text()
    low = t.lower()
    assert "beats" not in low and "does not work" not in low
    assert "no detectable edge" in t and "Not financial advice." in t
    assert "Data: Binance Vision (data.binance.vision); not affiliated with or endorsed by Binance." in t
    assert "rerun everything from the hashes" not in low
    assert "bit-for-bit reproduction on other hardware is not claimed" in t
    assert "The forecast file is attached, gzipped, to the [release]" in t and "not in this repository" not in t
    assert "can be rerun if the forecast file is obtained" not in t


def test_readme_has_no_exploratory_figures():
    t = README.read_text().lower()
    for word in ("brier", "calibration", "persistence", "net return", "breakeven", "break-even"):
        assert word not in t, word
    for pair in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"):
        assert t.count(pair.lower()) <= 3          # pairs appear only in the quoted list and the hash table


# Every URL in the README must be on this list (the number trace strips URLs, so they are checked here). One comment per entry.
ALLOWED_URLS = {
    "https://devsutharsystems.github.io/kronos-lab/": "the live site (GitHub Pages project URL; owner and repo come from site/js/config.js)",
    "https://github.com/devsutharsystems/kronos-lab/releases/tag/v1.0.0": "the release that carries the gzipped forecast file",
}
ALLOWED_URL_PREFIXES = {
    "https://github.com/devsutharsystems/kronos-lab/blob/56fcbdee4cb4055eb75669af5e411c45f845994b/": "the pre-registration file at the pre-registration commit",
    "https://github.com/devsutharsystems/kronos-lab/commit/": "the DEVIATIONS commits, found in git by subject (hash is checked below)",
}


def test_every_url_in_the_readme_is_allowed():
    for u in re.findall(r"https?://[^\s)>\]`]+", README.read_text()):
        ok = u in ALLOWED_URLS or any(u.startswith(p) for p in ALLOWED_URL_PREFIXES)
        assert ok, f"URL not on the allowlist: {u}"
        if u.startswith("https://github.com/devsutharsystems/kronos-lab/commit/"):
            assert is_commit(u.rsplit("/", 1)[1]), u
    t = README.read_text()
    assert "<https://devsutharsystems.github.io/kronos-lab/>" in t and "/releases/tag/v1.0.0>" in t
    assert t.index("## Links") < t.index("## Result")
    # the site URL and the repo come from the same config file as the pre-registration link
    cfg = (ROOT / "site" / "js" / "config.js").read_text()
    assert "github.com/devsutharsystems/kronos-lab/blob/56fcbdee4cb4055eb75669af5e411c45f845994b/" in cfg
