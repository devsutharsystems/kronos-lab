"""Download Kronos weights via from_pretrained into the project cache (env.sh). Run once, online."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "third_party" / "kronos"))
from model import Kronos, KronosTokenizer  # noqa: E402

# Revisions pinned to the HF repo sha recorded in docs/provenance/ (weights unchanged since 2025-06-30).
TOK = ("NeoQuasar/Kronos-Tokenizer-base", "0e0117387f39004a9016484a186a908917e22426")
MOD = ("NeoQuasar/Kronos-small", "901c26c1332695a2a8f243eb2f37243a37bea320")

tok = KronosTokenizer.from_pretrained(TOK[0], revision=TOK[1])
mod = Kronos.from_pretrained(MOD[0], revision=MOD[1])
print("tokenizer.training =", tok.training)
print("model.training     =", mod.training)
print("params: tokenizer", sum(p.numel() for p in tok.parameters()), "model", sum(p.numel() for p in mod.parameters()))
