---
name: fichero-test
description: Run the Fichero verification gate (scripts/verify_all.sh) at the right tier, read the JSON report, and file failures as issues. Manager/integrator lane — workers never run this.
---

# /fichero-test

`scripts/verify_all.sh` is the one gate. Everything else (`verify_fast.sh`,
`verify_python.sh`, individual `scripts/check_*.py`) is a leg it calls.

## Who runs this

**The manager or integrator, from the repo ROOT, one at a time.** Several contract
checks read source via root-relative paths and give false results elsewhere.

- **Workers never run this.** Workers are commit-only: they write tests, they don't
  execute pytest or `xcodebuild`. The machine is slow; the manager gates serially.
- **Never on Daniel's active desktop** at `--full`, and never `xcodebuild test`
  there — the platform legs launch GUI windows. Use a worktree, or stay at
  `--standard`.
- One `xcodebuild` at a time, machine-wide.

## Tiers

```bash
scripts/verify_all.sh              # --fast (default)
scripts/verify_all.sh --standard   # fast + backend pytest unit tests
scripts/verify_all.sh --full       # standard + platform legs (both by default)
scripts/verify_all.sh --full --macos
scripts/verify_all.sh --full --ios
```

| Tier | What runs | Who |
|---|---|---|
| `--fast` | swiftlint + ruff + `scripts/check_*.py` + `check_version_date.sh` + OpenAPI model sync | anyone, cheap |
| `--standard` | fast + backend pytest unit tests | manager, per merge |
| `--full` | standard + macOS / iOS build+test legs | manager, before release |

Platform legs can also be requested with `VERIFY_ALL_MACOS=1` / `VERIFY_ALL_IOS=1`.

## PYTHONPATH — the false-red trap

The shared `.venv` is editable-installed against Daniel's `~/code/fichero` checkout.
Running the backend suite from a **worktree** without an explicit `PYTHONPATH` gates
the *stale* tree — a green run that means nothing, or a red one that isn't yours.

```bash
PYTHONPATH=$PWD/fichero-server/src ~/code/fichero/.venv/bin/pytest fichero-server/tests/unit -q
```

Write-suites that are flag-gated need their `FICHERO_RUN_*` env var set, or they
silently skip.

## Read the report, don't scroll the log

Every run writes `build/verify_all_report.json`.

```bash
python3 scripts/render_verify_report.py            # human summary
scripts/verify_all.sh --standard --file-issues     # file de-duped GH issues on failure
```

`--file-issues` calls `scripts/verify_to_issues.sh --apply`: one issue per failing
check (and per failing pytest node), routed to the right milestone, and it writes
the manager flag `build/verify_all_needs_fixing.json`. Default is report-only; run
`scripts/verify_to_issues.sh` with no flags first to see what it *would* file.

For a bare pytest run, `python3 scripts/tests_to_issues.py <junit.xml>` does the
same from a JUnit XML.

## Never `&&`-chain a push to a test run

Parse the summary. Push **only** if `0 failed`. If red already landed on `main`:
revert, reopen the issues, then fix. A `pytest -k` subset skips the architecture
guardrails — any change that touches a persisted DB needs the **full** suite.

## Output

```
FICHERO VERIFY — <tier> — <date> — <sha>

Legs:     <n> passed / <n> failed
Report:   build/verify_all_report.json
Failures: <check or test node>, …

Verdict:  GREEN → safe to merge  /  RED → <issues filed | not filed>
```
