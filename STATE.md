# STATE.md — Fichero

## Next Session — Start Here (tooling-and-testing pivot)

**Latest commit: `71b19062`. Branch: 0.0.2.** Tonight's testing pass filed
**21 bugs (#998–#1019) + comments on #961, #1000, #1011, #1015**. Full ledger in HISTORY.md (entry: 2026-05-13 evening). Daniel's directive for the next session:

> "focus on code quality and testing the workflows. work on tooling and approaches so it can run autonomously overnight. you're building too often + swiftlinting too much, and you're not catching things — workflows aren't completing properly and the build/test cycle is too slow to know."

### Priority 1 — Tooling pass (do this BEFORE any bug fixes)

The bug-fix loop is currently slow and noisy:
- Every Swift change runs `xcodebuild` end-to-end (~30+ s).
- Swiftlint runs on every commit but doesn't catch the *real* bugs (constraint loops, silent failures, schema drift).
- Backend changes don't have an integration smoke that would catch loop-blocking regressions.
- Workflows complete with success status but produce missing/wrong outputs (#1003, #1006, #1011, #1016) — and we don't know until a human notices in the UI.

Build the missing test layers from #1017 in this order:

1. **SF Symbol static lint** (~2 hours) — closes #1015, prevents recurrence. Regex over `Image(systemName: "x")` against the SF Symbols catalog. Run as a pre-commit + CI step.
2. **Extractor schema round-trip** (~half day) — closes #1006, #1016, partial #1003. Post-write assertion at `_write_kg_rows`: every claim has populated SVO OR explicit None; every entity description ≥3 words OR None; per-page log of `(page_label, entities_written, claims_written)`. Loud failure on silent miss.
3. **Backend integration smoke** (~1 day) — closes #1000, #1004, #1002, #1011. pytest-asyncio: start uvicorn, run a small workflow on a fixture file, hammer `/api/health` during the run (assert <100ms), parse SSE stream (assert no `Runnable*` events leak), assert promised artifacts exist in DB after completion.
4. **Build acceleration** (~half day) — investigate incremental xcodebuild + a minimal `swift build` shortcut for non-UI changes. Cuts the iteration loop.
5. View snapshots + golden-set extraction quality come later (1-2 days each).

### Priority 2 — Highest-leverage single bug fix

**#998 graph constraint loop** — one-file change, unblocks Graph view entirely. Find the `ProgressView` whose width comes from float division (`32.142857 ≈ 225/7`) and round to int. Likely in the OntologyBrowser entity-kind chip strip.

### Priority 3 — Backend lock-up cluster

**#1000 / #1004 / #1008** — sweep `asyncio.to_thread` across long-running async handlers. Same fix template; closes 3 bugs at once. Verify with the new integration smoke (Priority 1.3).

### Don't break

- The rebuilt one-file library lives at `~/Library/Application Support/com.fichero.fichero/global.fichero/`.
- `.claude/worktrees/` is in `.gitignore`.
- `feedback_timelineview_snapshot_count`, `feedback_http_header_arbitrary_text`, `project_catalogue_writes_kg` MEMORY notes from earlier today inform the bug fixes.

### Open backlog beyond tonight's filings

12 pre-existing 0.0.2 issues remain (#928 PDF loupe, #958 structured artifact editors, #961 console hygiene now expanded with tonight's evidence, plus the release chain #659–#665).
