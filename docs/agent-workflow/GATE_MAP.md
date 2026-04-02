# 0.0.2 Feature Gate Map

Maps each 0.0.2 component to its gate status using `FICHERO_FEATURE_TIER` + existing feature flag system.

## Gate System

| Tier | Env Var | What's Enabled |
|---|---|---|
| `release` | `FICHERO_FEATURE_TIER=release` | Core 0.0.1 routes only |
| `dev` | `FICHERO_FEATURE_TIER=dev` | Core + all 0.0.2 routes |

## Current Route Assignments

### Core Routes (Always Enabled — `release` tier)

These routes are in `_CORE_ROUTE_SPECS` and run under both tiers:

| Route Prefix | Module | Feature |
|---|---|---|
| `/api/documents` | `documents.py` | Document management |
| `/api/search` | `search.py` | Semantic search |
| `/api/ingest` | `ingest.py` | File import |
| `/api/storage` | `storage.py` | Storage operations |
| `/api/folders` | `folders.py` | Folder management |
| `/api/artifacts` | `artifacts.py` | Artifact storage |
| `/api/providers` | `providers.py` | LLM provider config |
| `/api/models` | `models.py` | Model config |
| `/api/workflows` | `workflows.py` | Workflow definitions |
| `/api/workflow-execution` | `workflow_execution.py` | Workflow execution |
| `/api/batches` | `batch.py` | Batch operations |
| `/api/activity` | `activity.py` | Activity feed |
| `/api/chat` | `chat.py` | RAG chat |
| `/api/settings` | `settings.py` | App settings |

### Knowledge Graph Routes (`dev` tier only — `_DEV_ROUTE_SPECS`)

These routes are in `_DEV_ROUTE_SPECS` and require `FICHERO_FEATURE_TIER=dev`:

| Route Prefix | Module | Phase | Description |
|---|---|---|---|
| `/api/knowledge-graph` | `knowledge_graph.py` | Phase 1 | Claims, entities, epistemology, predictions |
| `/api/hermeneutics` | `hermeneutics.py` | Phase 2 | Interpretive frameworks, patterns, hermeneutic circle |
| `/api/mind-palace` | `mind_palace.py` | Phase 3 | 3D spatial workspace, RealityKit |
| `/api/research` | `research_agents.py` | Phase 4 | Agent research projects, sandboxed web tools |

## Promotion Criteria

A component is promoted from `dev` → `release` tier when:

1. **Unit tests pass** — `pytest fichero-api/tests/unit/`
2. **API contract tests pass** — `pytest test_api_contracts.py`
3. **Swift client builds** — `xcodebuild build` succeeds with generated client
4. **SwiftLint zero warnings** — no serious violations
5. **Ruff zero errors** — clean Python lint
6. **Backend verified** — manual smoke test on `/health` endpoint
7. **Integration tested** — end-to-end workflow from SwiftUI to backend

## Feature Flags (Backend)

Feature flags live in `fichero-api/src/fichero/api/main.py`:

```python
# Tier resolution
FICHERO_FEATURE_TIER=release  # Core only
FICHERO_FEATURE_TIER=dev      # Core + 0.0.2 features
```

## Feature Flags (SwiftUI)

SwiftUI views gate on feature detection via `FeatureGate` enum:

```swift
enum FeatureGate {
    case knowledgeGraph    // dev tier
    case hermeneutics      // dev tier
    case mindPalace        // dev tier
    case agentResearch     // dev tier
}
```

Gate enforcement in SwiftUI is view-level visibility — routes still exist on the backend, but the UI hides unavailable features.

## Promotion Checklist

For each phase, before promoting to `release` tier:

- [ ] Python: `ruff check fichero-api/src/` — zero errors
- [ ] Python: `python -m pytest fichero-api/tests/unit/` — all pass
- [ ] Python: `python -m pytest fichero-api/tests/unit/test_api_contracts.py` — all pass
- [ ] Swift: `swiftlint lint` — zero serious violations
- [ ] Swift: `xcodebuild build` — succeeds
- [ ] Backend: `uvicorn` starts cleanly with `FICHERO_FEATURE_TIER=release`
- [ ] Routes: All tiered routes respond correctly to `FICHERO_FEATURE_TIER` change
- [ ] Swift client: `swift package build` succeeds in `fichero-api-client/`

## Current Status

| Component | Tier | Tests | SwiftLint | Build | Notes |
|---|---|---|---|---|---|
| Knowledge Graph (backend) | dev | ✅ 14/14 | ✅ | ✅ | Phase 1 complete |
| Knowledge Graph (SwiftUI) | dev | ❌ deferred | ✅ | ❌ deferred | ClaimInspectorView deferred |
| Hermeneutics (backend) | dev | ❌ | ✅ | ✅ | Phase 2 backend done |
| Hermeneutics (SwiftUI) | dev | ❌ | ✅ | ✅ | InterpretationPanelView refactored |
| Mind Palace | dev | ❌ | ✅ | ❌ | Backend routes exist |
| Agent Research | dev | ❌ | ✅ | ❌ | Backend routes exist |
| Integration | dev | ❌ | ✅ | ❌ | Phase 5 not started |
