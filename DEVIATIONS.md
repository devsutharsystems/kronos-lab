# Deviations from PREREGISTRATION.md

## 2026-11-06 15:40:59 +0530: run-critical file count

Section 5 of PREREGISTRATION.md calls scripts/launch_run.sh "the sixth run-critical file"; the list has five and launch_run.sh is the fifth. Wording error only, no change to the protocol. Results had not been seen (results/runs/ does not exist).

## 2026-11-07 10:29:32 +0530: run closed after the cutoff

The pre-registered cutoff 2026-11-07T03:30:00Z passed while the run was paused by the author. The run was not completed.

- Interruptions: the run was interrupted by SIGINT and resumed twice. restarts.log has 3 starts: 2026-11-06T10:14:07Z (resumed_done=0), 2026-11-06T16:44:29Z (resumed_done=2007), 2026-11-06T16:48:29Z (resumed_done=2025). launch.log shows exit code 130 for attempts 1 and 2, and no exit line for attempt 3, which started at 2026-11-06T16:48:26Z; per the author, the launch script was stopped first and the runner then interrupted. The last write to forecasts.jsonl was at 2026-11-06T16:49:21Z (22:19:21 IST). The run was not resumed before the cutoff.
- Counts: forecasts.jsonl has 2031 lines, 2031 unique origins, all with status ok and 11 samples of 24 values. By stage: 1: 300, 2: 294, 3: 594, 4: 843 (stage 4 has 1188 in the full design). 345 of 2376 origins were never run, all in stage 4.
- Analysis set: exactly the origins present in forecasts.jsonl (sha256 e4018459424723023204b6a111c3fa6887e71057c9bc9578d95325623a56fc8b, 2031 lines). All were written before the cutoff. This follows section 10 of PREREGISTRATION.md ("The analysis set is the origins in forecasts.jsonl at the cutoff with all 11 samples complete").
- DONE: results/runs/DONE is written by hand, not by the runner, with the reason "cutoff_passed_while_paused". It is written after this entry is committed.
- No definition, test, seed or threshold is changed.
- Results had not been seen at the time of writing: no accuracy, hit rate or label was computed.
