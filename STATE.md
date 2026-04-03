# STATE.md — Fichero

Last updated: 2026-04-03

## Current Branch

`codex/0.0.2-planning` — 0.0.2 semantic layer planning and early implementation

## Source of Truth

- GitHub Issues + Milestones: https://github.com/dtubb/fichero/milestones
- Project board: https://github.com/users/dtubb/projects/5
- Canonical roadmap: `docs/0.0.2-planning/AUTHORITATIVE_ROADMAP_SPEC.md`

## Completed This Session (2026-04-02 autonomous loop)

- #381: Created `docs/agent-workflow/0.0.2-gate-map.md` — gate map for all semantic features across Layers 0-6
- #365: Added `SourceMetadata` model with full citation validation (DOI, ISBN-13, ISBN-10, ISSN, arXiv), `ProvenanceInfo`, `KnowledgeClaim.source_metadata` field, 36 unit tests
- #366: Added `GET /entities/alias-map` endpoint + `GET /claims?entity=X` free-text filter, 2 unit tests
- SwiftLint: fixed 6 identifier_name errors (posX/posY/gridX/gridY in OntologyBrowser + EpistemologyGraphView)
- rules.json: committed agent rules configuration
- #367 partial: added `curated_only=true` convenience filter to GET /claims and /claims/filtered
- #392: Added 4 MCP tools — `fichero_kg_generate_heuristic_predictions`, `fichero_kg_apply_predictions`, `fichero_hm_create_circle_state`, `fichero_hm_navigate_circle`
- OpenAPI sync: 46 endpoints across 16 resources — regenerated Swift client
- SwiftLint: auto-fixed 88 sorted_imports violations (88→0 serious)

## Completed This Session (2026-04-03 autonomous loop — session-start-auto-solo)

- **#367**: Reversible entity merge/split + claim curation transitions
  - `POST /entities/merge`: absorbs entities into survivor with alias preservation
  - `POST /entities/split`: distributes aliases across primary + split-off entities
  - `POST /entities/audit/{id}/undo`: reverses any merge/split via audit chain
  - `GET /entities/audit`: lists audit records filtered by entity_id
  - `EntityMergeAudit` model: immutable operation log with reversal linkage
  - `KnowledgeEntity.merged_into_id` used for soft-delete redirect
  - `PATCH /claims/{id}` covers curation_state transitions (already existed)

- **#362**: General mutation log with undo/rollback for KG entities
  - `MutationLog` model: before/after state snapshots with `run_id` for AI batch grouping
  - `POST /knowledge-mutations/undo`: undo single mutation or rollback full AI run
  - `GET /knowledge-mutations`: list with filters (entity_type, entity_id, run_id, created_by)
  - `POST|PATCH /claims` now log mutations automatically with run_id/agent_id query params
  - `_log_mutation` helper for wiring mutations into any KG entity

**All 900 pytest pass. ruff clean. SwiftLint clean.**

## Completed This Session (2026-04-03 second autonomous loop)

- **#363**: Library snapshots and restore
  - `LibrarySnapshot` model with paths, sizes, retention policy
  - `snapshot_library()`: exports DuckDB tables to Parquet + copies LanceDB vectors
  - `POST /api/storage/snapshots`, `GET /api/storage/snapshots`, `GET /api/storage/snapshots/{id}`
  - `POST /api/storage/snapshots/{id}/restore`, `DELETE /api/storage/snapshots/{id}`, `PATCH /api/storage/snapshots/{id}/pin`
  - Pinned snapshots exempt from auto-retention; auto-expire via `auto_expire_days`

- **#361**: XMP sidecar support for images
  - `xmp_loader.py`: parse XMP sidecars with libxmp + regex fallback
  - Standard namespaces: dc, xmp, photoshop, Iptc4xmpCore, Iptc4xmpExt
  - Custom `ficher:` namespace for entity links, claim links, archive IDs, IIIF manifests
  - `apply_xmp_to_document()` merges into `Document.metadata`
  - Wired into `ingest.py` `_extract_image_metadata()` — runs during normal image ingestion

**900 pytest pass. ruff clean. SwiftLint clean.**

## Active Work

**Phase 1: Knowledge Graph Core + PyKEEN (#387)**
- Backend complete: models, migration, routes, embeddings, MCP tools, unit tests
- SwiftUI views: all done (ClaimInspector, OntologyBrowser, EpistemologyGraph, PredictionReview)
- Deferred: PyKEEN wiring (needs `pykeen` dependency)

**Phase dependencies:** Phase 2-5 all depend on Phase 1 backend being solid.

## Blocked

- 0.0.1 regression gate issues (#382-#386) require manual QA testing — not actionable autonomously
- Remaining Phase 1 work (PyKEEN) needs `pykeen` dependency added to project

## Open Issues by Phase

| Phase | Issue | Status | Notes |
|-------|-------|--------|-------|
| Phase 1 | #387 | In Progress | Backend + SwiftUI done; PyKEEN deferred |
| Phase 2 | #388 | Not Started | Depends on #387 |
| Phase 3 | #389 | Not Started | Depends on #387, #388 |
| Phase 4 | #390 | Not Started | Depends on #387, #388, #389 |
| Phase 5 | #391 | Not Started | Depends on #387-390 |

## Next Session — Start Here

1. **PyKEEN wiring** (#387): add `pykeen` to dependencies, wire `POST /predictions/generate/pykeen`, implement training pipeline
2. **After Phase 1 PyKEEN done**: move to Phase 2 (#388, Hermeneutics)
3. **0.0.1 regression gate**: manual QA checklist in `docs/qa/0.0.1-manual-qa-checklist.md`
