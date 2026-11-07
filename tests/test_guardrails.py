import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF = "tests/test_guardrails.py"


def _tracked():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True).stdout
    return [p for p in out.decode().split("\0") if p]


def test_gitignore_entries():
    lines = (ROOT / ".gitignore").read_text().split()
    for entry in [".venv/", ".cache/", "data/raw/", "third_party/kronos/"]:
        assert entry in lines


def test_env_sh_paths_inside_project():
    cmd = f'source "{ROOT}/scripts/env.sh" && printf "%s\\n%s" "$HF_HOME" "$PIP_CACHE_DIR"'
    out = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, check=True).stdout.split("\n")
    for p in out:
        assert Path(p).resolve().is_relative_to(ROOT), p


def test_no_tracked_file_over_5mb():
    big = [p for p in _tracked() if (ROOT / p).is_file() and (ROOT / p).stat().st_size > 5 * 1024 * 1024]
    assert big == []


def test_no_secret_patterns_in_tracked_files():
    pats = [re.compile(r"sk-" r"[A-Za-z0-9]{20,}"), re.compile(r"hf_" r"[A-Za-z0-9]{20,}"), re.compile(r"api_key" r"\s*=")]
    hits = []
    for p in _tracked():
        if p == SELF:
            continue
        f = ROOT / p
        if not f.is_file():
            continue
        text = f.read_bytes().decode("utf-8", errors="ignore")
        for pat in pats:
            if pat.search(text):
                hits.append((p, pat.pattern))
    assert hits == []


def test_every_tracked_data_group_is_named_in_data_license():
    import subprocess
    root = Path(__file__).resolve().parent.parent
    files = subprocess.run(["git", "-C", str(root), "ls-files", "data", "results", "site/data", "docs/provenance"], capture_output=True, text=True).stdout.split()
    assert files
    groups = set()
    for f in files:
        if f.endswith(".gitkeep"):                           # empty-directory placeholders hold no data
            continue
        parts = f.split("/")
        if parts[0] == "site":
            groups.add("site/data/")
        elif parts[:2] == ["docs", "provenance"]:
            groups.add("docs/provenance/")
        elif len(parts) > 2:
            groups.add("/".join(parts[:2]) + "/")          # data/sample/, results/final/, results/export/, results/spike/
        else:
            groups.add(f)                                    # a file directly under results/, e.g. results/data_quality.json
    text = (root / "DATA_LICENSE.md").read_text()
    missing = sorted(g for g in groups if g not in text)
    assert not missing, f"not named in DATA_LICENSE.md: {missing}"
    assert "docs/spike_report.md" in text and "Not affiliated with or endorsed by Binance" in text and "Not financial advice" in text
    assert "Data: Binance Vision (data.binance.vision)" in text
