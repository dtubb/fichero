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

## Completed This Session (2026-04-03 autonomous loop)

- **#395**: Fixed 8 SwiftLint violations across 4 SwiftUI view files:
  - `PredictionReviewView`: Extracted 4 subviews + state object → 0 violations
  - `EpistemologyGraphView`: Extracted 9 component views → 0 violations
  - `OntologyBrowser`: Extracted 4 subviews → 0 violations
  - `DocumentInspectorContentTab`: Extracted NSViewRepresentable + state object → 0 violations
  - **Result: 0 violations** across 341 Swift files
- **#387**: Updated issue body — confirmed SwiftUI views complete; stale DEFERRED section corrected
- **#367**: Updated issue body — `curated_only` filter confirmed done; merge/split/audit not done

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
2. **Entity merge/split** (#367): `POST /entities/merge`, `POST /entities/split`, audit log, undo
3. **After Phase 1 PyKEEN done**: move to Phase 2 (#388, Hermeneutics)
4. **0.0.1 regression gate**: manual QA checklist in `docs/qa/0.0.1-manual-qa-checklist.md`
