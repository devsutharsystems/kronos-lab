"""Kronos adapter: official KronosPredictor.predict() on MPS, eval mode, offline weights.

Follows docs/DECISIONS.md: eval() on model AND tokenizer, MPS only (no CPU fallback; the MPS fallback env
var is refused), predict() with sample_count=1, verbose=False, T=1.0, top_p=0.9, other arguments default.
kronos_lab/sampling.py is NOT used. pandas and torch are imported lazily so this file imports without them.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOK = ("NeoQuasar/Kronos-Tokenizer-base", "0e0117387f39004a9016484a186a908917e22426")
MOD = ("NeoQuasar/Kronos-small", "901c26c1332695a2a8f243eb2f37243a37bea320")
PRED_LEN = 24


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class KronosAdapter:
    def __init__(self):
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ.setdefault("HF_HOME", str(ROOT / ".cache" / "huggingface"))
        os.environ.setdefault("HF_HUB_CACHE", str(ROOT / ".cache" / "huggingface" / "hub"))
        if "PYTORCH_ENABLE_MPS_FALLBACK" in os.environ:
            raise SystemExit("PYTORCH_ENABLE_MPS_FALLBACK is set; it would silently run ops on CPU. Unset it.")
        import pandas as pd
        import torch

        self.pd, self.torch = pd, torch
        if not torch.backends.mps.is_available():
            print("MPS is not available; refusing to run (no CPU fallback).", file=sys.stderr)
            raise SystemExit(4)
        sys.path.insert(0, str(ROOT / "third_party" / "kronos"))
        from model import Kronos, KronosPredictor, KronosTokenizer

        self.tokenizer = KronosTokenizer.from_pretrained(TOK[0], revision=TOK[1])
        self.model = Kronos.from_pretrained(MOD[0], revision=MOD[1])
        self.training_after_load = {"model": self.model.training, "tokenizer": self.tokenizer.training}
        self.tokenizer.eval()
        self.model.eval()
        assert self.model.training is False and self.tokenizer.training is False
        self.predictor = KronosPredictor(self.model, self.tokenizer, device="mps", max_context=512)
        assert next(self.model.parameters()).device.type == "mps", "model parameters are not on MPS"
        assert next(self.tokenizer.parameters()).device.type == "mps", "tokenizer parameters are not on MPS"
        assert self.model.training is False and self.tokenizer.training is False

    def predict_one(self, inputs: dict, seed: int) -> list:
        """One independent sample_count=1 forecast. Returns the 24 predicted closes."""
        pd, torch = self.pd, self.torch
        df = pd.DataFrame(inputs["x"], columns=["open", "high", "low", "close", "volume", "amount"])
        x_ts = pd.Series(pd.to_datetime(inputs["x_times"]))
        y_ts = pd.Series(pd.to_datetime(inputs["y_times"]))
        torch.manual_seed(seed)
        out = self.predictor.predict(df, x_ts, y_ts, pred_len=PRED_LEN, T=1.0, top_p=0.9,
                                     sample_count=1, verbose=False)
        return [float(v) for v in out["close"].to_numpy()]

    def describe(self) -> dict:
        import numpy as np
        torch, pd = self.torch, self.pd
        hub = Path(os.environ["HF_HUB_CACHE"])
        w = {}
        for name, (repo, rev) in (("Kronos-small", MOD), ("Kronos-Tokenizer-base", TOK)):
            w[name] = _sha256(hub / f"models--{repo.replace('/', '--')}" / "snapshots" / rev / "model.safetensors")
        return {
            "torch": torch.__version__, "numpy_runtime": np.__version__, "pandas": pd.__version__,
            "device": "mps",
            "model_param_device": str(next(self.model.parameters()).device),
            "tokenizer_param_device": str(next(self.tokenizer.parameters()).device),
            "mps_is_available": bool(torch.backends.mps.is_available()),
            "model_training": self.model.training, "tokenizer_training": self.tokenizer.training,
            "training_flags_right_after_from_pretrained": self.training_after_load,
            "pytorch_enable_mps_fallback_set": "PYTORCH_ENABLE_MPS_FALLBACK" in os.environ,
            "weights_sha256": w,
        }

    def memory_stats(self) -> dict:
        t = self.torch.mps
        return {"mps_current_allocated_bytes": t.current_allocated_memory(),
                "mps_driver_allocated_bytes": t.driver_allocated_memory()}

    def empty_cache(self) -> None:
        self.torch.mps.empty_cache()
