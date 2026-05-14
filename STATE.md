# STATE.md — Fichero

## Next Session — Start Here

**Latest commit: `5817e859`. Branch: 0.0.2.** This session: autonomous session — shipped #1017 layer 3 (SF Symbol static lint) and closed #1019 (stopped @State mutation inside the graph Canvas render closure). Both committed + pushed to 0.0.2; full 3-leg Swift check green (build + 683 tests).

### What to do first

1. **#1000 backend lock-up** — still architectural, NOT fixed. `_run_workflow_in_background` runs as `asyncio.create_task` on the main loop, so any sync-blocking tool node inside `app.astream_events` freezes `/api/health`. Needs a live repro to find the blocking tool — not viable headless. Either offload blocking tool bodies (#1004 pattern, large surface) or run the whole execution off-loop.
2. **#1008** — KG Tools menu auto-run; backend trigger + Swift menu changes. Needs Xcode.
3. **#961 / #998 / #958** — all SwiftUI/AppKit, need full Xcode build + 3-leg Swift check. #998 may be relieved by the #1019 fix (same view-switch path) — re-test first.

### Other open 0.0.2 work

- #1017 test-coverage gap — layers 2 + 3 DONE. Layers 1 (backend integration smoke), 4 (SwiftUI snapshot), 5 (golden-set extraction) still open.
- #988 entity resolution — step 1 (graph-context candidate generator) DONE. Remaining: wire into `/api/kg/review`, probabilistic field scoring, auto-merge tiers, after-extraction hook.
- #1001 — loud-log done (both `chat_with_fallback` + `chat_structured_with_fallback`); **opt-in UI toggle still open, needs Daniel's product decision** (default behaviour: block vs. warn?).
- #958 structured artifact editors, #928 PDF loupe (blocked on #783).
- Release chain (out of autonomous scope): #659–#665.

### Don't break

- This session's additions: `fichero-engine/tests/unit/test_sf_symbol_names.py` (scans Swift source, validates SF Symbol literals against CoreGlyphs.bundle; skips when catalog absent) for #1017 layer 3; `GraphSimulation` plain class in `OntologyBrowser.swift` holding force-directed sim state — Canvas mutates it freely, `graphRevision` @State flips the empty-state branch. Don't move sim state back to `@State`.
- `extraction_invariants.py` (pure boundary checks, wired into `_write_kg_rows` WARNING log) for #1017; `graph_context_merge_candidates` + `MergeCandidate` in `kg/graph.py` for #988.
- `StructuredDecodeError` IS an `AppleUnavailableError` subclass by design (#949/#962) — don't revert.
- KG consolidation: new KG modules must call `_common.slug_verb` rather than re-implementing the slugifier. Public API preserved: `_predicate_uri`, `build_full_graph`, `build_full_cooccurrence`, `invalidate_graph_cache`, `_predicate_slug`.
