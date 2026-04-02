# STATE.md — Fichero

Last updated: 2026-04-02

## Current Branch

`codex/0.0.2-planning` — 0.0.2 semantic layer planning and early implementation

## Source of Truth

- GitHub Issues + Milestones: https://github.com/dtubb/fichero/milestones
- Project board: https://github.com/users/dtubb/projects/5
- Canonical roadmap: `docs/0.0.2-planning/AUTHORITATIVE_ROADMAP_SPEC.md`

## Completed This Session

- Aligned GitHub issues (#387-#391) with roadmap spec
- Confirmed TASKS.md deprecated — GitHub is sole source of truth for execution
- Confirmed 17 open issues cover 0.0.2 → 0.1.0 scope

## Active Work (2026-04-02)

**Phase 1: Knowledge Graph Core + PyKEEN (#387) — IN PROGRESS**

Backend complete (models, migration, routes, embeddings, MCP tools).
Deferred: PyKEEN wiring (needs `pykeen` dependency), SwiftUI views (Phase 1-4 UI pending).

Next step for Phase 1:
- SwiftUI views: ClaimInspectorView, OntologyBrowserView, EpistemologyGraphView, PredictionReviewView

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

1. **Claim #387** if not already claimed — verify backend tests still green
2. **Build SwiftUI views for Phase 1**: ClaimInspectorView, OntologyBrowserView, EpistemologyGraphView, PredictionReviewView
3. **Sync OpenAPI schema** (`./scripts/sync_openapi_schema.sh`) after any backend changes
4. **Verify `ruff check` and `swiftlint`** pass before any PR
5. After Phase 1 SwiftUI done — move to Phase 2 (#388, Hermeneutics)
