# HANDOFF: #6600 perf + security lane (branch perf-review)

Brief: .builder-brief-perf-review-1.txt. End the final turn with `DONE <short sha>` once everything is committed.
Spec tag for built is `[OK]` (not `[BUILT]`).

## Done and committed
- Step 2.29 (lenses): fichero_builder/review_lenses.py, wired in scripts/harness_review.py; test_harness_review_lenses.py; checklist item 12; both bullets [OK].
- perf-method: scripts/perf_trial.py `judge_measure`/`compare`, scripts/perf_baseline.json (tolerances, empty figures), test in test_perf_trial.py. Bullet still [GAP] in spec: flip to [OK].
- fichero_builder/perf_rung.py + tests/test_perf_rung.py; security_rung.py + tests/test_security_rung.py (readers, thresholds, waiver lints).

## Written, uncommitted at handoff time (commit first)
- check_tool.py: Config fields `perf`/`security` ([check.perf], [check.security]), `perf()`, `security()`, `security_lints()`, RUNGS now (..guards, security, contract-current, since-guards, build, perf), `reuse` flag on _remote_build.
- scripts/perf_engine_run.py, scripts/security_scan_run.py (drivers, print PERF-RESULT / SECURITY-RESULT lines).
- test_work_verb.py adjusted for the new RUNGS (pending == build, perf).

## To do
1. Run all fichero-builder/tests and fichero-server/tests/unit/scripts/test_perf_trial.py; fix anything the new RUNGS broke (test_status_page etc.). Pre-existing ruff errors in test_check_raw_geometry_readers.py / test_check_store_wholesale_reload.py are not ours.
2. harness.toml: add `[check.perf]` and `[check.security]` (enforce=false, timeout_s, pins {bandit, semgrep, gitleaks, osv-scanner}, osv=false); harness.toml is under check_paths.
3. Tests for check_tool.security_lints against a real tmp git repo (bare nosec red, reason+issue passes, third nosemgrep red unless approved lambda, baseline raise) and for the rung's not-required/skip rows and report-only behaviour; add to test_perf_rung.py/test_security_rung.py.
4. harness_review.py: put the security rung's `table` (from the ladder JSON rung named "security") into the prompt under "SECURITY SCAN"; test that it matches the rung's table.
5. scripts/install_security_tools.sh reading pins from harness.toml (brew install semgrep gitleaks osv-scanner; uv tool install bandit; pytest-benchmark, pyinstrument in the runner venv). Pins must be confirmed real versions at install; none were installed or verified here. Write the two baselines (bandit, gitleaks) in their own batch; file Security - * issues. osv stays OFF until lane deps-security clears the Dependabot alerts.
6. Flip spec bullets to [OK] with real `Test:` lines (perf-method, perf-rung-engine, security-scan-rung, scan-thresholds-and-waivers) and Step 2.30 Tests line in docs/contributor_manual/specs/harness/dev-workflows.md, only for what is truly tested.

## Findings to tell the manager
- tests/perf: entity-list tests ran ~25 min each (verify_perf.sh header), whole suite ~50 min: cannot fit the 6-min budget. The seven perf tests are NOT converted to pytest-benchmark; needs a decision (a fast subset / smaller fixtures) and a run on the M4.
- The spec says the security rung runs remote with no git, but semgrep --baseline-commit and gitleaks need history. Implemented to run in the scratch tree (`where` here); remote form is open.
- osv: KEV list and "fix for direct dependency" are parameters of read_osv, not fed by the driver yet.
- Rungs are report-only (enforce=false) until measured.
