#!/usr/bin/env bash
# Run spike configs strictly one at a time (never in parallel). Usage: scripts/run_spike.sh <device> <cfg>...
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/env.sh"
export HF_HUB_OFFLINE=1
OUT="$ROOT/results/spike"; mkdir -p "$OUT"
DEV="$1"; shift
for CFG in "$@"; do
  LOG="$OUT/${DEV}_${CFG}.log"
  /usr/bin/time -l "$ROOT/.venv-kronos/bin/python" "$ROOT/scripts/spike_kronos.py" --device "$DEV" --cfg "$CFG" > "$LOG" 2> "$LOG.time"
  RSS=$(awk '/maximum resident set size/{print $1}' "$LOG.time")
  FP=$(awk '/peak memory footprint/{print $1}' "$LOG.time")
  echo "$DEV $CFG exit-ok maxrss=${RSS:-NA} footprint=${FP:-NA}"
  grep -E "^(after from_pretrained|mps available)" "$LOG" || true
  grep '^RESULT ' "$LOG" | sed 's/^RESULT //' | python3 -I -c "
import sys,json
for l in sys.stdin:
    d=json.loads(l); d['maxrss_bytes_time_l']=int('${RSS:-0}'); d['peak_footprint_bytes_time_l']=int('${FP:-0}')
    print(json.dumps(d))" >> "$OUT/spike_raw.jsonl"
done
