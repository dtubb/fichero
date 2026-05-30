# Planner dispatch — 2026-05-30

**You are the planner.** No code edits. Worktree: `~/code/fichero-0.0.2`. Use jcodemunch-mcp for code navigation ([[reference_jcodemunch_mcp_single_source]]).

## Standby until integrator's Phase 0 lands

When `agent-work/dispatch/2026-05-30-integrator-DONE.md` appears and reviewer signs off, your Phase 2 sequencing pickup begins.

## Activation pickup

You've already produced `agent-work/proposals/2026-05-30-mindpalace-phased-plan.md` for P1–P4. After Opus's merge lands, **two pieces will already be in trunk** (cross-platform color helper, LinkType + visible edges). Update the plan to reflect what's left:

1. **Plan the Phase 2 work execution order**, accounting for the hot file `SpatialScene3D.swift` and the OpenAPI serialization rule. Concretely:
   - Order: (a) backend `GET /api/mind_palace/library_snapshot` → (b) Swift wire-in to `MindPalaceService`/`MindPalaceState` → (c) incremental scene diffing → (d) hover/edge labels. (a) is OpenAPI-changing; must finish before unmerged OpenAPI batches from f_gpt (#1101 bibtex).
   - Estimate which lane (Codex/Sonnet/Haiku) is right for each, per [[reference_lane_model_assignment]].

2. **Plan the release-data import cluster** (#1231–#1239 — Daniel's Phase 1 additions). Group:
   - `xlsx-shaped` (#1237) — needs `/api/ingest/xlsx` Swift wrapper (integrator's coverage doc flagged this).
   - `link-mode importers` (#1232 Chota Valley maps, #1234 Archivo Judicial, #1238 Istmina) — same pattern as Box/Dropbox (#1329/#1330). Propose a shared "linked-folder importer" backend abstraction.
   - `materials-with-existing-catalog` (#1233 GHC/ACENET, #1235 Mosquera, #1236 Marshall) — needs a "pre-catalogued ingest" workflow that doesn't re-run extractors.
   - `infra-blocker` (#1239 remote ACENET SSH) — depends on remote-backend reachability (see [[feedback_independently_verify_lane_test_claims]] for backend-discovery rules).

3. **Plan #1229 + #1230 sequencing** (toolbar polish + XCUITest target). #1230 has a TCC blocker ([[feedback_xcuitest_tcc_automation_grant]]) — Daniel needs to grant Xcode Accessibility+Automation once. Flag this as a manual prerequisite.

4. **Output:** `agent-work/proposals/2026-05-30-phase2-execution-plan.md` with: dispatch order, per-task lane assignment, OpenAPI-serialization constraints, and which work is parallelizable. Reference [[feedback_lane_orchestration_lessons]] for the hot-file/serial-is-better-than-parallel discipline.

5. **Notify:** `agent-work/dispatch/2026-05-30-planner-DONE.md` with one-line summary. Manager dispatches workers.

## Hard rules

- No code edits.
- KG/aggregation logic stays backend-side ([[feedback_kg_logic_in_backend]]).
- Tool prompts + model choices are user-editable, not hardcoded ([[feedback_user_editable_not_hardcoded]]).
