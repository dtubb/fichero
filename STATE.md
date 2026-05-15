# STATE.md — Fichero

## Next Session — Start Here

**Branch: 0.0.2.** Autonomous loop iteration 4 done. **Phase A complete.** **Phase B endpoint queue empty** — #1068/#1069/#1047/#1050 all shipped.

### What to do first

1. **Phase B tail — #1030 / #1071 / charts** per `agent-work/proposals/swiftui-logic-audit.md` (lower priority): claims responses carry resolved SVO + `content_quality`; `GET /api/entities` scoping params (`kinds`, `scope`, `count_by_kind`). If that empties, extend toward #1072 (whole-app SwiftUI-logic audit).
2. **Phase C** — wire SwiftUI to consume the Phase B endpoints (needs Xcode MCP):
   - `GET /api/documents/{id}/knowledge-graph` — retire `KnowledgeGraphInspectorSection`'s client-side dedup/grouping + O(n) `getEntity` fan-out; use `include_children=true` for parent PDFs; render the new `catalogue` field as a header block above the entity sections (#1047); restore Dates section to `EntityKind.displayOrder`.
   - `GET /api/entities/{id}/inspector` — `EntityDetailView` header should render the new `summary` field instead of `entity.description` (#1050).
   - Pure-UI polish: #1062, #1063, #1066, #1034, #1058, #1049.
3. **Verify on a real run** — nothing the loop shipped is confirmed by a real-app run. Restart the dev backend first (Swift test runs cache-pollute it — MEMORY `feedback_runalltests_pollutes_dev_backend`).

### This iteration (loop iteration 4)

- **#1047 SHIPPED** — `GET /api/documents/{id}/knowledge-graph` now returns a `catalogue` field: the document's catalogue artifacts (`catalogue.narrative` / `.timeline` / `.keywords` + legacy `catalogue`), narrative-first. Empty for leaf docs. Helpers `_catalogue_artifacts` / `_is_catalogue_artifact` in `document_inspector.py`. +3 pytest cases.
- **#1050 SHIPPED** — `EntityInspectorResponse` now carries a server-composed `summary` field — deterministic entity-level line (`type · claim count [across N documents] · aliases`), never a claim echo. `entity.description` left intact (still feeds similarity). `_compose_entity_summary` in `entity_inspector.py`. +3 pytest cases.
- Pre-existing failure noted: `test_routes_settings.py::TestResetAIDefaults::test_reset_clears_all_settings` fails on clean HEAD (legacy `fichero-api/` path) — unrelated to this work, not introduced here.

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
- `entity_inspector._compose_entity_summary` builds the `summary` field as a deterministic entity-level line — it must NEVER echo a claim's text/predicate (that was the #1050 bug). `entity.description` stays as-is because `entity_vectors.find_similar` still consumes it; don't empty it out.
