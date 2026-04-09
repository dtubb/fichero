# STATE.md — Fichero

Last updated: 2026-04-09

## Current Branch

`codex/0.0.2-planning` — 0.0.2 semantic layer planning and early implementation

## Source of Truth

- GitHub Issues + Milestones: https://github.com/dtubb/fichero/milestones
- Project board: https://github.com/users/dtubb/projects/5
- Canonical roadmap: `docs/0.0.2-planning/AUTHORITATIVE_ROADMAP_SPEC.md`

## Completed This Session (2026-04-09)

- Verified GitHub issue #387 directly via `gh issue view` before implementation
- Wired `POST /predictions/generate/pykeen` to real PyKEEN training/evaluation in `fichero-api/src/fichero/api/routes/knowledge_graph.py`
- Rejected a simulated/fake Codex implementation and replaced it with actual PyKEEN pipeline usage (`TriplesFactory`, `pipeline`, `predict_target`)
- Added/updated unit tests covering PyKEEN run persistence and missing-graph validation in `fichero-api/tests/unit/test_knowledge_graph_api.py`
- Validated targeted backend tests, `ruff check`, and `swiftlint`

## Phase Implementation Status (2026-04-07 Assessment)

### Phase 1 — Knowledge Graph Core + PyKEEN (#387) ⚠️ PARTIAL
**Backend:** Models, migration, routes, embeddings, MCP tools, unit tests — DONE
**SwiftUI:** OntologyBrowser, EpistemologyGraph, ClaimInspector, PredictionReview — DONE
**Now completed:**
- `POST /predictions/generate/pykeen` is wired to real PyKEEN training/evaluation
- Real PyKEEN imports added in `knowledge_graph.py`
- Prediction runs persist `KnowledgePredictionRun` records with real ranking metrics and preview metadata
**Still missing:**
- No model artifact persistence/loading yet
- `POST /predictions/{run_id}/apply` still returns 501
- No OpenAPI/schema sync or Swift client regeneration has been run for this change
- No full backend suite / xcodebuild pass has been run yet this session

### Phase 2 — Hermeneutics (#388) ✅ BUILT
- Models (`hermeneutics_models.py`): Framework, Interpretation, HermeneuticCircle, PatternInstance, HermesSuggestion — all done
- Routes (`hermeneutics.py` 542 lines): full CRUD for frameworks, interpretations, circles, suggestions
- SwiftUI views: `InterpretationPanelView`, `FrameworkListView`, `InterpretationListView`, `HermeneuticCircleListView` — all done
- **Ready for wiring / testing**

### Phase 3 — Mind Palace / RealityKit (#389) ✅ BUILT
- Models (`spatial_models.py`): SpatialRoom, SpatialNode, SpatialViewport, NativeNote, etc. — all done
- Routes (`mind_palace.py` 774 lines): full CRUD for rooms, nodes, viewports, notes
- **SwiftUI Mind Palace views: NOT BUILT** — Layer 6 spatial workspace SwiftUI is still outstanding

### Phase 4 — Agent Research / Layer 0 (#390) ✅ BUILT
- Models (`research_models.py` 273 lines): ResearchProject, ResearchPlan, ResearchTask, ResearchNote, etc.
- Routes (`research_agents.py` 846 lines): full CRUD for projects, sessions, results, sandbox tools
- **SwiftUI Research views: NOT BUILT** — Layer 0 agent research UI is still outstanding

### Phase 5 — Integration & Polish (#391) ⚠️ NOT STARTED
- MCP adapters for all 4 phases (Layer 0, 5, 6, KG)
- Integration tests across routes
- SwiftUI navigation wiring for all new views

## Regression Gate (0.0.1 Bugs #382-#386)

**Decision:** 0.0.1 regression bugs (#382-#386) are not autonomous — need manual QA. However, they are **not blockers** for continuing 0.0.2 work. 0.0.2 code doesn't touch the 0.0.1 bug surface.

**Action:** Daniel runs QA when ready. 0.0.2 work continues in parallel.

## Open Issues by Phase

| Phase | Issue | Status | Notes |
|-------|-------|--------|-------|
| Phase 1 | #387 | In Progress | PyKEEN route is now wired; remaining work is model artifact persistence, apply/inference path, and full quality/openapi follow-through |
| Phase 2 | #388 | In Progress | Backend + SwiftUI done, needs wiring verification |
| Phase 3 | #389 | In Progress | Routes done, SwiftUI Mind Palace views missing |
| Phase 4 | #390 | In Progress | Routes done, SwiftUI Research views missing |
| Phase 5 | #391 | Not Started | MCP adapters + integration tests |

## Next Session — Start Here

1. **Finish #387 properly:** run broader backend quality checks, then decide whether this route needs OpenAPI sync / Swift client regeneration despite no request/response schema change
2. **Implement next PyKEEN step:** add model artifact persistence and/or wire `POST /predictions/{run_id}/apply` off stored run metadata
3. **Phase 2 verification** (#388): run hermeneutics routes/tests end-to-end after #387 is stable
4. **Check git state first:** there are pre-existing unrelated deletions/modifications in the worktree; do not commit blindly
