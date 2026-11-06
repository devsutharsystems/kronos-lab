"""Pipeline health from forecasts.jsonl and health.jsonl ONLY. Standard library only.

Prints counts, shapes, finiteness and timing. It reads no price file and computes no accuracy,
hit rate, Brier or P&L.   Usage: python3 -I scripts/check_health.py [--dir results/runs]
"""
import argparse
import json
import statistics
import sys
from pathlib import Path


def check(run_dir) -> dict:
    run_dir = Path(run_dir)
    recs, bad_lines = [], 0
    fp = run_dir / "forecasts.jsonl"
    if fp.exists():
        for ln in fp.read_text().splitlines():
            try:
                recs.append(json.loads(ln))
            except ValueError:
                bad_lines += 1
    by_stage, statuses = {}, {}
    shape_bad = nonfinite = 0
    secs = []
    for r in recs:
        by_stage[r["stage"]] = by_stage.get(r["stage"], 0) + 1
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
        c = r.get("closes")
        if r["status"] in ("ok", "nan"):
            if not (isinstance(c, list) and len(c) == 11 and all(isinstance(x, list) and len(x) == 24 for x in c)):
                shape_bad += 1
            elif any(v is None or v != v or abs(v) == float("inf") for x in c for v in x):
                nonfinite += 1
            secs.append(r["seconds"])
    uniq = len({(r["pair"], r["date"]) for r in recs})
    health = []
    hp = run_dir / "health.jsonl"
    if hp.exists():
        health = [json.loads(l) for l in hp.read_text().splitlines() if l.strip()]
    return {"lines": len(recs), "unique_origins": uniq, "truncated_or_bad_lines": bad_lines,
            "done_per_stage": dict(sorted(by_stage.items())), "status_counts": statuses,
            "nan_count": statuses.get("nan", 0), "shape_11x24_bad": shape_bad, "origins_with_nonfinite": nonfinite,
            "all_shapes_ok": shape_bad == 0, "all_finite": nonfinite == 0,
            "median_seconds_per_origin": statistics.median(secs) if secs else None,
            "health_lines": len(health), "last_health": health[-1] if health else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(Path(__file__).resolve().parent.parent / "results" / "runs"))
    rep = check(ap.parse_args(argv).dir)
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
