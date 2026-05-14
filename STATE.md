# STATE.md — Fichero

## Next Session — Start Here

**Latest commit: `976296d3`. Branch: 0.0.2.** Autonomous loop iteration 2 done. **Phase A (backend release-blockers) is complete** — all 4 issues closed. **Phase B started** — the SwiftUI-logic audit is written.

### What to do first

1. **Phase B implementation — start with #1068.** Read `agent-work/proposals/swiftui-logic-audit.md`. The keystone is one canonical backend endpoint `GET /api/documents/{id}/knowledge-graph` (with `include_children` covering #1069). Both the library list view and the KG inspector currently consume *different* endpoints with their own client-side dedup/grouping — that split is the root of #1068. Backend-first, pytest-verifiable; SwiftUI rewiring is a thin Phase C follow-up.
2. **Then #1047 → #1050 → #1030/#1071** per the proposal's sequence.
3. **Verify on a real run** — nothing the loop/prior sessions shipped is confirmed by a real-app run. Restart the dev backend first (Swift test runs cache-pollute it — MEMORY `feedback_runalltests_pollutes_dev_backend`).

### This iteration

- **#1064 FIXED** (`1231444d`) — born-digital PDF text-layer short-circuit hoisted above the skip-if-artifact cache; a stale OCR artifact no longer shields it. Tested, closed.
- **#1021, #1028, #1026** — verified already implemented + tested by prior sessions (the "fixed but not closed" pattern); closed as hygiene, no code change needed.
- **Phase B audit** (`976296d3`) — `agent-work/proposals/swiftui-logic-audit.md`: ~6 SwiftUI files / ~1500 lines of client-side KG logic, mapped to backend endpoints + a sequence.

### State of the 0.0.2 milestone

- ~58 open issues — Phase A cluster fully closed. Still needs ruthless triage: move non-crash/freeze/data-loss issues to 0.0.3.
- **Needs Daniel's input:** #1054 (search threshold value), #1057 (model-defaults UI decision).

### Don't break

- `builder._execute_node` converts any tool's `result["error"]` into a `SystemicErrorDetected` abort, AND gates on garbage output (#1029, `output_quality.assess_result_quality`). Tools surfacing partial success must NOT set `error`.
- `process_vision`: the PDF text-layer short-circuit now runs **before** the skip-if-artifact cache check; the cache check is gated on `not pdf_layer_used` (#1064). Don't reorder them back.
- `extract_all._classify_systemic_error` (#1060); `StructuredDecodeError.kind` + `RETRYABLE_KINDS` (#1027); `DBWriter` fails loud via bounded `_drain()` (#1000).
- KG/entity *logic* belongs in the backend, not SwiftUI — see `feedback_kg_logic_in_backend` memory + `agent-work/proposals/swiftui-logic-audit.md`.
- `StructuredDecodeError` IS an `AppleUnavailableError` subclass by design (#949/#962) — don't revert.
