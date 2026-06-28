# Test/QA Worker Report — API Surface & Test Harness batch

Worker: Claude. Branch: `lane/tests` (worktree `ms-tests`), reset to `origin/main`
(`82a865a3`) at start. Commits authored as Claude (`noreply@anthropic.com`) with
`Co-Authored-By: Daniel Tubb`. **Not pushed** — manager merges.

## Milestone & issues

**Test Coverage (#82) is drained for this lane** — only #1988 (App/private code,
not unit-testable) and #1939 (XCUITest harness, needs Xcode) remain.
**Auto-advanced** to the soonest-due open milestone with actionable issues:
**#70 API Surface & Test Harness** (due 2026-06-19, 11 open). Picked the
backend-test issues my lane can gate (ruff + pytest):

- **#1810 — [Testing] close backend test gaps (settings, extraction, dedup)** — advanced
- **#117 — [QA] Backend API Contract & Endpoint Audit** — advanced

Skipped the Swift/EPIC ones (#1672/#1671/#1670/#1666/#1443/#1407/#1406 are
generated-client / SwiftUI work; #1848/#1407 are EPICs; #1709 is Swift tests
needing Xcode). The XCUITest half of #1810 also needs the Xcode harness — I
covered the backend half.

## What was added (3 files, 22 tests)

| Issue | File | Under test | Coverage |
|-------|------|-----------|----------|
| #1810 / #1804 | `test_merge_dedup_claim_state.py` (5) | `merge_dedup_only._claim_target_state`, `_empty_summary` | conservative suppression contract: every action rejects, but only `disable` preserves confidence — `demote`/`prune` cap at 0.2 (and never raise an already-low score); empty-summary keys + all-zero |
| #1810 | `test_settings_validators.py` (10) | `settings._validate_provider_updates`, `_validate_profile` | unknown provider → 422 (names field); None/""/omitted provider fields skipped; non-provider `*_model` fields ignored; one bad provider among many rejected; profile needs name/provider/model + known provider |
| #117 | `test_library_header.py` (7) | `library_header.require_library_path`, `optional_library_path` | absent → None / 400; present → URL-decoded path (spaces/slashes); blank → "" / 400; non-empty-but-unusual value returned (emptiness gates, not validity) |

All target previously-untested logic (verified `testrefs=0` before writing),
focused on edges/contracts — not happy-path. The dedup confidence-cap and the
header 400/decode contract are exactly the silent-data / silent-failure risks
#1810 and #117 call out.

## Gate results (run from this worktree)

- `ruff check fichero-engine/src/` → **All checks passed** (tests only; no src changed)
- `pytest` on the 3 new files together → **22 passed, 0 failed** (no cross-pollution)

## Commits (newest first)

```
test: cover X-Fichero-Library-Path header dependencies (#117 contract audit)
test: cover settings ai-defaults + model-profile validators (#1810)
test: cover merge_dedup claim-suppression target state (#1810 / #1804)
```

## Notes for the manager

- #1810 and #117 are **advanced, not closed** — both are umbrella/checklist
  issues. Remaining #1810 work: XCUITest reactivation (Xcode), per-provider
  structured-extraction tests, extraction-schema #1803. Remaining #117: broader
  route-group contract sweeps (ingest/search/workflows) and Swift/OpenAPI
  contract compatibility.
- Nothing pushed.
