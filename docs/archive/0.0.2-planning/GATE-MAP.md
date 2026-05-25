# 0.0.2 Feature Gate Map

## Overview

Fichero uses a two-tier feature gate system controlled by the `FICHERO_FEATURE_TIER` environment variable:

| Tier | Env Value | What's Exposed |
|------|-----------|----------------|
| **release** | `FICHERO_FEATURE_TIER=release` | Core routes only |
| **dev** | `FICHERO_FEATURE_TIER=dev` | Core + all 0.0.2 layers |

Default when unset: `release`.

**Promotion path:** `dev` → `release` requires completing the promotion criteria for each layer.

---

## Layer Gate Matrix

### Layer 0 — Agent Research (Research Projects/Plans/Tasks/Steps + Sandboxed Tools)

| Component | Route Prefix | Release Gate Status | Promotion Criteria |
|-----------|-------------|---------------------|--------------------|
| Research Project/Plan/Task/Step CRUD | `/api/research` | **DEV** — complete | None needed (data model only) |
| Sandboxed Web Search | `/api/research/tools/web-search` | **DEV** — complete | 1. Sandbox security tests pass |
| Sandboxed Browser Navigate | `/api/research/tools/browser-navigate` | **DEV** — complete | 1. Sandbox security tests pass |
| Sandboxed Document Fetch | `/api/research/tools/document-fetch` | **DEV** — complete | 1. Source creation tested |
| LangGraph Research Agent | _(not yet implemented)_ | **DEV** — not started | See Phase 4 issue #390 |

**Promotion criteria for Layer 0:**
- [ ] All sandbox tools block `file://`, `ftp://`, `smb://`, `s3://` URLs (verified by `test_sandbox_blocks_dangerous_urls`)
- [ ] LangGraph agent wired to workflow executor
- [ ] Research activity monitoring endpoints
- [ ] SwiftUI Research views built

---

### Layer 1 — Sources (Documents)

| Component | Route Prefix | Release Gate Status | Promotion Criteria |
|-----------|-------------|---------------------|--------------------|
| Document CRUD | `/api/documents` | **RELEASE** — always on | N/A (existing) |
| Document Ingest | `/api/ingest` | **RELEASE** — always on | N/A (existing) |
| Source reference metadata | _(tracked in #365)_ | **DEV** — incomplete | See issue #365 |

**Promotion criteria for Layer 1:**
- [ ] Issue #365 (source reference metadata) resolved
- [ ] Migration idempotency verified for existing documents

---

### Layer 2 — Claims (Multi-Source)

| Component | Route Prefix | Release Gate Status | Promotion Criteria |
|-----------|-------------|---------------------|--------------------|
| Claims CRUD + filters | `/api/knowledge-graph` | **DEV** — complete | 1. Heuristic predictions working |
| Multi-source claim creation | `/api/knowledge-graph` | **DEV** — complete | 1. Migration script tested on real data |
| Semantic embed + search | `/api/knowledge-graph` | **DEV** — complete | 1. LanceDB index operational |
| Similar claim retrieval | `/api/knowledge-graph` | **DEV** — complete | 1. Embedding quality spot-check |

**Promotion criteria for Layer 2:**
- [ ] Migration script (`scripts/migrate_claims_to_multi_source.py`) run on real library
- [ ] Semantic search relevance validated by human
- [ ] SwiftUI ClaimInspectorView built and reviewed

---

### Layer 3 — Ontology (Entity-Centric Views)

| Component | Route Prefix | Release Gate Status | Promotion Criteria |
|-----------|-------------|---------------------|--------------------|
| Entity CRUD + alias management | `/api/knowledge-graph` | **DEV** — complete | 1. Alias-aware lookup tested |
| Entity-centric claim view | `/api/knowledge-graph` | **DEV** — complete | 1. Entity "bio" view validated |
| Semantic entity search | `/api/knowledge-graph` | **DEV** — complete | 1. Search relevance spot-check |

**Promotion criteria for Layer 3:**
- [ ] Entity alias-aware lookup tested with real aliases
- [ ] OntologyBrowserView (SwiftUI) built
- [ ] Reversible entity merge/split (issue #367) reviewed

---

### Layer 4 — Epistemology (Claim Relationships)

| Component | Route Prefix | Release Gate Status | Promotion Criteria |
|-----------|-------------|---------------------|--------------------|
| Claim relationship (supports/contradicts) | `/api/knowledge-graph` | **DEV** — complete | 1. Relationship CRUD tested |
| Evidence chain queries | `/api/knowledge-graph` | **DEV** — complete | 1. Chain traversal performance OK |
| PyKEEN predictions | `/api/knowledge-graph` | **DEV** — not wired | See Phase 1 issue #387 |

**Promotion criteria for Layer 4:**
- [ ] `POST /predictions/generate/heuristic` producing sensible results
- [ ] `apply_prediction` path verified end-to-end (currently returns 501 for actual PyKEEN)
- [ ] PyKEEN training pipeline implemented OR heuristic path formally adopted as permanent
- [ ] EpistemologyGraphView (SwiftUI) built

---

### Layer 5 — Hermeneutics (Interpretation)

| Component | Route Prefix | Release Gate Status | Promotion Criteria |
|-----------|-------------|---------------------|--------------------|
| Interpretive Framework CRUD | `/api/hermeneutics` | **DEV** — complete | 1. Framework model reviewed |
| Hermeneutic Context application | `/api/hermeneutics` | **DEV** — complete | 1. Context application tested |
| Pattern detection | `/api/hermeneutics` | **DEV** — complete | 1. Pattern recognition validated |
| Part-whole navigation | `/api/hermeneutics` | **DEV** — complete | 1. Circle navigation UX reviewed |
| AI interpretation suggestions | `/api/hermeneutics` | **DEV** — complete | 1. LLM integration tested |

**Promotion criteria for Layer 5:**
- [ ] InterpretationPanelView (SwiftUI) built
- [ ] PatternBrowserView (SwiftUI) built
- [ ] At least one interpretive framework defined and tested
- [ ] LLM interpretation quality reviewed by human

---

### Layer 6 — Mind Palace (Visual + Spatial)

| Component | Route Prefix | Release Gate Status | Promotion Criteria |
|-----------|-------------|---------------------|--------------------|
| Mind Palace Space CRUD | `/api/mind-palace` | **DEV** — complete | 1. Space model reviewed |
| RealityKit viewport | _(SwiftUI + RealityKit)_ | **DEV** — not started | See Phase 3 issue #389 |
| 3D spatial notes | _(SwiftUI + RealityKit)_ | **DEV** — not started | See Phase 3 issue #389 |

**Promotion criteria for Layer 6:**
- [ ] MindPalaceView (SwiftUI) built
- [ ] RealityKit 3D viewport integrated
- [ ] Spatial note placement working
- [ ] Performance acceptable on target hardware

---

## Current Gate State Summary

```
RELEASE tier:  /api/documents  /api/search  /api/ingest  /api/storage
                /api/folders  /api/artifacts  /api/providers  /api/models
                /api/chat  /api/workflows  /api/workflow-execution

DEV tier only: /api/knowledge-graph  (Layers 1-4)
               /api/hermeneutics     (Layer 5)
               /api/mind-palace     (Layer 6)
               /api/research        (Layer 0)
```

**Nothing in Layers 0-6 has been promoted to `release` tier yet.**

---

## Promotion Checklist Template

For each layer, before promoting from `dev` → `release`:

- [ ] All unit tests pass (`python -m pytest fichero-engine/tests/unit/`)
- [ ] All API integration tests pass for the layer
- [ ] Layer-specific quality gates documented above are complete
- [ ] SwiftUI views built and reviewed (or explicit opt-out documented)
- [ ] `FICHERO_FEATURE_TIER=release` tested locally
- [ ] `scripts/sync_openapi_schema.sh` run
- [ ] Swift client regenerated and builds
- [ ] Migration scripts tested on realistic data
- [ ] Performance acceptable at expected data scale

---

## Implementation

- Gate system: `fichero-engine/src/fichero/api/main.py`
  - `_CORE_ROUTE_SPECS`: always-on routes
  - `_DEV_ROUTE_SPECS`: dev-only routes
  - `resolve_feature_tier()`: reads `FICHERO_FEATURE_TIER` env
- Feature flags (route-internal): currently none beyond tier system
- SwiftUI tier gating: not yet implemented — views show all features; gate in API only
- Tests: `fichero-engine/tests/unit/test_feature_tier_routing.py`

---

## Related

- Issue #381: Gate map for semantic features
- Issue #387: Phase 1 — Knowledge Graph Core + PyKEEN
- Issue #388: Phase 2 — Hermeneutics
- Issue #389: Phase 3 — Mind Palace + RealityKit
- Issue #390: Phase 4 — Agent Research
- Issue #391: Phase 5 — Integration & Polish
- Plan: `docs/agent-workflow/PLAN-0.0.2-knowledge-graph.md`
