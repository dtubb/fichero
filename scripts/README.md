# Repository scripts

The scripts in this directory support development and release work. They are
shell, Python, or Ruby helpers; they are not part of the Python engine package.

## Development and verification

- `dev.sh`, `start-backend.sh`, and `launch-release.sh` run the local engine or
  app during development.
- `verify_all.sh`, `verify_fast.sh`, and `verify_python.sh` run the repository
  verification tiers described in [AGENTS.md](../AGENTS.md).
- The `check_*.py` scripts are focused repository guardrails for API, Swift,
  documentation, generated-client, and architecture invariants.
- `add-swift-file.rb` and `remove-swift-file.rb` maintain Xcode file references.

## Worktrees and issue flow

- `spawn-worker.sh` creates a milestone worker in a worktree under
  `$FICHERO_WORKTREES` and starts its tmux session.
- `setup-workers.sh` prepares the worker environment.
- `choose_next.py`, `dispatch_advisor.py`, and `file_issue.sh` support issue
  selection, sizing, and routing.
- `notify_manager.sh` sends a worker completion or blocker to the manager inbox.
- `tests_to_issues.py` turns recorded test failures into tracked issues.

## Builds and releases

Build, packaging, signing, release, migration, and smoke-test helpers are named
`build-*`, `release*`, `notarize.sh`, `migrate.py`, `smoke-*`, and
`validate_mas_bundle.sh`. Read the script's `--help` output and the relevant
Contributor Guide page before running one; several operate on external services
or release artifacts.
