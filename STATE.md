# STATE.md — Fichero

## Next Session — Start Here

**Branch: 0.0.2.** Autonomous loop iteration 3 done. **Phase A complete.** **Phase B in progress** — the canonical KG endpoint is built (#1068, #1069 shipped).

### What to do first

1. **Phase B — continue with #1047 → #1050 → #1030/#1071** per `agent-work/proposals/swiftui-logic-audit.md`. #1047: fold the folder catalogue narrative into the knowledge-graph endpoint when the target is a folder. #1050: extend `GET /api/entities/{id}` with a server-composed summary.
2. **Phase C (after Phase B queue empties)** — wire SwiftUI to consume `GET /api/documents/{id}/knowledge-graph` (use `include_children=true` for parent PDFs), retire `KnowledgeGraphInspectorSection`'s client-side dedup/grouping + the O(n) `getEntity` fan-out, restore the Dates section to `EntityKind.displayOrder`.
3. **Verify on a real run** — nothing the loop shipped is confirmed by a real-app run. Restart the dev backend first (Swift test runs cache-pollute it — MEMORY `feedback_runalltests_pollutes_dev_backend`).

### This iteration

- **#1068 SHIPPED** — `GET /api/documents/{id}/knowledge-graph` in `api/routes/document_inspector.py`: the canonical KG grouping. Resolves entities, follows merge chains to the canonical (absorbed entities' claims kept, not dropped), groups by kind incl. a synthetic Dates group, dedups within kind. 9 pytest cases.
- **#1069 SHIPPED** — `include_children` param on the same endpoint: BFS over the doc tree aggregating page-child claims onto the parent PDF (extract_all writes claims to page docs, never the parent). +2 pytest cases (11 total in `test_inspector_aggregates.py`).

### State of the 0.0.2 milestone

- ~58 open issues — Phase A cluster fully closed. Still needs ruthless triage: move non-crash/freeze/data-loss issues to 0.0.3.
- **Needs Daniel's input:** #1054 (search threshold value), #1057 (model-defaults UI decision).

### Don't break

- `builder._execute_node` converts any tool's `result["error"]` into a `SystemicErrorDetected` abort, AND gates on garbage output (#1029, `output_quality.assess_result_quality`). Tools surfacing partial success must NOT set `error`.
- `process_vision`: the PDF text-layer short-circuit now runs **before** the skip-if-artifact cache check; the cache check is gated on `not pdf_layer_used` (#1064). Don't reorder them back.
- `extract_all._classify_systemic_error` (#1060); `StructuredDecodeError.kind` + `RETRYABLE_KINDS` (#1027); `DBWriter` fails loud via bounded `_drain()` (#1000).
- KG/entity *logic* belongs in the backend, not SwiftUI — see `feedback_kg_logic_in_backend` memory + `agent-work/proposals/swiftui-logic-audit.md`.
- `document_inspector._build_knowledge_graph` *follows* `merged_into_id` to the canonical entity — it does NOT skip merged entities the way the old SwiftUI code did (skipping silently drops absorbed entities' claims; that was a #1068 under-count cause). Don't revert to skipping.
- `StructuredDecodeError` IS an `AppleUnavailableError` subclass by design (#949/#962) — don't revert.
