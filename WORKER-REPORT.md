# Test/QA Worker Report — Test Coverage batch

Worker: Claude. Branch: `lane/tests` (worktree `ms-tests`), reset to `origin/main`
(`c224697b`) at start. Commits authored as Claude (`noreply@anthropic.com`) with
`Co-Authored-By: Daniel Tubb`. **Not pushed** — manager merges.

## Issues picked

From milestone **Test Coverage** (#82), the actionable items for this lane are the
two **Python** umbrella issues (the rest — #1988–#1993, #1939 — are Swift/XCUITest
and need the Xcode test gate, which this worktree can only `swiftlint`, not run):

- **#1982 — python/cli (31 untested symbols)** — addressed
- **#1987 — python/workflows (175 untested symbols)** — advanced

Both are broad "N untested symbols" umbrellas; they won't fully close in one pass
(much of the remainder is HTTP route handlers that need TestClient + library
fixtures). I targeted the **untested pure helpers** found via `get_untested_symbols`,
testing edges/validation/regression per Daniel's bar — not happy-path only.

## What was added (57 tests, 4 files)

| Issue | File | Module under test | Coverage |
|-------|------|-------------------|----------|
| #1982 | `test_cli_formatters_helpers.py` (23) | `cli/formatters.py` | `_truncate` (==width not truncated, overflow appends "..." beyond width, width 0); `_align_columns` (pad/join, multi-row, overlong not truncated, zip-to-shortest, non-str); `_first` (skips None/"" but keeps 0/False, None when absent); `_kv`/`_line`/`_human` (empty markers, envelope unwrap, id+label+detail); `_to_jsonable` (recursive model unwrap) |
| #1982 | `test_cli_engine_manager_helpers.py` (8) | `cli/engine_manager.py` | `_is_process_alive` (real current pid True; ProcessLookupError/OSError → False); `_get_uptime` (lsof→ps etime; None on blank/lsof-missing/lsof-nonzero/ps-timeout) |
| #1987 | `test_workflows_builder_helpers.py` (21) | `workflows/builder.py` | `_required_llm_capability_for_category` (media pass-through, case/space-insensitive, else "text"); `_result_worth_caching` (the empty-result cache-poisoning guard — full truth table); `_generate_node_names` (label/tool fallback, unique suffixes, empty) |
| #1987 | `test_scheduler_tz.py` (5) | `workflows/scheduler.py` | `_utcnow` tz-aware UTC; `_ensure_aware_utc` (None passthrough, naive tagged UTC keeping wall clock, already-UTC equivalent, other offset → same UTC instant) |

These were chosen for real consequence: `_result_worth_caching` prevents an
empty transcription poisoning every rerun on the same file; the scheduler tz
helpers prevent schedules firing early/late; `_is_process_alive`/`_get_uptime`
back `status`/`stop`/`restart`.

## Gate results (run from this worktree)

- `ruff check fichero-engine/src/` → **All checks passed!** (no src changed; tests only)
- `pytest` on the 4 new files → **57 passed, 0 failed**
- New files + sibling suites together (`test_cli_formatters`, `test_workflow_executor`)
  → **112 passed, 0 failed** (no cross-test pollution)
- No Swift changes, so no swiftlint run needed this batch.

## Commits (newest first)

```
7edbdb7b test: cover workflows builder + scheduler tz helpers (#1987 Test Coverage)
60103ea6 test: cover cli/engine_manager process helpers (#1982 Test Coverage)
61fc0447 test: cover cli/formatters.py structural helpers (#1982 Test Coverage)
```

## Notes for the manager

- #1982 and #1987 are **advanced, not closed** — they're umbrella counts. Remaining
  untested symbols are mostly route handlers (citations/folders/iiif/integrations/
  export) that need TestClient + a seeded library fixture; a good next batch.
- Swift Test Coverage issues (#1988–#1993, #1939) were intentionally left: this lane
  can only `swiftlint` (style), which cannot verify a Swift test compiles or passes,
  and the brief routes the Xcode build/test gate to the manager. Shipping
  unverifiable Swift tests would be irresponsible — recommend a Swift-capable lane.
- Nothing pushed.
