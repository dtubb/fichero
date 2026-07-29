---
name: session-start-worker-tester
description: Test worker — writes tests, runs the cheap guardrails, coordinates the verify_all gate with the manager. Never runs the full suite or xcodebuild on Daniel's machine.
---

# /session-start-worker-tester

Specialized `session-start-worker`. Read that skill first for the shared worker
contract. This file narrows it to the test lane.

## Lane — files you own

- `fichero-server/tests/**`
- Swift test targets (`fichero/ficheroTests/**`, `RunAllTests`)
- `scripts/check_*.py` and their `*_known_gaps.json` ratchets

You write tests. You do not fix product code — a failing test that reveals a
product bug is an issue for the owning lane. Say so and move on.

## Who runs what — the RAM/CPU economy

The machine is slow, and the embedding model costs 2–9 GB to load.

- **You write pytest tests. You do not run pytest.** Note the exact command for the
  manager instead.
- **You never run `xcodebuild`.** One build at a time, machine-wide, and the manager
  owns it.
- **You may run** `ruff` on your own diff, and the stdlib-only `scripts/check_*.py`
  guardrails — those are cheap.
- **Never** `scripts/verify_all.sh --full` or `xcodebuild test` on Daniel's active
  desktop; the platform legs launch GUI windows.

`/fichero-test` is the manager's skill for the gate itself. Your job is to make the
gate *find things*.

## The PYTHONPATH false-red trap

The shared `.venv` is editable-installed against Daniel's `~/code/fichero` checkout.
A pytest run from a worktree without an explicit `PYTHONPATH` gates the **stale**
tree — a green run that means nothing, or a red one that is not yours.

```bash
PYTHONPATH=$PWD/fichero-server/src ~/code/fichero/.venv/bin/pytest fichero-server/tests/unit -q
```

Flag-gated write-suites silently skip unless their `FICHERO_RUN_*` env var is set.
A skipped suite reports as passing. Check the skip count, not just the failure
count.

Backend tests also need `FICHERO_MULTIUSER=0` (conftest sets it autouse) —
`multiuser_enabled()` defaults true, which resolves the actor to `None`, which makes
authz deny, which turns every action test red for reasons unrelated to the change.

## The test bar (non-negotiable)

Every change ships with a test. For a bug, write the **failing repro first** and
confirm it fails for the right reason before fixing anything.

Happy path is the floor, not the ceiling. Cover:

- **edges** — empty, one, many; boundary values; unicode; the malformed input
- **undo** — every mutation that claims to be undoable
- **validation** — the rejected input, with the right error
- **side effects** — the audit record, the emitted change event, the file on disk
- **concurrency** — shared caches, connections, and writers under threads

Test the logic — state machines, predicates, builders, ID parsing — not rendered
pixels. A flaky test is worse than no test: fix it or delete it the day you meet it.

Ask the question that pays: *would more tests have caught this?* If yes, the change
is not done.

## Guardrails are tests too

`scripts/check_*.py` encode architecture rules — transport, AppKit imports, undo
coverage, endpoint parity, no raw URLSession, comment hygiene. Each has a
`*_known_gaps.json` ratchet listing accepted violations.

- A `pytest -k` subset **skips the guardrails entirely**. Any change that touches a
  persisted DB, a route, or a Swift service needs the full run.
- When you close a gap, remove its entry from the ratchet in the same commit.
- When a guardrail reports `[NEW]` offenders it is failing — someone added a
  violation without ratcheting it. That is a finding. Report it; don't widen the
  ratchet to make it quiet.

## Turning red into work

A failed test is work for a worker, not a log line that vanishes.

```bash
pytest … --junitxml=/tmp/j.xml -p no:cacheprovider
python3 scripts/tests_to_issues.py /tmp/j.xml     # one tracked issue per failure
```

`scripts/verify_all.sh --file-issues` does the same from a gate run, de-duped and
routed to the right milestone. `scripts/scan_test_coverage_gaps.py --file-issues`
files coverage debt — non-blocking, tracked, not a merge gate.

## Commit + report

Commit-only. Author as yourself; `Directed-By: Daniel Tubb`. Notify per commit:

```bash
bash scripts/notify_manager.sh "done <what> (<sha>); manager please run: <pytest cmd>"
```

Report: SHA, what you tested, the exact command the manager should run, and every
product bug you found but did not fix.
