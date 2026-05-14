# STATE.md — Fichero

## Next Session — Start Here

**Latest commit: `aa2f7402`. Branch: 0.0.2.** Tonight's autonomous loop closed 4 more bugs (#999, #1012, #1014, #1018). Open 0.0.2 count: 16 → 12.

### What to do first

1. **#998 graph crash** — still needs Xcode debugger session to pinpoint the ProgressView with `min == max == 32.142857`. Set a symbolic breakpoint on the AppKit constraint-warning emitter.
2. **#1000 / #1004 / #1008 backend lock-up cluster** — `asyncio.to_thread` sweep across long-running async handlers; one fix template closes all three.
3. **Tooling pass** (from STATE.md history): build the test layers from #1017 in order — SF Symbol static lint (~2h), extractor schema round-trip (~½d), backend integration smoke (~1d).

### Other open 0.0.2 work

- Extraction quality: #1001 / #1003 / #1009 / #1011 / #1016 (likely all caused by the OpenRouter fallback path after Apple Intelligence guardrail trip)
- Backend noise: #1002 (LangChain SSE leak)
- UI: #1007 manual refresh button, #1008 manual housekeeping, #1019 SwiftUI 'modifying state during view update'
- Pre-existing: #928 PDF loupe (blocked on #783), #958 structured artifact editors, #961 console hygiene
- Release chain (out of autonomous scope): #659–#665

### Pre-existing test failure (not blocking)

`fichero-engine/tests/unit/test_chat_structured.py::TestAppleUnavailableHierarchy::test_bridge_stderr_decoding_stays_runtime_error` fails on main — `StructuredDecodeError` is no longer subclass of `AppleUnavailableError`. Either the test or the class hierarchy drifted. Worth filing.

### Don't break

- Tonight's four fixes: 503-JSON-body diagram fallback, Catalogue→Archival Summary tool rename, hidden KG inspector column, richer storage error diagnostics.
- Yesterday's five fixes: empty-SF-Symbol guards, filter-chip presence-filtering, claim-card excerpt-fallback, source-link styling, PDFPageWithToolbar minus its toolbar.
- MEMORY notes: TimelineView snapshot count, HTTP header arbitrary text (now applied to #999), catalogue → KG flow.
