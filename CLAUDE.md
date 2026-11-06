# Kronos Lab: rules for every session in this repo

1. Work only inside this folder; quote paths with spaces.
2. Never add a git remote, push, or run gh; print the exact command for Dev instead.
3. No API keys, tokens or .env files. Public endpoints only.
4. Never execute third-party scripts. Code in third_party/kronos may only be imported after its source has been read and summarized to Dev.
5. Always `source scripts/env.sh` before Python; run df -h before any download over 100 MB.
6. 8 GB RAM: one model in memory at a time; batch sizes come from the measured spike, not guesses.
7. Until PREREGISTRATION.md is committed, never compute or print accuracy, hit rate, Brier or P&L on test-window data; pipeline health only (row counts, NaNs, timing).
8. Every number in README/site must be read from a file in results/; no hand-typed figures. Anything not pre-registered is labelled "exploratory".
9. Site uses no external CDN scripts or fonts.
10. Every report: what changed, exact commands with real output, test results, unverified/assumed items; max 20 lines.
11. Never modify global git config. If git has no user.name/email, tell Dev and stop.
