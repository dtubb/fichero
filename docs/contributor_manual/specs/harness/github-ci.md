# GitHub CI and security tools — Design Spec

> Milestone: harness
> Manual: contributor-facing.

> Tags: **[OK]** built and tested · **[PARTIAL]** built, partly proven or partly wired ·
> **[GAP]** intended, never built (needs an issue) · **[BROKEN]** regression, code
> contradicts the rule (needs an issue).

## Intent

The repository is public, so GitHub Actions (including macOS arm64 runners), CodeQL, secret scanning and Dependabot cost
nothing. They add a second, independent reading of every change beside the builder's own ladder; they do not replace
it. Spec-change: owner 2026-11-20.

## Dependabot

- `ci.dependabot` [GAP] — `.github/dependabot.yml` opens weekly update PRs (version and security) against `integration`
  for `fichero-server` (uv, reading `uv.lock`), the Swift packages under `fichero/` and `fichero/fichero-api-client`,
  and GitHub Actions. Minor and patch updates are grouped per ecosystem and labelled `dependencies` plus the ecosystem.
  Dependabot edits the manifests and `Package.resolved` itself; nobody edits a `Package.resolved` by hand.
  `fichero-builder` has no manifest or lock file today, so it has no entry; adding a `pyproject.toml` or requirements
  file there is what would bring it in. Acceptance: `.github/dependabot.yml` parses, is `version: 2`, and every entry has
  `target-branch: integration`, a weekly schedule and a `directory` that exists in the tree.
  Test: `fichero-server/tests/unit/scripts/test_github_ci_files.py::test_dependabot_yml_targets_integration_weekly_over_directories_that_exist` in fichero-server/tests/unit/scripts/.

## Security workflow

- `ci.security-workflow` [GAP] — `.github/workflows/security.yml` runs on pull requests to `integration` and nightly. It
  does not add a second scanner: job `scanners` runs the builder's security rung as it is (`scripts/install_security_tools.sh`,
  then `scripts/security_scan_run.py` with the pins of `harness.toml [check.security]` and the baselines under `scripts/`:
  bandit, semgrep, gitleaks), and reads osv-scanner's JSON over `fichero-server/uv.lock` and both Swift `Package.resolved`
  files with the rung's own `security_rung.read_osv` (CVSS 7.0 or above, known exploited, or a fix for a direct dependency).
  A red row fails the job; a `REFUSED` line (brew installed a scanner newer than the Macs' pin) is printed and does not fail.
  Job `codeql` runs CodeQL for Python (ubuntu) and Swift (macos-15, `build-mode: none`; if the Swift extractor refuses that
  mode the job is changed to a manual build, which needs the Xcode project and is not attempted here). CodeQL results go to
  code scanning; blocking a merge on high or critical alerts is a repository ruleset setting. The owner switches on, in
  Settings > Code security: secret scanning, push protection, and code scanning as a required check on `integration`; these
  are settings, not code, and this workflow does not set them. Acceptance: the workflow triggers on `pull_request` to
  `integration` and on a schedule, names `security_scan_run.py` and `read_osv`, and its CodeQL matrix is Python and Swift.
  Test: `fichero-server/tests/unit/scripts/test_github_ci_files.py::test_security_workflow_runs_on_prs_and_nightly_reuses_the_rungs_scanner_and_adds_codeql` in fichero-server/tests/unit/scripts/.

## Test workflow

- `ci.test-workflow` [GAP] — `.github/workflows/tests.yml` runs on pull requests to `integration`, report-only (every job is
  `continue-on-error`, so a red run blocks nothing until the maintainer has read a few weeks of results). Job `engine`
  (macos-15, arm64; uv with its cache keyed on `fichero-server/uv.lock`) runs every `scripts/check_spec_*.py` guard and
  then `pytest tests/unit` in `fichero-server`. Job `swift` (macos-15) builds the `Fichero (Dev Local)` scheme and runs its
  unit tests with signing off. Public repositories pay nothing for these minutes; the first runs are the measure of whether
  the Swift job fits in a run the builder can wait for, and if it does not it is split or moved to Xcode Cloud (see
  `reviews/2026-11-20-ci-review.md`). Acceptance: the workflow triggers on `pull_request` to `integration`, has exactly
  the jobs `engine` and `swift`, both `continue-on-error` on `macos-15`, and the engine job enables the uv cache.
  Test: `fichero-server/tests/unit/scripts/test_github_ci_files.py::test_test_workflow_runs_on_prs_to_integration_report_only_with_a_cached_uv_engine_job_and_a_swift_job` in fichero-server/tests/unit/scripts/.

## The builder reads the results

- `ci.builder-reads-actions` [GAP] — `builder check` may take a green GitHub Actions run for the same commit as one rung,
  so the three Macs do less. It is opt-in: `[check.github] use_actions = false` in `harness.toml`, off until the owner
  turns it on. How it reads a run, on the manager's side only (workers have no GitHub token and never call it):
  `gh run list --commit <head sha> --workflow tests.yml --json databaseId,status,conclusion` for the exact head sha of the
  batch, then the run's jobs through `gh api` (the Actions "list jobs for a workflow run" endpoint). The jobs are
  `continue-on-error`, which makes the run's own conclusion `success` even when a job failed, so the rung reads each JOB's
  conclusion and each step's conclusion, never the run's. The rung is satisfied only when the run is `completed`, its head
  sha equals the batch head exactly, and the `engine` job's steps `Spec guards` and `Unit tests` are `success`. It then
  stands in for the engine unit-test rung and the spec-guard rung of that batch, and the ladder row says
  `from GitHub run <id>`. A run that is missing, still running, for another sha, red, cancelled, or unreadable (no `gh`,
  no network, a bad reply) is never a pass: the rung runs on the Macs as it does today and the row says why the run was not
  used. The `build`, `perf`, red-on-base and review rungs never come from GitHub. The security rung's scanners may be taken
  the same way from the `security.yml` job `scanners`, and CodeQL alerts are read from code scanning for the head sha and
  listed in the review prompt under SECURITY SCAN as reported, never as a gate. Acceptance (no network, a fake `gh`): a
  completed run for the head sha whose `Unit tests` step succeeded satisfies the rung; the same run with the step failed,
  a run for the parent sha, a run still `in_progress`, a `gh` that exits non-zero, and `use_actions = false` each leave the
  rung to run locally with the reason in its row. Built: nothing yet; the workflows above are what it will read.
