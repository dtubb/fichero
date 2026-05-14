# STATE.md — Fichero

## Next Session — Start Here

**Latest commit: `1d6e8118`. Branch: 0.0.2.** This session: autonomous backend bug sweep — closed #1004, #1003, #1009; partially addressed #1001 (loud-log half done, opt-in UI toggle left open).

### What to do first

1. **#1008 is now unblocked** — it was blocked on #1004 (`asyncio.to_thread` pattern), which shipped this session. Apply the same off-load template to the KG Tools menu auto-run work.
2. **#1000 backend lock-up** — same `asyncio.to_thread` template; one fix shape. Lowest-numbered open backend bug.
3. **#961 console hygiene** — deferred this session (SwiftUI/AppKit domain, needs full Xcode build + 3-leg Swift check, three separate diagnostic passes). Lower priority than functional bugs per the issue.
4. **#998 graph crash** — needs Xcode debugger session; symbolic breakpoint on the AppKit constraint-warning emitter.

### Other open 0.0.2 work

- #1001 — loud-log done; **opt-in UI toggle still open, needs Daniel's product decision** (default behaviour: block vs. warn?).
- #1019 SwiftUI 'modifying state during view update' — needs Main Thread Checker; Daniel to reproduce.
- #958 structured artifact editors, #1017 test-coverage gap, #928 PDF loupe (blocked on #783).
- Release chain (out of autonomous scope): #659–#665.

### Don't break

- This session's four fixes: `asyncio.to_thread` off-load on both embed endpoints (#1004); zero-entity-page observability logs in `_write_kg_rows` (#1003); WARNING-level paid-fallback notices in `llm.py` (#1001); sharpened `_SECTIONS` instruction strings (#1009).
- `StructuredDecodeError` IS an `AppleUnavailableError` subclass by design (#949/#962) — three tests were refreshed this session to match the current contract; don't revert them.
- KG consolidation: new KG modules must call `_common.slug_verb` rather than re-implementing the slugifier. Public API preserved: `_predicate_uri`, `build_full_graph`, `build_full_cooccurrence`, `invalidate_graph_cache`, `_predicate_slug`.
