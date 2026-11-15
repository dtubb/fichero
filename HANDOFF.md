# HANDOFF: #6600 perf + security lane (branch perf-review)

Brief: .builder-brief-perf-review-1.txt. End the final turn with `DONE <short sha>` once everything is committed.
Spec tag for built is `[OK]` (not `[BUILT]`).

## Done and committed
- Step 2.29 (lenses): fichero_builder/review_lenses.py, wired in scripts/harness_review.py; test_harness_review_lenses.py; checklist item 12; both bullets [OK].
- perf-method: scripts/perf_trial.py `judge_measure`/`compare`, scripts/perf_baseline.json (tolerances, empty figures), test in test_perf_trial.py. Bullet still [GAP] in spec: flip to [OK].
- fichero_builder/perf_rung.py + tests/test_perf_rung.py; security_rung.py + tests/test_security_rung.py (readers, thresholds, waiver lints).

## Generation 2: done and committed
- Builder tests (513) and test_perf_trial.py (21) green with the new RUNGS.
- harness.toml `[check.perf]`, `[check.security]` (enforce=false, pins all empty: nothing installed).
- security_lints tested on a real git repo; two real bugs fixed: `git grep -E` `\s` does not match on macOS (waiver counts were always 0), and `diff -U0` died on `diff.external=` (now `--no-ext-diff`). Skip and report-only tests for both rungs.
- harness_review.py: "SECURITY SCAN (new findings only)" from the ladder JSON's security rung `table`; tested.
- scripts/install_security_tools.sh (`--check`, `--write-pins`; tested only with stub binaries, never run for real).
- Spec: perf-method and scan-thresholds-and-waivers [OK]; perf-rung-engine and security-scan-rung [PARTIAL] with what is open; Step 2.30 Tests line; fixed a bare-filename Test citation on security-lens (check_spec_citations).

## Still open (needs the manager or a runner)
1. Run `scripts/install_security_tools.sh --write-pins` on the runner (installs software: not done here), then write the bandit and gitleaks baselines in their own batch and file `Security - *` issues.
2. Convert the perf tests to pytest-benchmark (see findings), write scripts/perf_baseline.json figures from three nights on the M4.
3. The app half of the perf rung (`perf-rung-app`) is untouched.

## Findings to tell the manager
- tests/perf: entity-list tests ran ~25 min each (verify_perf.sh header), whole suite ~50 min: cannot fit the 6-min budget. The seven perf tests are NOT converted to pytest-benchmark; needs a decision (a fast subset / smaller fixtures) and a run on the M4.
- The spec says the security rung runs remote with no git, but semgrep --baseline-commit and gitleaks need history. Implemented to run in the scratch tree (`where` here); remote form is open.
- osv: KEV list and "fix for direct dependency" are parameters of read_osv, not fed by the driver yet.
- Rungs are report-only (enforce=false) until measured.
