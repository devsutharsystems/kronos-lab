"""Build README.md from README.template.md. Every figure is read from a file; nothing is typed here.

  python3 scripts/build_readme.py [--check]

Sources: results/final/results.json, results/data_quality.json, DEVIATIONS.md, PREREGISTRATION.md, site/js/config.js (repo URL),
git log (commit hashes, found by subject), and results/runs/restarts.log (count of starts only, when the file exists).
--check exits 1 if README.md differs from the generated text. Reads no price data and computes no statistic.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREREG_COMMIT = "56fcbdee4cb4055eb75669af5e411c45f845994b"
DEV_SUBJECTS = ("Deviation note: run-critical file count", "Deviation note: run closed at cutoff")
SERVE_PORT = 8010


def git_hash_by_subject(subject: str) -> str:
    r = subprocess.run(["git", "-C", str(ROOT), "log", "--format=%H%x09%s"], capture_output=True, text=True)
    hits = [h for h, _, s in (ln.partition("\t") for ln in r.stdout.splitlines()) if s == subject]
    if r.returncode or len(hits) != 1:
        raise RuntimeError(f"cannot find exactly one commit with subject {subject!r} (shallow clone? use fetch-depth 0)")
    return hits[0]


def repo_url() -> str:
    cfg = (ROOT / "site" / "js" / "config.js").read_text()
    return re.search(r"(https://github\.com/[^/]+/[^/]+)/blob/", cfg).group(1)


def count_starts(deviations_text: str, root: Path = ROOT) -> int:
    from_dev = int(re.search(r"restarts\.log has (\d+) starts", deviations_text).group(1))
    log = root / "results" / "runs" / "restarts.log"
    if log.exists():                                              # only the count of start lines is read
        n = sum(1 for ln in log.read_text().splitlines() if " start " in ln)
        assert n == from_dev, f"restarts.log has {n} starts, DEVIATIONS.md says {from_dev}"
    return from_dev


def prereg_section(text: str, number: int) -> list:
    out, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^## (\d+)\.", line)
        if m:
            cur = int(m.group(1)); continue
        if cur == number and line.startswith("- "):
            out.append(line[2:].strip())
    return out


def pct(x, d=1):
    return f"{x * 100:.{d}f}%"


def pp(x, d=1):
    return f"{x * 100:+.{d}f}"


def fields(root: Path = ROOT) -> dict:
    res = json.loads((root / "results" / "final" / "results.json").read_bytes())
    dq = json.loads((root / "results" / "data_quality.json").read_text())
    prereg = (root / "PREREGISTRATION.md").read_text()
    dev = (root / "DEVIATIONS.md").read_text()
    P, done = res["primary"], res["meta"]["done"]
    level = int(re.search(r"Percentile (\d+)% confidence", prereg).group(1))
    alpha = re.search(r"family alpha (0\.\d+)", prereg).group(1)
    assert P["decision_h1"] == P["decision_h2"] == "no detectable edge", "README prose is written for the 'no detectable edge' outcome"
    assert P["p_h2_holm"] < float(alpha) and P["ci_diff"][0] < 0 < P["ci_diff"][1] and P["p_h1_holm"] >= float(alpha)
    assert P["always_up_accuracy"] < 0.5
    planned, ndone, starts = done["total"], done["done"], count_starts(dev, root)
    url = repo_url()
    prereg_url = f"{url}/blob/{PREREG_COMMIT}/PREREGISTRATION.md"
    dev1, dev2 = (git_hash_by_subject(s) for s in DEV_SUBJECTS)
    stage_line = re.search(r"By stage: ([^.]*?)\)\.", dev)
    f = {}
    f["result_paragraph"] = (
        f"Kronos-small was tested on forecast origins at 00:00 UTC for {P['n_days']} days and {len(dq['pairs'])} pairs, {planned} planned in total. "
        f"The analysis set has {P['n']} origins (see below). At the primary horizon of {24} hours ahead, the pre-registered rule gave "
        f"**H1 (versus a coin flip): {P['decision_h1']}** and **H2 (versus always-up): {P['decision_h2']}**.\n\n"
        f"Kronos direction accuracy was {pct(P['accuracy'])} ({P['k_correct']} of {P['n']}), with a {level}% day-block bootstrap interval of "
        f"{pct(P['ci_accuracy'][0])} to {pct(P['ci_accuracy'][1])}. The largest edge over a coin flip that the interval does not rule out is "
        f"{pp(P['largest_edge_not_ruled_out_h1'])} percentage points. Always-up accuracy was {pct(P['always_up_accuracy'])}; Kronos minus always-up "
        f"was {pp(P['accuracy_diff'])} percentage points ({level}% interval {pp(P['ci_diff'][0])} to {pp(P['ci_diff'][1])}), and the largest gain over "
        f"always-up not ruled out is {pp(P['largest_gain_vs_always_up_not_ruled_out_h2'])} percentage points. "
        f"This describes this window, this model size and this sample size; smaller effects than these intervals can show are not excluded.")
    f["h2_note"] = (
        f"**Note on H2.** The exact test's Holm-adjusted p-value versus always-up was {P['p_h2_holm']:.3f}, which is below {alpha} on its own. "
        f"The pre-registered rule also requires the day-block interval for the accuracy difference to exclude zero; it runs from "
        f"{pp(P['ci_diff'][0])} to {pp(P['ci_diff'][1])} percentage points, so no edge is declared. Both numbers are reported. "
        f"The exact tests treat origins as independent, which is why the interval condition is part of the rule.")
    f["alwaysup_note"] = (
        f"**Always-up baseline (descriptive, not pre-registered).** Always-up accuracy is the share of analysis-set origins that closed up. "
        f"At {pct(P['always_up_accuracy'])} it is below one half: this window had more down days than up days, so always-up is a weak baseline here.")
    f["stop_paragraph"] = (
        f"The pre-registered cutoff ({re.search(r'cutoff (2026-[0-9T:-]+Z)', dev).group(1)}) passed while the run was paused, so it stopped with "
        f"{ndone} of {planned} origins ({planned - ndone} never run). The runner was started {starts} times: it was interrupted by SIGINT and resumed "
        f"{starts - 1} times, as the restart log records. The analysis set is exactly the origins present in `forecasts.jsonl` at the cutoff; "
        f"{P['n']} of them have a non-zero label and signal. Dates, counts and the file hash are in `DEVIATIONS.md`, whose entries are linked below. "
        f"Nothing in the definitions, tests, seeds or thresholds changed.")
    s3 = prereg_section(prereg, 3)
    s4 = [b for b in prereg_section(prereg, 4) if b.startswith(("Six spot pairs", "Forecast days", "Origin:"))]
    s5 = prereg_section(prereg, 5)[:3]
    q = [b.replace("**", "") for b in s3 + s4 + s5]
    f["question_block"] = "Quoted from `PREREGISTRATION.md`:\n\n" + "\n".join("- " + b for b in q) + (
        f"\n\nData checks (`results/data_quality.json`): {len(dq['pairs'])} pairs, interval {dq['interval']}, "
        f"{sum(v['missing_bars_total'] for v in dq['pairs'].values())} missing bars.")
    f["prereg_short"] = PREREG_COMMIT[:8]
    f["prereg_url"] = prereg_url
    f["dev1_title"], f["dev2_title"] = "run-critical file count", "run closed after the cutoff"
    f["dev1_url"], f["dev2_url"] = f"{url}/commit/{dev1}", f"{url}/commit/{dev2}"
    f["port"] = str(SERVE_PORT)
    rows = [("Processed series " + m.group(1), m.group(2)) for m in re.finditer(r"^\| ([A-Z]+USDT) \| `([0-9a-f]{64})` \|", prereg, flags=re.M)]
    assert len(rows) == 6
    rows += [("Kronos-small weights (model.safetensors)", re.search(r"Kronos-small `model\.safetensors` sha256 `([0-9a-f]{64})`", prereg).group(1)),
             ("Kronos-Tokenizer-base weights (model.safetensors)", re.search(r"Kronos-Tokenizer-base `model\.safetensors` sha256 `([0-9a-f]{64})`", prereg).group(1)),
             ("requirements-kronos.txt", re.search(r"`requirements-kronos\.txt` sha256 `([0-9a-f]{64})`", prereg).group(1)),
             ("results/runs/forecasts.jsonl (not in the repository)", re.search(r"sha256 ([0-9a-f]{64}), \d+ lines", dev).group(1)),
             ("results/final/results.json", hashlib.sha256((root / "results" / "final" / "results.json").read_bytes()).hexdigest())]
    f["hash_table"] = "| File | sha256 |\n|---|---|\n" + "\n".join(f"| {a} | `{b}` |" for a, b in rows)
    f["limits_quote"] = "\n".join("- " + b for b in prereg_section(prereg, 11))
    f["samples"] = str(res_samples(prereg))
    return f


def res_samples(prereg: str) -> int:
    return int(re.search(r"(\d+) samples were chosen", prereg).group(1))


def render(root: Path = ROOT) -> str:
    text = (root / "README.template.md").read_text()
    f = fields(root)
    for k, v in f.items():
        text = text.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[a-z0-9_]+\}\}", text)
    assert not left, f"unfilled fields: {left}"
    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = render()
    target = ROOT / "README.md"
    if a.check:
        return 0 if target.read_text() == text else 1
    target.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote README.md ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
