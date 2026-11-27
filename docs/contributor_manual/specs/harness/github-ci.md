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
  and `integration`, has exactly the jobs `engine`, `engine-macos`, `contracts`, `builder` and `swift`, all `continue-on-error`, and the
  Python jobs enable the uv cache. Built (2026-11-25): the triggers and jobs above. Test:
  `fichero-server/tests/unit/scripts/test_github_ci_files.py::test_test_workflow_runs_on_prs_to_integration_report_only_with_a_cached_uv_engine_job_and_a_swift_job` in fichero-server/tests/unit/scripts/.

## Python test tiers on Actions

- `ci.python-tiers` [PARTIAL] (#6600; the jobs and their shape tests are in the tree; the first run on integration, GitHub
  run 45666948572 of 2026-11-25, was read and its reds are below, and no Linux run of the engine tiers has been made here:
  this Mac has no Docker) — GitHub Actions runs every Python tier a hosted runner can, one job per tier, in parallel, so a
  red names its tier and the builder can read each by name. Until 2026-11-25 every job ran on macos-15 and the engine and
  contract jobs failed at install, which `continue-on-error` showed as green: Actions tested almost nothing. What runs where:

  | Job | Runner | What it runs |
  |---|---|---|
  | `engine` (twelve, `engine (1/12)`..`engine (12/12)`) | ubuntu-latest | the engine's `tests/unit` tier without `macos_only`, split by test file: `scripts/ci_shard_tests.py` deals every `test_*.py` under `tests/unit` to twelve shards, each file weighed by its `def test_` count, heaviest first to the lightest shard, so the shards together are the whole tier, are even by test count, and a new file or folder needs no workflow edit; each shard has a 30-minute job limit; shard 1 also runs the `check_spec_*` guards from the repo root as its `Spec guards` step, and its `Unit tests` step runs even when a guard is red |
  | `engine-macos` | macos-26 | exactly the `macos_only` tests of `tests/unit` and `tests/contracts`; when the engine does not install on the hosted runner, the `Install the engine` step says `NOT RUN:` with uv's reason in a notice and the job ends without red, and the tests are skipped (a NOT RUN is not a green; the Macs run these tests either way) |
  | `contracts` | ubuntu-latest | the engine's `tests/contracts` without `macos_only` |
  | `builder` | ubuntu-latest | the builder's own suite (stdlib plus pytest, uv's cache keyed on `fichero-builder/pyproject.toml`) |

  The engine jobs install with `uv sync --frozen --all-extras` from the one `fichero-server/uv.lock` on the engine's
  Python, 3.12 (the repo's `.python-version`; `setup-uv`'s `python-version`), never the runner's default: run 45666948572
  took 3.14 on Linux and 3.15 on macos-26, and onnxruntime 1.29.0 has no 3.15 wheel, which was why `engine-macos` failed
  at install. The Apple-only dependencies (the PyObjC frameworks of the `dev` extra; MLX is installed into the app at build
  time, not from the lock) carry `; sys_platform == 'darwin'`, so the same lock syncs on Linux and on macOS with every macOS
  version unchanged. The `engine` and `contracts` jobs then add the briefcase `requires` of
  `[tool.briefcase.app.fichero_server]` with uv.lock's versions as constraints, as `scripts/setup_venv.sh` does on the
  Macs (its step 2): spaCy's two language models come only from there. Kraken and htrmopo come only from the bundle's own
  install step, which needs a built bundle, so the runners have neither; a test that needs them starts with
  `pytest.importorskip`, as the suite's other Kraken tests do (the Macs' venv has them, `setup_venv.sh` fails without).
  An engine started with `$FICHERO_BASE_PATH` (every test engine) makes nothing under the home's Application Support: on a
  runner with no `~/Library/Application Support/Fichero`, each engine start in run 45676804358 made it and the real-state
  guard (#5530) failed 109 tests. No engine module imports an Apple framework at import time (each import is inside the function that
  needs it), so the package imports on Linux, and no memory or process reading goes through `ctypes.util.find_library`
  off macOS (there it shells out to `ldconfig`, and a page call hung on it under a fork in run 45666948572). A test that
  needs macOS itself (PyObjC, an Apple framework or Apple Vision's worker, a macOS tool such as `plutil`, `sips` or
  `hdiutil`, APFS behaviour) carries `@pytest.mark.macos_only` (registered in `pyproject.toml`; `tests/conftest.py` skips
  it off darwin with the reason); a test already skipped off macOS keeps its own `skipif` and gains the marker, so
  `engine-macos` runs it. Every pytest run in the workflow passes `--timeout=300 --timeout-method=thread` (pytest-timeout,
  in the `dev` extra; the gates' method, #6007) and `-rfE`, so a hang ends the run with each thread's stack and a red
  names its tests. Linux torch wheels pull the CUDA libraries, so a cold Linux install is large; uv's cache keeps it to one
  download per lock. The integration and perf tiers need models, libraries and a quiet machine and stay on the Macs.
  Acceptance: `tests.yml` has one job per tier it runs, named for the tier, each with a cached uv on Python 3.12, none
  gated off a trigger; the Linux jobs exclude `macos_only` and `engine-macos` runs only it or says NOT RUN; the shards
  cover the tier once and are even by test count; every pytest run has the per-test timeout. Tests:
  `fichero-server/tests/unit/scripts/test_github_ci_files.py::test_each_python_tier_is_its_own_job_with_cached_uv_and_the_engine_job_keeps_the_steps_the_builder_reads`,
  `::test_the_python_tiers_run_on_linux_with_the_unit_tier_in_twelve_shards_and_macos_runs_only_the_macos_only_tests`,
  `::test_the_shards_together_are_the_whole_unit_tier_each_entry_once`,
  `::test_apple_only_dependencies_carry_a_darwin_marker_so_the_lock_syncs_on_linux`,
  `::test_macos_only_is_a_registered_marker_that_skips_off_darwin_with_its_reason`.
  *Not proved:* a green Linux run of the engine shards. Run 45676804358 (the first complete one, every shard inside its
  limit) had 187 failed and 198 errors; the real-state, spaCy, Kraken, Apple Silicon, Apple Vision, macOS-tool and APFS
  ones are fixed or marked, and the rest are listed in the report of that commit for the next run to confirm.

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
  no Python interpreter. `fichero/ci_scripts/ci_pre_xcodebuild.sh`: for the test build only (`build-for-testing`,
  `test-without-building`) it deletes `keychain-access-groups` from `fichero/fichero/Fichero.entitlements` in Xcode Cloud's
  checkout. The unit tests run inside Fichero.app (TEST_HOST), and that restricted entitlement is honoured only with a
  provisioning profile listing the Mac; Xcode Cloud's test Mac is in none, and build 4's `Test - macOS` ended "Failed to
  install or launch the test runner" (RunningBoard error 5). The app already falls back when the keychain group is missing
  (`OwnerKeyStore.needsLocalFallback(-34018)`), and the host never starts an engine under XCTest (`isRunningXCTests`).
  Not proved until an Xcode Cloud run reads green: the error-5 cause is inferred, not read from a log. Acceptance: every
  `ci_scripts/ci_*.sh` starts no Python and is executable; the pre-xcodebuild script touches only that key, only for the
  test build. Test:
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
  secret is caught only by the gitleaks scan of `ci.security-workflow` and the builder's own security rung; the builder's `unit` rung
  pushes a batch head only after its own gitleaks scan and the land boundary patterns are clean (`ci.builder-reads-actions`).

## The builder reads the results

Still the design and not built (the `ci.builder-reads-actions` bullet below is what is built): the security rung's scanners may be
  taken from the `security.yml` job `scanners` the same way, and CodeQL alerts are read from code scanning for the head sha and listed in
  the review prompt under SECURITY SCAN as reported, never as a gate. The `build`, `perf`, red-on-base and review rungs never come from GitHub.

- `ci.builder-reads-actions` [PARTIAL] (#6600) — `builder check` takes the GitHub Actions run of the batch head as the `unit` rung.
  `[check].actions` in `harness.toml` lists the rungs Actions may supply (`["unit"]`; `guards` is not read from Actions: the
  `Spec guards` step runs only `check_spec_*.py` and runs the head's own workflow and scripts, so it is neither every guard nor the pinned copy);
  `[check].actions_timeout_s` (default 1500) is how long it waits. For a listed rung, in the loop with the loop's credentials
  (a worker never calls it): once the land boundary patterns (`[land].boundary`) have no hit over `since..head` and the `security` row shows gitleaks ran over the batch with no new finding (whatever `[check.security].enforce` says; a skipped, not-run or refused `security` row blocks it), the batch head is force-pushed to `refs/heads/lane-<lane>` on origin, where `<lane>` is the lane the loop is checking (`do_check` passes it down; never the HEAD of the engine repo, which judges every lane), and only when the head is the tip of that lane's `work-<lane>` ref (`tests.yml`
  runs its Python jobs on that push; `ci.Hosted.push`), then `ci.wait` polls the check runs of exactly that sha (the commit's `check-runs` endpoint)
  until all twelve `engine (N/12)` check runs are `completed`; they must belong to one Actions run, whose jobs are read through `ci.Hosted.jobs` for the conclusions of the
  step `Unit tests` (rung `unit`) of every `engine (N/12)` job (the `contracts` and `builder` jobs are not read). The rung is green only
  when all twelve jobs are present and each `Unit tests` step is `success`; fewer than twelve jobs is no usable run. The jobs are `continue-on-error`, so the run's own conclusion
  is never read. A green step is the rung's green and its row says `from GitHub run <id>`; a red step is the rung's red, with the
  tail of `gh run view <id> --job <job> --log-failed` of each red job (`ci.Hosted.failed_log`) as the fix brief. No finished run of that sha within the timeout, a run for another sha,
  no `gh`, no network, a boundary hit, a `security` row that is not a clean gitleaks scan (nothing is pushed), a failed push, a bad reply, no lane named, a lane name that is no branch name, a head that is not the tip of `work-<lane>`: the rung runs on the Macs as before and the
  journal gets one `check` row (`state = actions-local`) with the reason, and `unit` runs the selected tests on the Macs. Acceptance (a fake `gh`, a local bare origin; tests in
  `fichero-builder/tests/test_actions_rungs.py`): a green run (twelve `engine (N/12)` jobs) supplies the rung and the head is on origin; a red `Unit tests` step
  in any one shard is the rung's red with the failing lines; eleven shards, no run, a run for another sha, a run `in_progress`, a `gh` that exits non-zero, a rung
  not listed, no lane named, a head that is not the tip of `work-<lane>`, a lane name that is no branch name, a boundary hit, and a `security` row that is report-only with a gitleaks finding, skipped as not required, not run or missing each run locally and leave the bare origin without the head. A red already on the base is not told apart: the rung reads the whole engine tier of the head's run with no comparison against the base, so until the tier has a green Linux run (see *Not proved* under `ci.python-tiers`) a `unit` red may be a base red, and the fix brief carries the failing lines for the reader to judge. With the engine repo's HEAD on another lane's branch, only `lane-<lane>` of the checked lane is pushed. With no `[check].always_tests` the `unit` rung is off locally, and Actions does not turn it on: `local()` answers (the rung's skip) and nothing is pushed, whatever `[check].actions` lists. Built: the push and the `unit` rung (`guards` always runs locally), off in this repository: no `.toml` here sets `[check].always_tests`, so the `unit` rung is skipped and never reads Actions; not built: reading the security
  scanners and CodeQL alerts from Actions, and a real run against GitHub (nothing here has run `gh` for real yet).

## What the builder reads from Actions and what it runs on the Macs

- `ci.actions-or-local` [PARTIAL] (#6600) — each check has one place it may come from; the table says which. Everything Swift,
  red-on-base, perf and security stays on the Macs. Acceptance: every rung's row names its source, `local`, a runner, or
  `from GitHub run <id>`; a rung in the last two rows of the table never names a GitHub run (only the `unit` rung is
  wrapped by `from_actions`; `fichero-builder/tests/test_actions_rungs.py` covers a listed and an unlisted rung). No guard checks
  the table against the code yet.

| Rung | Where it runs |
| --- | --- |
| `unit` (engine `tests/unit`) | Actions `Unit tests` step of all twelve `engine` jobs when `[check].actions` lists `unit` and `[check].always_tests` is set (it is not in this repository, so the rung is skipped); no usable run: the selected tests run on the Macs |
| `guards` (every `scripts/check_*.py`) | the Macs, against the pinned copy; the Actions `Spec guards` step is not the rung |
| `ready`, `diff-bound`, `red-on-base`, `contract-current`, `since-guards` | the Macs |
| `security` (bandit, semgrep, gitleaks, osv-scanner) | the Macs; `security.yml` is not read yet |
| `build`, Swift tests, `perf`, review | the Macs, never Actions |

Not rungs, not read by the builder yet:

| Check | Where |
| --- | --- |
| CodeQL | code scanning alerts for the head; never run locally, never a gate in the builder |
| Dependabot | its pull requests and alerts live on GitHub |
| Builder's own tests, contract tier | the Macs; the `builder` and `contracts` jobs of `tests.yml` are not read yet (`ci.python-tiers`) |
| Nightly verify, DMG, notarize, smoke, publish | the Macs, never Actions |
