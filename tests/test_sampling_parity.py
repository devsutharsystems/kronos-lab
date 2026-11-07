"""Parity of kronos_lab.sampling against the ORIGINAL Kronos predictor, same seed, CPU.

Needs torch + cached weights (run under .venv-kronos with HF_HUB_OFFLINE=1); skipped otherwise.
Uses only the example CSV shipped with Kronos; compares outputs to each other, never to realised prices.
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("HF_HOME", str(ROOT / ".cache" / "huggingface"))
os.environ.setdefault("HF_HUB_CACHE", str(ROOT / ".cache" / "huggingface" / "hub"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

torch = pytest.importorskip("torch")
if not (ROOT / "third_party" / "kronos" / "model").exists():      # the Kronos source is fetched by scripts/fetch_kronos.sh, not committed
    pytest.skip("third_party/kronos source not present (run scripts/fetch_kronos.sh)", allow_module_level=True)
sys.path.insert(0, str(ROOT / "third_party" / "kronos"))
CSV = ROOT / "third_party" / "kronos" / "tests" / "data" / "regression_input.csv"
TOK = ("NeoQuasar/Kronos-Tokenizer-base", "0e0117387f39004a9016484a186a908917e22426")
MOD = ("NeoQuasar/Kronos-small", "901c26c1332695a2a8f243eb2f37243a37bea320")

# Tolerance: the wrapper inverse-scales each sample then averages; the original averages then
# inverse-scales. Equal in exact arithmetic, differ by float32 rounding only.
RTOL, ATOL = 1e-5, 1e-5
LOOKBACK, PRED = 512, 24


@pytest.fixture(scope="module")
def predictor():
    if not CSV.exists():
        pytest.skip("example CSV missing")
    from model import Kronos, KronosPredictor, KronosTokenizer
    try:
        tok = KronosTokenizer.from_pretrained(TOK[0], revision=TOK[1])
        mod = Kronos.from_pretrained(MOD[0], revision=MOD[1])
    except Exception as e:  # weights not cached
        pytest.skip(f"weights not available offline: {e}")
    tok.eval(); mod.eval()
    return KronosPredictor(mod, tok, device="cpu", max_context=512)


@pytest.fixture(scope="module")
def window():
    d = pd.read_csv(CSV)
    d["timestamps"] = pd.to_datetime(d["timestamps"])
    x = d.iloc[:LOOKBACK].reset_index(drop=True)
    return x, x["timestamps"], d["timestamps"].iloc[LOOKBACK:LOOKBACK + PRED].reset_index(drop=True)


@pytest.mark.parametrize("S,seed", [(1, 11), (5, 12)])
def test_mean_of_samples_matches_original(predictor, window, S, seed):
    from kronos_lab.sampling import predict_samples
    x, xt, yt = window
    torch.manual_seed(seed)
    orig = predictor.predict(x, xt, yt, PRED, T=1.0, top_k=0, top_p=0.9, sample_count=S, verbose=False)
    torch.manual_seed(seed)
    samples = predict_samples(predictor, [x], [xt], [yt], PRED, T=1.0, top_k=0, top_p=0.9, sample_count=S)
    assert samples.shape == (1, S, PRED, 6)
    assert np.isfinite(samples).all()
    np.testing.assert_allclose(samples.mean(axis=1)[0], orig.values, rtol=RTOL, atol=ATOL)
    if S > 1:  # samples are genuinely distinct paths
        assert not np.allclose(samples[0, 0], samples[0, 1])
