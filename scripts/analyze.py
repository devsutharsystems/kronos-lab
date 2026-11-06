"""Run the pre-registered analysis (sections 6-9).

  python scripts/analyze.py --root . --out results/final          REAL mode: refuses unless results/runs/DONE exists
  python scripts/analyze.py --synthetic --out results/synthetic_demo   SYNTHETIC mode: generated data, clearly labelled

Writes <out>/results.json and <out>/results_table.csv. Synthetic mode never touches results/runs,
data/processed or data/raw, and refuses to write into results/final or under results/runs.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # needed under `python -I`

from kronos_lab import analysis as A  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--out", required=True)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--B", type=int, default=A.B_BOOT)
    ap.add_argument("--seed", type=int, default=1, help="SYNTHETIC data seed (synthetic mode only)")
    ap.add_argument("--skill", type=float, default=0.1, help="SYNTHETIC predictor skill (synthetic mode only)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    if not out.is_absolute():
        out = Path.cwd() / out
    out = out.resolve()

    if a.synthetic:
        forbidden = [(ROOT / "results" / "final").resolve(), (ROOT / "results" / "runs").resolve()]
        if any(out == f or f in out.parents for f in forbidden):
            print(f"REFUSED: synthetic output may not go to {out}", file=sys.stderr)
            return 3
        inp = A.synthetic_inputs(seed=a.seed, skill=a.skill, rho=0.5)
        source, meta = "SYNTHETIC", {"seed": a.seed, "skill": a.skill, "rho": 0.5}
    else:
        inp, meta = A.load_real_inputs(a.root)      # raises unless results/runs/DONE exists
        source = "REAL"

    res = A.run_analysis(inp, B=a.B)
    out.mkdir(parents=True, exist_ok=True)
    payload = {"data_source": source, "meta": meta, **res}
    if source == "SYNTHETIC":
        payload = {"SYNTHETIC_DO_NOT_CITE": True, **payload}
    (out / "results.json").write_text(json.dumps(A.clean(payload), indent=1, allow_nan=False) + "\n")
    rows = A.results_table(res, source)
    cols = ["data_source", "section", "metric", "value", "ci_low", "ci_high", "p_raw", "p_holm", "n", "note"]
    with open(out / "results_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in A.clean(rows):
            w.writerow({k: ("" if r[k] is None else r[k]) for k in cols})
    p = res["primary"]
    print(f"{source}: N={p['n']} D={p['kronos_down_calls_D']} accuracy={p['accuracy']:.4f} "
          f"CI={[round(x, 4) for x in p['ci_accuracy']]} p_holm H1={p['p_h1_holm']:.4g} H2={p['p_h2_holm']:.4g}")
    print(f"{source}: {p['headline']}")
    print(f"wrote {out / 'results.json'} and {out / 'results_table.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
