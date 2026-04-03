
## 2026-04-03 — Autonomous Loop Session

- #367: Reversible entity merge/split + claim curation transitions
  - `POST /entities/merge`: absorbs entities into survivor with alias preservation
  - `POST /entities/split`: distributes aliases across primary + split-off entities
  - `POST /entities/audit/{id}/undo`: reverses any merge/split via audit chain
  - `GET /entities/audit`: lists audit records filtered by entity_id
  - `EntityMergeAudit` model: immutable operation log with reversal linkage
  - `KnowledgeEntity.merged_into_id` used for soft-delete redirect
  - `PATCH /claims/{id}` covers curation_state transitions (already existed)

- #362: General mutation log with undo/rollback for KG entities
  - `MutationLog` model: before/after state snapshots with `run_id` for AI batch grouping
  - `POST /knowledge-mutations/undo`: undo single mutation or rollback full AI run
  - `GET /knowledge-mutations`: list with filters (entity_type, entity_id, run_id, created_by)
  - `POST|PATCH /claims` now log mutations automatically with run_id/agent_id query params
  - `_log_mutation` helper for wiring mutations into any KG entity

- #395: Fixed 8 SwiftLint violations across 4 SwiftUI view files:
  - Extracted 13 component files from 4 long views
  - Result: 0 violations across 341 Swift files

**All 900 pytest pass. ruff clean. SwiftLint clean.**

## 2026-04-02 — Autonomous Loop Session

- #381: Created `docs/agent-workflow/0.0.2-gate-map.md` — gate map for Layers 0-6
- #365: SourceMetadata model + citation validation (DOI, ISBN-13/10, ISSN, arXiv) + ProvenanceInfo + 36 unit tests
- #366: GET /entities/alias-map + GET /claims?entity=X filter + 2 unit tests
- #392: Added 4 MCP tools — `fichero_kg_generate_heuristic_predictions`, `fichero_kg_apply_predictions`, `fichero_hm_create_circle_state`, `fichero_hm_navigate_circle`
- OpenAPI sync: 46 endpoints across 16 resources — regenerated Swift client
- SwiftLint: auto-fixed 88 sorted_imports violations across all SwiftUI files (101 files, +275/-275 lines)
- SwiftLint: fixed 6 identifier_name violations (posX/posY/gridX/gridY in OntologyBrowser + EpistemologyGraphView)
- rules.json: agent rules configuration committed
- #367 partial: curated_only=true filter added to GET /claims and /claims/filtered
- Phase 1 SwiftUI: ClaimInspectorView, OntologyBrowserView, EpistemologyGraphView, PredictionReviewView

## 2026-04-02 — Session Sync

- Aligned GitHub issues (#387-391, #362-381) with AUTHORITATIVE_ROADMAP_SPEC.md
- Fixed labels on all 5 Phase issues (removed conflicting status:done on #390)
- Confirmed TASKS.md deprecated — GitHub is sole source of truth

## 2026-04-02 — Phase 1 SwiftUI Views

- Branch: codex/0.0.2-planning
- Added OntologyBrowser, EpistemologyGraph, PredictionReview views for Phase 1

## 2026-03-29 — Session Summary

- Realigned planning split: 0.0.1 execution stays in ~/code/fichero and 0.0.2 planning stays in ~/code/fichero-0.0.2.
- Completed peer-review framing for 0.0.2 semantic layer and captured the componentized plan in the 0.0.2 worktree (A-G slices, undo/snapshot baseline, and 0.0.3/0.1.0 deferral split).
- Updated STATE.md and MEMORY.md in main worktree to preserve the two-worktree operating model and clear next-session entry points for 0.0.1.

## 2026-04-03 — #367 Reversible entity merge/split and claim curation state v1

- Branch: codex/0.0.2-planning
- Entity merge/split/undo + curation transitions done

## 2026-04-03 — #362 Undo and rollback for human + AI changes

- Branch: codex/0.0.2-planning
- MutationLog + undo/rollback + AI run grouping done
