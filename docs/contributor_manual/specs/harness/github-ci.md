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

- `ci.dependabot` [PARTIAL] (#6600; the file and its shape test are in the tree, no run of it on GitHub has been read yet) — `.github/dependabot.yml` opens weekly update PRs (version and security) against `integration`
  for `fichero-server` (uv, reading `uv.lock`), the Swift package `fichero/fichero-api-client` (the one `Package.swift` under `fichero/`; Dependabot's swift ecosystem reads a `Package.swift`, not the Xcode project's `Package.resolved`, so the app project has no entry),
  and GitHub Actions. Minor and patch updates are grouped per ecosystem and labelled `dependencies` plus the ecosystem.
  Dependabot edits the manifests and `Package.resolved` itself; nobody edits a `Package.resolved` by hand.
  `fichero-builder` has no manifest or lock file today, so it has no entry; adding a `pyproject.toml` or requirements
  file there is what would bring it in. Acceptance: `.github/dependabot.yml` parses, is `version: 2`, and every entry has
  `target-branch: integration`, a weekly schedule and a `directory` that exists in the tree; a `swift` entry's directory holds a `Package.swift`.
  Test: `fichero-server/tests/unit/scripts/test_github_ci_files.py::test_dependabot_yml_targets_integration_weekly_over_directories_that_exist` in fichero-server/tests/unit/scripts/.

## Security workflow

- `ci.security-workflow` [PARTIAL] (#6600; the file and its shape test are in the tree, no run of it on GitHub has been read yet) — `.github/workflows/security.yml` runs on pull requests to `integration` and nightly. It
  does not add a second scanner: job `scanners` reads the pins and the `osv` switch from `harness.toml [check.security]`,
  installs bandit and semgrep by `uv tool install` and gitleaks from its release at exactly those pinned versions (osv-scanner
  too, only when `osv` is true), then runs `scripts/security_scan_run.py` with those pins and the baselines under `scripts/`:
  bandit, semgrep, gitleaks, and osv-scanner over the Python lock and both Swift `Package.resolved` files read by the rung's
  `security_rung.read_osv` only when `osv = true` (it is false while lane deps-security has open alerts, and the workflow
  follows it, so a PR is not red for an alert it did not cause). A red row fails the job, and so does a `REFUSED` line or a
  scanner that wrote no JSON: a scanner that did not run is never a green.
  Job `codeql` runs CodeQL for Python (ubuntu) and Swift (macos-15, `build-mode: none`; if the Swift extractor refuses that
  mode the job is changed to a manual build, which needs the Xcode project and is not attempted here). CodeQL results go to
  code scanning; blocking a merge on high or critical alerts is a repository ruleset setting. The owner switches on, in
  Settings > Code security: secret scanning, push protection, and code scanning as a required check on `integration`; these
  are settings, not code, and this workflow does not set them. Acceptance: the workflow triggers on `pull_request` to
  `integration` and on a schedule, names `security_scan_run.py`, reads the pins and `osv` from `harness.toml`, fails on a refused scanner, and its CodeQL matrix is Python and Swift.
  Test: `fichero-server/tests/unit/scripts/test_github_ci_files.py::test_security_workflow_runs_on_prs_and_nightly_reuses_the_rungs_scanner_and_adds_codeql` in fichero-server/tests/unit/scripts/.

## Test workflow

- `ci.test-workflow` [PARTIAL] (#6600; the file and its shape test are in the tree, no run of it on GitHub has been read yet) — `.github/workflows/tests.yml` runs on pull requests to `integration`, report-only (every job is
  `continue-on-error`, so a red run blocks nothing until the maintainer has read a few weeks of results). Job `engine`
  (macos-15, arm64; uv with its cache keyed on `fichero-server/uv.lock`) runs every `scripts/check_spec_*.py` guard and
  then `pytest tests/unit` in `fichero-server`. Job `swift` (macos-15) builds the `Fichero (Dev Local)` scheme and runs its
  unit tests with signing off. Public repositories pay nothing for these minutes; the first runs are the measure of whether
  the Swift job fits in a run the builder can wait for, and if it does not it is split or moved to Xcode Cloud (see
  `reviews/2026-11-20-ci-review.md`). Acceptance: the workflow triggers on `pull_request` to `integration`, has exactly
  the jobs `engine` and `swift`, both `continue-on-error` on `macos-15`, and the engine job enables the uv cache.
  Test: `fichero-server/tests/unit/scripts/test_github_ci_files.py::test_test_workflow_runs_on_prs_to_integration_report_only_with_a_cached_uv_engine_job_and_a_swift_job` in fichero-server/tests/unit/scripts/.

## Dependency and security audits

- `ci.dependency-audit` [PARTIAL] (#6600) — one auditor reads both sides, not one per language: osv-scanner reads the engine's
  `fichero-server/uv.lock` and both Swift `Package.resolved` files (the app project's, which Dependabot cannot read, and
  the api-client package's), and `security_rung.read_osv` in `fichero-builder/fichero_builder/security_rung.py` turns
  its findings into the rung's rows. pip-audit is not added: it would read the same advisories for the Python lock
  alone. Swift advisories arrive the same way, and as Dependabot security alerts for the api-client package. Built:
  the reader, the pinned version and the workflow step. Left: `harness.toml [check.security] osv = false`, so neither
  the rung nor the workflow runs it today; it is switched on when the open alerts are cleared. Acceptance: with
  `osv = true` a vulnerable pin in a fixture lock is a red row naming the package and the advisory, for the Python
  lock and for a `Package.resolved`; with `osv = false` the row says not run, never green.

## Python test tiers on Actions

- `ci.python-tiers` [GAP] (#6600) — GitHub Actions runs every Python tier a hosted runner can, one job per tier, so the
  builder can read each by name. Built: the engine's `tests/unit` tier and the `check_spec_*` guards
  (`ci.test-workflow`). Left: the builder's own suite (`fichero-builder/tests`) and the engine's contract tier
  (`fichero-server/tests/contracts`) have no job. The integration and perf tiers need models, libraries and a quiet
  machine and stay on the Macs. Acceptance: `tests.yml` has one job per tier it runs, named for the tier, and the
  shape test in `fichero-server/tests/unit/scripts/test_github_ci_files.py` names each.

## Xcode Cloud

- `ci.xcode-cloud-swift-only` [GAP] (#6600) — Xcode Cloud, if it is used, builds and tests Swift only: the app schemes and
  the Swift test target. It never runs Python: no engine tests, no guards, no engine (Briefcase) build. Python stays on
  GitHub Actions and the Macs. Nothing is configured today: the tree holds no Xcode Cloud workflow or script, and the
  Swift job runs on Actions (`ci.test-workflow`) until its measured time says it should move. Acceptance: a custom
  script added for Xcode Cloud starts no Python interpreter, and a test of the CI files says so.

## Repository settings

- `ci.settings-are-the-owners` [GAP] (#6600) — secret scanning, its push protection, Dependabot alerts and security
  updates, and code scanning as a required check on `integration` are repository settings. The owner switches them
  on; no workflow, script or builder verb sets them, and a worker has no token that could. Until they are on, a
  secret is caught only by the gitleaks scan of `ci.security-workflow` and the builder's own security rung, after the
  push, not before it.

## The builder reads the results

- `ci.builder-reads-actions` [GAP] (#6600) — `builder check` may take a green GitHub Actions run for the same commit as one rung,
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

## What the builder reads from Actions and what it runs on the Macs

- `ci.actions-or-local` [GAP] (#6600) — each check has one place it may come from. Today every row below is run on the
  Macs: `harness.toml` has no `[check.github]` table and `fichero-builder/fichero_builder/check_tool.py` has no reader
  (`ci.builder-reads-actions`). Acceptance: every rung's row names its source, `local`, a runner, or
  `from GitHub run <id>`; a rung in the last two rows of the table never names a GitHub run.

| Check | Read from GitHub | Run on the Macs |
| --- | --- | --- |
| Engine unit tests, spec guards | a green `tests.yml` job for the exact head, when `use_actions` is on | otherwise, and always when the run is missing, red or unreadable |
| bandit, semgrep, gitleaks, osv-scanner | the `scanners` job of `security.yml`, the same way | otherwise |
| CodeQL | code scanning alerts for the head, listed for the reviewer | never run locally; never a gate in the builder |
| Dependabot | its pull requests and alerts live on GitHub | nothing in the builder reads them yet |
| Builder's own tests, contract tier | not yet (`ci.python-tiers`) | yes |
| Pinned checks, ready, diff bound, red-on-base, the build rung, Swift tests, perf, review | never | always |
| Nightly verify, DMG, notarize, smoke, publish | never | always |
