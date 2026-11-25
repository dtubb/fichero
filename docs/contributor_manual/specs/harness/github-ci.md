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
  Job `codeql` runs CodeQL for Python (ubuntu, `build-mode: none`). Swift is not in the matrix: Swift has no `none` mode, a
  manual build needs the Xcode project, and the project is in Xcode 27's format, which GitHub's hosted macOS runners cannot
  open (the same wall as `ci.swift-on-actions`). Swift comes back into the matrix, as a manual build, when a hosted runner has
  Xcode 27 or on a self-hosted runner; until then the Swift code has no CodeQL scan here. CodeQL results go to
  code scanning; blocking a merge on high or critical alerts is a repository ruleset setting. The owner switches on, in
  Settings > Code security: secret scanning, push protection, and code scanning as a required check on `integration`; these
  are settings, not code, and this workflow does not set them. Acceptance: the workflow triggers on `pull_request` to
  `integration` and on a schedule, names `security_scan_run.py`, reads the pins and `osv` from `harness.toml`, fails on a refused scanner, and its CodeQL matrix is Python only (Swift out, with the reason in a comment).
  Test: `fichero-server/tests/unit/scripts/test_github_ci_files.py::test_security_workflow_runs_on_prs_and_nightly_reuses_the_rungs_scanner_and_adds_codeql` in fichero-server/tests/unit/scripts/.

## Test workflow

- `ci.test-workflow` [PARTIAL] (#6600; the file and its shape test are in the tree, no run of it on GitHub has been read yet) — `.github/workflows/tests.yml` runs on pull requests to `integration`, on pushes to `lane-*` branches and to
  `integration`, and by hand; report-only (every job is `continue-on-error`, so a red run blocks nothing until the maintainer
  has read a few weeks of results). The Python tiers (`ci.python-tiers`) run on every trigger; the Swift job
  (`ci.swift-on-actions`) does not run on a lane push, because the Macs own Swift for lane checks. Public repositories pay
  nothing for these minutes. Acceptance: the workflow triggers on `pull_request` to `integration` and on `push` to `lane-*`
  and `integration`, has exactly the jobs `engine`, `contracts`, `builder` and `swift`, all `continue-on-error`, and the
  Python jobs enable the uv cache. Built (2026-11-25): the triggers and jobs above. Test:
  `fichero-server/tests/unit/scripts/test_github_ci_files.py::test_test_workflow_runs_on_prs_to_integration_report_only_with_a_cached_uv_engine_job_and_a_swift_job` in fichero-server/tests/unit/scripts/.

## Python test tiers on Actions

- `ci.python-tiers` [PARTIAL] (#6600; the jobs and their shape test are in the tree, no run of them on GitHub has been read yet) —
  GitHub Actions runs every Python tier a hosted runner can, one job per tier, in parallel, so a red names its tier and the
  builder can read each by name. The jobs (macos-15, arm64; uv with its cache): `engine`, the engine's `tests/unit` tier with the
  `check_spec_*` guards as its own `Spec guards` step (kept in this job because `ci.builder-reads-actions` reads exactly the
  `engine` job's `Spec guards` and `Unit tests` steps; a separate guards job would run them twice); `contracts`, the engine's
  `tests/contracts`; `builder`, the builder's own suite (`cd fichero-builder && python -m pytest tests -q`, stdlib plus pytest,
  uv's cache keyed on `fichero-builder/pyproject.toml`). The integration and perf tiers need models, libraries and a quiet
  machine and stay on the Macs. Acceptance: `tests.yml` has one job per tier it runs, named for the tier, each with a cached uv,
  none gated off a trigger. Test: `fichero-server/tests/unit/scripts/test_github_ci_files.py::test_each_python_tier_is_its_own_job_with_cached_uv_and_the_engine_job_keeps_the_steps_the_builder_reads`.

## Swift on Actions

- `ci.swift-on-actions` [PARTIAL] (#6600; the job and its shape test are in the tree, no run of it on GitHub has been read yet) —
  job `swift` of `tests.yml` builds the app scheme `Fichero (Dev Local)` (the one that does not embed the engine) with
  `build-for-testing` and runs the Swift unit tests (`-testPlan fichero -only-testing:FicheroTests`; never the UI plans), signing
  off, on the newest hosted macOS runner (`macos-26`). It selects its Xcode explicitly: the project needs Xcode 27
  (`LastUpgradeCheck = 2700`, deployment targets 27), so the job looks for `/Applications/Xcode_27*.app` and `xcode-select`s it;
  when the hosted image has none, a `Swift NOT RUN` notice names the Xcodes it has and every later step is skipped, so the job is
  not red and not green. DerivedData and the cloned Swift packages are cached under `.ci/`, keyed on the app project's
  `Package.resolved` and the Xcode major. It runs on pull requests, integration pushes and by hand, never on a lane push.
  Acceptance: the shape test below. Test:
  `fichero-server/tests/unit/scripts/test_github_ci_files.py::test_the_swift_job_selects_its_xcode_says_not_run_without_it_caches_by_package_resolved_and_skips_lane_pushes`.

## Xcode Cloud

- `ci.xcode-cloud-swift-only` [PARTIAL] (#6600; the repository side is in the tree, the App Store Connect side is the owner's
  and not done) — Xcode Cloud, if it is used, builds and tests Swift only: the app schemes and the Swift test target. It never
  runs Python: no engine tests, no guards, no engine (Briefcase) build. Python stays on GitHub Actions and the Macs.
  Built (2026-11-25): `fichero/ci_scripts/ci_post_clone.sh` (beside the project, where Xcode Cloud looks): it refuses a
  scheme that embeds the engine (`*Embedded*`, `App Store`) with its name, trusts the packages' plugins and macros, and starts
  no Python interpreter. Acceptance: every `ci_scripts/ci_*.sh` starts no Python and is executable. Test:
  `fichero-server/tests/unit/scripts/test_github_ci_files.py::test_xcode_cloud_scripts_never_start_python`.

  The workflows (what runs on which trigger):

  | Workflow | Start condition | Scheme | Actions |
  | --- | --- | --- | --- |
  | `Swift PR` | a pull request to `integration` whose changes touch `fichero/` | `Fichero (Dev Local)` | Build (macOS); Test (macOS) with test plan `fichero` (`FicheroTests` only) |
  | `Swift integration` | a push to `integration` touching `fichero/` | `Fichero (Dev Local)` | Build (macOS and iOS); Test (macOS) with test plan `fichero` |
  | (none) | lane branches, schedules, tags | — | lane checks stay on the Macs; UI plans and the embedded and App Store schemes never run here |

  Budget: the free tier is 25 compute hours a month. At about 15 to 25 minutes a run (a measured run will say), that is roughly
  60 to 100 runs a month, so the file-change condition matters: a PR that touches only `fichero-server/`, `scripts/` or docs
  starts no Xcode Cloud run. If a month's usage passes 20 hours, `Swift integration` is the one to switch off first; GitHub
  Actions (`ci.swift-on-actions`) stays the second reading.

  The owner's clicks (App Store Connect and Xcode; no worker or script does these):
  1. Xcode: open `fichero/fichero.xcodeproj`, Product > Xcode Cloud > Create Workflow, choose the `Fichero` app product, and
     grant Xcode Cloud access to the GitHub repository when asked (App Store Connect > Xcode Cloud > Settings > Source Code).
  2. Edit the workflow: name it `Swift PR`; Environment: the Xcode 27 release, macOS latest; Start Conditions: remove the default
     branch condition, add Pull Request Changes, source branch any, target branch `integration`, Files and Folders: `fichero/`.
  3. Actions: remove the default Archive; add Build (platform macOS, scheme `Fichero (Dev Local)`) and Test (platform macOS,
     scheme `Fichero (Dev Local)`, test plan `fichero`); Post-Actions: none.
  4. Duplicate it as `Swift integration`: Start Condition Branch Changes on `integration`, files `fichero/`; add Build for iOS.
  5. App Store Connect > Users and Access > Xcode Cloud usage: note the month's compute hours after the first week.

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
| Builder's own tests, contract tier | not yet read (`ci.python-tiers` runs them as jobs `builder` and `contracts`) | yes |
| Pinned checks, ready, diff bound, red-on-base, the build rung, Swift tests, perf, review | never | always |
| Nightly verify, DMG, notarize, smoke, publish | never | always |
