# Unified Verification Gate — Design

**Date:** 2026-05-20
**Status:** Draft for review
**Owner:** Daniel + Claude

## Goal

One gate that verifies the whole product — frontend (Swift app), backend/engine
(Python), and CLI (Python) — across **lint + build + run + test**, in a single
invocation. Two faces of the same gate:

1. **⌘U in Xcode** runs everything (simple mental model — no fast/full tiers).
2. **One terminal command** (`scripts/verify_all.sh`) runs the same everything,
   for Daniel and (later) the autoloop.

The gate is the long-term defense against contract drift like #1075: it proves
all three clients agree with the engine against the *same* seeded library.

## Scope

**In scope (this plan):**
- A single source-of-truth Python gate script + a single top-level command.
- A new **CLI live-contract test** (the CLI mirror of the Swift
  `AppEngineContractTests`) — closes the biggest gap (CLI is currently
  mock-only).
- **Unify the test database**: one seeder (`seed_test_library.py`) used by the
  Swift harness, the Python contract walker, and the new CLI test.
- Wire the Python gate into ⌘U via one Swift gate test.

**Out of scope (explicit follow-ups):**
- Extending the contract walker to POST/PUT/PATCH/DELETE + field-level value
  snapshots (the "every function returns expected stuff" expansion). Separate plan.
- Autoloop integration (`cascade_router` build_validate calling the gate every
  issue / every Nth). Separate plan, separate repo (`~/code/autoloop`).
- A literal GUI launch smoke (boot the `.app`, screenshot, quit). Fragile;
  the live contract tests already exercise the app's real service layer.

## The "everything" matrix

| Leg | Lint | Build | Run | Test |
|---|---|---|---|---|
| **Frontend (Swift app)** | swiftlint | xcodebuild (compile) | app service layer exercised live by `AppEngineContractTests` | 688 Swift tests + contract tests via ⌘U |
| **Backend/engine (Python)** | ruff | import-check | **start-smoke**: boot uvicorn, hit `/health`, serve seeded lib | backend unit pytest + integration contract walker |
| **CLI (Python)** | ruff | import-check (`import fichero.cli`) | real CLI commands against seeded lib | mocked `test_cli_*` + new live contract test |

Interpretations to confirm at review:
- **"xcode lint"** = swiftlint + a clean xcodebuild compile (errors fail;
  pre-existing warnings like the `#selector` ones are reported, not fatal). A
  full `xcodebuild analyze` pass can be added later if wanted.
- **"backend build + run"** = start-smoke (decided), *not* a briefcase bundle
  build. Briefcase remains a separate pre-ship step.
- **"frontend run"** = the live `AppEngineContractTests` driving the real Swift
  service layer against a running engine (not a GUI launch).

## Architecture

Single source of truth, two entry points, no double-running:

```
⌘U (Xcode)                          scripts/verify_all.sh (terminal / autoloop-later)
  │                                   │
  ├─ xcodebuild build  ───────────────┤  (compile = frontend build + "xcode lint")
  ├─ 688 Swift tests + AppEngine…     ├─ swiftlint            (frontend lint)
  └─ CrossLanguageGateTests ──┐       └─ xcodebuild test ─────┘  (runs ⌘U's whole Swift suite,
                              │                                    incl. CrossLanguageGateTests)
                              ▼
                    scripts/verify_python.sh   ← the Python gate (single source of truth)
                      ├─ ruff check            (backend + cli lint = "pylint")
                      ├─ backend unit pytest
                      ├─ integration contract walker   (GET endpoints, seeded)
                      ├─ backend start-smoke   (boot uvicorn + /health + serves seed)
                      ├─ cli import-smoke + real CLI run
                      ├─ cli mocked tests
                      └─ cli live-contract test (new)
```

- ⌘U gets the Swift legs natively (compile + Swift tests). The
  `CrossLanguageGateTests` test shells out to `verify_python.sh`, so ⌘U also
  runs every Python leg and **fails if any of them fail**.
- `verify_all.sh` = `swiftlint` + `xcodebuild test`. Because the gate test lives
  *inside* the Swift suite, that one `xcodebuild test` transitively runs the
  entire cross-language gate. Nothing is orchestrated twice; the autoloop later
  just calls `verify_all.sh`.

## Components

1. **`fichero-engine/scripts/verify_python.sh`** — the Python gate, single
   source of truth. Sets `PYTHONPATH=fichero-engine/src`. Runs each leg in
   order, prints a clear per-leg PASS/FAIL summary, exits non-zero on first (or
   any) failure. Legs: ruff → backend unit pytest → integration contract walker
   → backend start-smoke → cli import/run smoke → cli mocked tests → cli
   live-contract test. Idempotent; cleans up any engine/temp lib it starts.

2. **`tests/integration/test_cli_engine_contract.py`** (new) — the CLI mirror of
   `AppEngineContractTests`. Connect-or-spawn an engine, seed a library via the
   shared seeder, drive the CLI's real `FicheroClient` (the one in
   `cli/client.py`, not the dead generated client), assert returned
   values/counts/IDs == seeder ground truth for documents/workflows/
   entities/artifacts + a create→read→delete round-trip.

3. **Seeder unification** — replace the contract walker's inline `_seed(db)`
   (`test_contract_endpoint_walk.py`) with `seed_test_library.py`, and have the
   new CLI test use it too. One ground-truth library, validated by all three
   clients. Keep the seeder's "counts derived by querying the library back"
   property so expectations never hardcode.

4. **`fichero/fichero-tests/CrossLanguageGateTests.swift`** (new) — one
   `@MainActor` XCTest that runs `verify_python.sh` as a subprocess (reusing
   `EngineHarness.repoRoot()` to locate it), streams output as an
   `XCTAttachment`, and `XCTAssertEqual(process.terminationStatus, 0)`.
   `XCTSkip` (not fail) when the venv/script is absent, mirroring the harness,
   so a Swift-only environment still passes.

5. **`scripts/verify_all.sh`** (new) — top-level one-command entry point:
   `swiftlint` + `xcodebuild test -scheme Fichero -destination 'platform=macOS'
   -skipPackagePluginValidation`. This is what Daniel runs in a terminal and
   what the autoloop will call later.

## Key design considerations

- **Engine/port contention.** During one ⌘U run, three things may want an engine
  on :8765: the Swift `AppEngineContractTests`, the backend start-smoke, and the
  CLI live-contract test. All use the connect-or-spawn pattern (reuse a healthy
  :8765, else spawn). They must therefore **reuse a single engine** rather than
  fight for the port. The spawned engine must carry `FICHERO_PARENT_PID` (already
  done for the Swift harness) so it never orphans. The Python gate should prefer
  connecting to whatever engine is already up and select libraries per-request
  via the `X-Fichero-Library-Path` header.
- **No live-backend pollution.** Per existing guidance, the gate must not run
  against an engine Daniel is live-testing; it seeds disposable libraries under
  `/var/folders` and routes by header. (Memory: don't pollute the dev backend.)
- **Temp-dir cleanup.** The Swift harness currently leaves `fichero-itest-*`
  dirs in `/var/folders`; the unified seeder usage should clean up after itself.
- **Runtime.** ⌘U now runs the full cross-language gate every time (Daniel's
  explicit choice). Expect several minutes. Acceptable; fast/full tiering was
  declined.

## Success criteria

- `⌘U` (and `scripts/verify_all.sh`) run lint + build + run-smoke + tests for
  frontend, backend/engine, and CLI, and **fail loudly** if any leg fails.
- The new CLI live-contract test asserts CLI-over-HTTP == seeded ground truth.
- The Python contract walker, the CLI test, and the Swift harness all seed via
  the **same** `seed_test_library.py`.
- A green run leaves **no** orphan engine on :8765 and **no** leftover temp libs.
- The whole thing is one command (and one ⌘U), with `verify_python.sh` as the
  reusable single source of truth the autoloop will later call.
