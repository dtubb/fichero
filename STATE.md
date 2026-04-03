# STATE.md — Fichero

Last updated: 2026-04-02

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

## Active Work (2026-04-02)

**Phase 1: Knowledge Graph Core + PyKEEN (#387) — SWIFTUI COMPLETE, supporting features done**

Backend complete (models, migration, routes, embeddings, MCP tools).
SwiftUI views: all done — ClaimInspectorView, OntologyBrowserView, EpistemologyGraphView, PredictionReviewView.
Deferred: PyKEEN wiring (needs `pykeen` dependency).

Supporting work done this session:
- #381: gate map documented in `docs/agent-workflow/0.0.2-gate-map.md`
- #365: SourceMetadata model implemented (citation validation)
- #366: entity alias-map + `?entity=` filter implemented
- SwiftLint: 6 identifier_name violations fixed
- #367 partial: `curated_only=true` filter added to claims endpoints

## Active Work (2026-04-02)

**Phase 1: Knowledge Graph Core + PyKEEN (#387) — SWIFTUI COMPLETE, supporting features done**

Backend complete (models, migration, routes, embeddings, MCP tools).
SwiftUI views: all done — ClaimInspectorView, OntologyBrowserView, EpistemologyGraphView, PredictionReviewView.
Deferred: PyKEEN wiring (needs `pykeen` dependency).

Supporting work done this session:
- #381: gate map documented in `docs/agent-workflow/0.0.2-gate-map.md`
- #365: SourceMetadata model implemented (citation validation)
- #366: entity alias-map + `?entity=` filter implemented

**Phase dependencies:** Phase 2-5 all depend on Phase 1 backend being solid.

## Blocked

- None currently — Phase 1 backend is complete, UI work can proceed independently

## Open Issues by Phase

| Phase | Issue | Status | Notes |
|-------|-------|--------|-------|
| Phase 1 | #387 | In Progress | Backend done; SwiftUI pending |
| Phase 2 | #388 | Not Started | Depends on #387 |
| Phase 3 | #389 | Not Started | Depends on #387, #388 |
| Phase 4 | #390 | Not Started | Depends on #387, #388, #389 |
| Phase 5 | #391 | Not Started | Depends on #387-390 |

Plus 12 sub-task issues (#362-#381) for 0.0.2-0.1.0 features.

## Next Session — Start Here

1. **Remaining Phase 1 SwiftUI**: PyKEEN wiring (backend) — add `pykeen` to dependencies, wire `POST /predictions/generate/pykeen`, implement training pipeline
2. Verify `ruff check` and `swiftlint` pass before any PR
3. After Phase 1 PyKEEN done — move to Phase 2 (#388, Hermeneutics)
4. 8 pre-existing length violations in KnowledgeGraph views (files 400-505 lines) — low priority
