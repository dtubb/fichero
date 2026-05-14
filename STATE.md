# STATE.md — Fichero

## Next Session — Start Here

**Latest commit: `9867eb28`. Branch: 0.0.2.** Tonight's autonomous loop closed 5 UI bugs (#1005, #1006, #1010, #1013, #1015). Total open 0.0.2 bug count down from 21 to 16.

### What to do first

1. **Tooling pass** (still the highest-leverage work): build the test layers from #1017 in this order — SF Symbol static lint (~2h), extractor schema round-trip (~½d), backend integration smoke (~1d). Specifics in #1017's body.
2. **#998 graph crash** — needs Xcode debugger session to pinpoint the ProgressView with `min == max == 32.142857`. Set a symbolic breakpoint on the AppKit constraint-warning emitter; the float source is one Xcode session away.
3. **#1000 / #1004 / #1008 backend lock-up cluster** — `asyncio.to_thread` sweep across long-running async handlers; one fix template closes all three.

### Other open 0.0.2 work

- Extraction quality: #1001 / #1003 / #1009 / #1011 / #1016 (likely all caused by the OpenRouter fallback path after Apple Intelligence guardrail trip)
- Backend noise: #999 (mermaid header), #1002 (LangChain SSE leak), #1018 (thumbnail invalid response)
- UI: #1007 manual refresh button, #1008 manual housekeeping, #1012 catalogue naming collision, #1014 empty inspector pane, #1019 SwiftUI 'modifying state during view update'
- Pre-existing: #928 PDF loupe (blocked on #783), #958 structured artifact editors, #961 console hygiene
- Release chain (out of autonomous scope): #659–#665

### Don't break

- The 5 fixes shipped tonight: empty-SF-Symbol guards, filter-chip presence-filtering, claim-card excerpt-fallback, source-link styling, PDFPageWithToolbar minus its toolbar.
- MEMORY notes from yesterday: TimelineView snapshot count, HTTP header arbitrary text, catalogue → KG flow.
