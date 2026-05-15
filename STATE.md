# STATE.md — Fichero

## Next Session — Start Here

**Branch: 0.0.2.** Autonomous loop iteration 5 done. **Phase B audits + backend cleanup complete.** #1072 whole-app audit shipped (`agent-work/proposals/swiftui-logic-audit-whole-app.md`); #1030 backend repair migration shipped.

### What to do first

1. **Phase C — wire SwiftUI to the new endpoints** (needs Xcode MCP):
   - `GET /api/documents/{id}/knowledge-graph` — retire `KnowledgeGraphInspectorSection`'s client-side dedup/grouping + O(n) `getEntity` fan-out; use `include_children=true` for parent PDFs; render the new `catalogue` field as a header block (#1047); restore Dates section to `EntityKind.displayOrder`.
   - `GET /api/entities/{id}/inspector` — `EntityDetailView` header renders the new `summary` field (#1050).
   - **#1030 frontend half** — `ClaimSummaryCardView` / `EntityDetailView` should compose `{verb} {object}` from claim metadata rather than render raw `claim.text` / `entity.description` when those fields look like a repr. Add a defensive guard.
   - Pure-UI polish: #1062, #1063, #1066, #1034, #1058, #1049.
2. **Phase B extension — implement the three whole-app clusters from `swiftui-logic-audit-whole-app.md`**:
   - **Cluster 1 (HIGH)** — typed artifacts response (typed `items`, `is_canonical`/`superseded_by`, `display_name`, `user_visible`) — retires 4 duplicated client parsers.
   - **Cluster 2 (HIGH)** — `GET /workflow-execution/threads/{threadId}/state` (one composed run aggregate) — collapses the SwiftUI SSE reducer, every Activity rollup, and four divergent "what's internal" filters.
   - **Cluster 3** — `tier_eligibility` + cost-sort + `recommended` as server fields on the model-listing endpoint; resolved AI defaults; de-duplicated `/api/providers` — ties #1057/#1059.
3. **Run the SVO-repr repair on a real library** (dry-run first):
   `PYTHONPATH=fichero-engine/src python fichero-engine/scripts/run_migration.py repair_kg_svo_repr_leak --dry-run --library-path ~/fichero-library`
4. **Verify on a real run** — Restart the dev backend first (Swift test runs cache-pollute it — MEMORY `feedback_runalltests_pollutes_dev_backend`).

### This iteration (loop iteration 5)

- **#1072 SHIPPED** — Whole-app SwiftUI-logic audit in `agent-work/proposals/swiftui-logic-audit-whole-app.md`. Three parallel sweeps of Views/Models/Services found the same anti-pattern as the KG audit in three more clusters (artifacts, workflow runs, model/provider capability). Citations independently verified by code-reviewer subagent. Issue stays open as the umbrella for the implementation moves.
- **#1030 backend SHIPPED** — `MigrationRunner.repair_kg_svo_repr_leak` scrubs existing KG rows with leaked kwarg-repr in `text`/SVO fields/`source_excerpt`/`description`. Idempotent, dry-run, audit-logged. Detector consolidated into `kg/_common.parse_kwarg_repr` so forward guard + repair share one detector. Per-row try/except keeps a single bad row from aborting the run. +10 pytest cases. Registered in CLI script + API route. Issue stays open for the SwiftUI render-time guard half.
- Pre-existing failure noted (still): `test_routes_settings.py::TestResetAIDefaults::test_reset_clears_all_settings` (legacy `fichero-api/` path) — unrelated.

### State of the 0.0.2 milestone

- 55 open issues. Phase A + Phase B backend cluster fully closed; whole-app audit + #1030 backend now done. Still needs ruthless triage: most issues should move to 0.0.3.
- **Needs Daniel's input:** #1054 (search threshold value), #1057 (model-defaults UI decision).

### Don't break

- `kg/_common.parse_kwarg_repr` is the canonical detector — both `extractors._normalize_kwarg_repr_fields` (forward guard) and `MigrationRunner._repair_claim_svo_repr` / `_repair_entity_svo_repr` (#1030 backfill) consume it. Drift between them is exactly what #1030 was about.
- `MigrationRunner.repair_kg_svo_repr_leak` recomposes `claim.text` mirroring `extractors._write_kg_rows` — entity-bearing: `"{subject} {verb} {obj}."`, date-style: `"{stem}: {verb} {obj}."`. If the forward composition ever changes (e.g. strips trailing punctuation from `obj`), the repair must change too or they'll diverge.
- The "no recoverable SVO" guard exists on BOTH the claim and entity helpers — a polluted row whose repr parsed to empty verb+object is left for manual review, NOT blanked. Don't remove the guards.
- `builder._execute_node` converts any tool's `result["error"]` into a `SystemicErrorDetected` abort, AND gates on garbage output (#1029).
- `process_vision`: the PDF text-layer short-circuit runs **before** the skip-if-artifact cache check (#1064). Don't reorder.
- KG/entity *logic* belongs in the backend, not SwiftUI — `feedback_kg_logic_in_backend` + the two audit docs in `agent-work/proposals/`.
- `document_inspector._build_knowledge_graph` *follows* `merged_into_id` to the canonical entity (does NOT skip merged entities — that was a #1068 under-count cause).
- `StructuredDecodeError` IS an `AppleUnavailableError` subclass by design (#949/#962).
- `entity_inspector._compose_entity_summary` builds `summary` as a deterministic entity-level line — must NEVER echo a claim's text/predicate (the #1050 bug).
