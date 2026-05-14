# STATE.md — Fichero

## Next Session — Start Here

**Latest commit: `60f58ee1`. Branch: 0.0.2.** Autonomous loop just closed 4 more bugs (#1016, #1007, #1002, #1011). Open 0.0.2 count: 12 → 8.

### What to do first

1. **#998 graph crash** — still needs Xcode debugger session to pinpoint the ProgressView with `min == max == 32.142857`. Set a symbolic breakpoint on the AppKit constraint-warning emitter.
2. **#1000 / #1004 / #1008 backend lock-up cluster** — `asyncio.to_thread` sweep across long-running async handlers; one fix template closes all three. **#1008 is blocked on #1004** (this session deferred it for that reason).
3. **Tooling pass** (from STATE.md history): build the test layers from #1017 in order — SF Symbol static lint (~2h), extractor schema round-trip (~½d), backend integration smoke (~1d).

### Other open 0.0.2 work

- Extraction quality: #1001 / #1003 / #1009 (Apple Intelligence guardrail + OpenRouter fallback degrades typing & coverage; #1011 partially mitigated tonight by surfacing silent failures, but the underlying LLM-call quality is unchanged.)
- UI: #1019 SwiftUI 'modifying state during view update' (needs Main Thread Checker runtime diagnostics — Daniel to reproduce.)
- Pre-existing: #928 PDF loupe (blocked on #783), #958 structured artifact editors, #961 console hygiene
- Meta: #1017 test-coverage gap
- Release chain (out of autonomous scope): #659–#665

### Pre-existing test failures (not blocking)

- `fichero-engine/tests/unit/test_chat_structured.py::TestAppleUnavailableHierarchy::test_bridge_stderr_decoding_stays_runtime_error` — `StructuredDecodeError` is no longer subclass of `AppleUnavailableError`. Either the test or the class hierarchy drifted.
- `fichero-engine/tests/unit/test_routes_settings.py::TestResetAIDefaults::test_reset_clears_all_settings` — assertion failure on settings reset (pre-existing).

Both confirmed unrelated to this session via stash test.

### Don't break

- Tonight's four fixes: degenerate entity description sanitiser, KG auto-refresh, LangChain SSE filter, catalogue silent-failure surfacing.
- Recent fixes: 503-JSON-body diagram fallback, Catalogue→Archival Summary tool rename, hidden KG inspector column, richer storage error diagnostics.
- MEMORY notes: TimelineView snapshot count, HTTP header arbitrary text, catalogue → KG flow, "Pydantic field must be declared" (relevant to extractor work).
