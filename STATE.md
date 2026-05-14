# STATE.md — Fichero

## Next Session — Start Here

**Latest commit: `55fe58f5`. Branch: 0.0.2.** This session: autonomous backend session — shipped #1017 layer 2 (extraction invariants) and #988 step 1 (graph-context merge-candidate generator). Both committed + pushed to 0.0.2 with progress comments on the umbrella issues.

### What to do first

1. **#1000 backend lock-up** — investigated this session, NOT fixed. Root cause is architectural, not a one-call swap: `_run_workflow_in_background` runs as `asyncio.create_task` on the main loop (core.py:218), so any sync-blocking tool node inside `app.astream_events` freezes `/api/health`. Activity tracking is already non-blocking (`activity_store` uses `to_thread`). Needs a live repro to find which tool blocks — not viable headless. Either offload blocking tool bodies (#1004 pattern, large surface) or run the whole execution off-loop.
2. **#1008** — KG Tools menu auto-run; backend trigger + Swift menu changes. Needs Xcode.
3. **#961 / #998 / #1019 / #958** — all SwiftUI/AppKit, need full Xcode build + 3-leg Swift check.

### Other open 0.0.2 work

- #1017 test-coverage gap — layer 2 (extractor invariant validation) DONE. Layers 1 (backend integration smoke), 3 (SF Symbol lint), 4 (SwiftUI snapshot), 5 (golden-set extraction) still open.
- #988 entity resolution — step 1 (graph-context candidate generator) DONE. Remaining: wire into `/api/kg/review`, probabilistic field scoring, auto-merge tiers, after-extraction hook.
- #1001 — loud-log done; **opt-in UI toggle still open, needs Daniel's product decision** (default behaviour: block vs. warn?).
- #1019 SwiftUI 'modifying state during view update' — needs Main Thread Checker; Daniel to reproduce.
- #958 structured artifact editors, #928 PDF loupe (blocked on #783).
- Release chain (out of autonomous scope): #659–#665.

### Don't break

- This session's additions: `extraction_invariants.py` (pure boundary checks, wired into `_write_kg_rows` WARNING log) for #1017; `graph_context_merge_candidates` + `MergeCandidate` in `kg/graph.py` for #988.
- `StructuredDecodeError` IS an `AppleUnavailableError` subclass by design (#949/#962) — don't revert.
- KG consolidation: new KG modules must call `_common.slug_verb` rather than re-implementing the slugifier. Public API preserved: `_predicate_uri`, `build_full_graph`, `build_full_cooccurrence`, `invalidate_graph_cache`, `_predicate_slug`.
