
## 2026-04-07 — Autonomous Loop Session

- **#387 Phase 1 assessment**: Assessed 0.0.2 phase implementation status across all 5 phases
  - Phase 1 (#387): Backend done, PyKEEN route needs wiring + pip install
  - Phase 2 (#388): Backend + SwiftUI done, fully built
  - Phase 3 (#389): Backend done, SwiftUI Mind Palace views missing
  - Phase 4 (#390): Backend done, SwiftUI Research views missing
  - Phase 5 (#391): Not started — MCP adapters + integration
  - 0.0.1 regression bugs (#382-#386) are NOT blockers for 0.0.2 work
- Added `pykeen` to `pyproject.toml` (Briefcase `requires` + `dependencies`)
- Removed stale `BLOCK.md` and `CONTINUE.md`

## 2026-04-03 — Autonomous Loop Session

- **#367**: Reversible entity merge/split + claim curation transitions
  - `POST /entities/merge`: absorbs entities into survivor with alias preservation
  - `POST /entities/split`: distributes aliases across primary + split-off entities
  - `POST /entities/audit/{id}/undo`: reverses any merge/split via audit chain
  - `GET /entities/audit`: lists audit records filtered by entity_id
  - `EntityMergeAudit` model: immutable operation log with reversal linkage
  - `KnowledgeEntity.merged_into_id` used for soft-delete redirect
  - `curated_only=true` convenience filter on GET /claims and GET /claims/filtered

- **#362**: General mutation log with undo/rollback for KG entities
  - `MutationLog` model: before/after state snapshots with `run_id` for AI batch grouping
  - `POST /knowledge-mutations/undo`: undo single mutation or rollback full AI run
  - `GET /knowledge-mutations`: list with filters (entity_type, entity_id, run_id, created_by)
  - `POST|PATCH /claims` now log mutations automatically with run_id/agent_id query params
  - `_log_mutation` helper for wiring mutations into any KG entity

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

- **#395**: Fixed 8 SwiftLint violations across 4 SwiftUI view files:
  - Extracted 13 component files from 4 long views
  - Result: 0 violations across 341 Swift files

**All 900 pytest pass. ruff clean. SwiftLint clean.**

## 2026-04-02 — Autonomous Loop Session

- #381: Created `docs/agent-workflow/0.0.2-gate-map.md` — gate map for Layers 0-6
- #365: SourceMetadata model + citation validation (DOI, ISBN-13/10, ISSN, arXiv) + ProvenanceInfo + 36 unit tests
- #366: GET /entities/alias-map + GET /claims?entity=X filter + 2 unit tests
- #392: Added 4 MCP tools — generate/apply predictions, circle navigation
- OpenAPI sync: 46 endpoints across 16 resources — regenerated Swift client
- SwiftLint: auto-fixed 88 sorted_imports violations (101 files), 6 identifier_name violations
- rules.json: agent rules configuration committed
- Phase 1 SwiftUI: ClaimInspectorView, OntologyBrowserView, EpistemologyGraphView, PredictionReviewView

## 2026-04-10 — Session Summary

- **Session Start Assessment**: Reviewed #388 (Hermeneutics Phase 2) state — work was stopped at user request
- **Git State Observation**: codex/0.0.2-planning branch, skills relocated to plugins, .venv untracked
- **Planning branch issue**: Active work should happen on main or feature branch, not planning branch
