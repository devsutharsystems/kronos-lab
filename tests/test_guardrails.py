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
