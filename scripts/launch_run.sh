#!/usr/bin/env bash
# Launch the main Kronos Lab run with retries. Run it yourself in Terminal.app:
#   cd "$HOME/Documents/Lets Data Science/week7/kronos-lab" && caffeinate -dimsu bash scripts/launch_run.sh
# Up to 10 attempts; 30 s pause after a failed attempt; stops when the runner exits 0 or results/runs/DONE exists.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
source "$ROOT/scripts/env.sh"
export HF_HUB_OFFLINE=1
unset PYTORCH_ENABLE_MPS_FALLBACK
OUT="results/runs"
CUTOFF="2026-11-07T03:30:00Z"
mkdir -p "$OUT"
LOG="$OUT/launch.log"
log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"; }

for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if [ -f "$OUT/DONE" ]; then log "attempt $attempt: $OUT/DONE exists, stopping"; exit 0; fi
  log "attempt $attempt: start"
  "$ROOT/.venv-kronos/bin/python" -m kronos_lab.runner --out "$OUT" --cutoff "$CUTOFF" >> "$OUT/runner.out" 2>&1
  rc=$?
  log "attempt $attempt: exit code $rc"
  if [ "$rc" -eq 0 ] || [ -f "$OUT/DONE" ]; then log "stopping (exit $rc, DONE=$([ -f "$OUT/DONE" ] && echo yes || echo no))"; exit 0; fi
  [ "$attempt" -lt 10 ] && sleep 30
done
log "gave up after 10 attempts"
exit 1
