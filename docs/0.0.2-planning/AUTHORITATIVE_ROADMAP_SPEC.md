# Fichero Authoritative Roadmap Spec (0.0.2 -> 0.1.0)

**Status:** Canonical planning spec  
**Date:** 2026-03-29  
**Worktree:** `codex/0.0.2-planning`

## 1) Summary

This is the single source of truth for roadmap planning.

Core priorities:
- Search + Semantic scope clarity across `0.0.2` -> `0.1.0`
- Source reference metadata + provenance rigor
- Claim curation, entity-centric retrieval, multilingual + contradiction handling
- Feature gating through current mechanisms only (`FICHERO_FEATURE_TIER`, existing flags, existing QA gate pattern)

Architecture invariants:
- FastAPI is canonical for state changes
- SwiftUI and MCP are peer clients to backend contracts
- No business-logic forks in clients
- Claims always trace to source evidence (`claim -> segment -> source`)

Ontology vs interpretation separation:
- **Ontology layer:** entities, claims, claim links, contradiction state
- **Interpretation layer:** argument/method records linked to claims and sources

---

## 2) Milestone Breakdown (Decision-Complete)

### 0.0.2 — Search + Semantic Foundation

Deliverables:
- Canonical FastAPI knowledge write path
- Source reference metadata contract + validation
- Unified lexical + semantic retrieval contract
- Entity-centric claim retrieval (entity + alias + entity-type filters)
- Knowledge CRUD for sources/entities/claims/claim-links
- Undo/rollback + snapshot/restore baseline
- Curation v1 (`unreviewed/shortlisted/curated/rejected`)
- Reversible entity merge/split and alias normalization
- SwiftUI + MCP convergence on canonical API contracts

Non-goals:
- Advanced orchestration loops
- NetworkX/PyKEEN runtime integration
- Embedded IFFY/IIIF server mode

### 0.0.3 — Migration + Operational Hardening

Deliverables:
- Migration/backfill tooling with dry-run + rollback validation
- Reindex/repair jobs and recomputation workers
- Multilingual baseline (language-aware fields, transliteration-aware alias linking)
- Contradiction workflows v1
- Thin MCP adapters mapped 1:1 to canonical FastAPI contracts

### 0.0.4 — Semantic UX + Trust Workflow

Deliverables:
- Claim review queue UX
- Contradiction triage UX (side-by-side evidence)
- Search explanation + metrics visibility
- Interpretations workspace v1

### 0.1.0 — Epistemic Platform Expansion

Deliverables:
- Advanced orchestration policy + flows
- Derived graph reasoning integration (NetworkX)
- Optional latent inference track (PyKEEN)
- Optional embedded IFFY/IIIF server mode
- Advanced graph/interpretation exploration

Note:
- Legacy/re-enable items remain in `0.1.0` by decision and must be labeled `legacy-reenable`.

---

## 3) Public Contract Set (Frozen for Planning)

### Source Metadata Contract

Required source fields:
- `title`, `authors`, `publication_date`, `publisher`, `journal_name`
- `doi`, `isbn`, `issn`
- `archive_id` / `digital_object_id`, `call_number`
- `repository`, `repository_url`, `source_url`
- `iiif_manifest`, `iiif_image` (when available)
- `language`, `rights_statement`, `restrictions`, `provenance`

Behavior:
- Preserve raw imported values and normalized values
- Track metadata provenance (`imported|manual|agent`, timestamp)
- Validate identifier formats where practical

### Claim Navigation Contract

Required retrieval flows:
- entity -> claims
- entity type -> claims (e.g., all location claims)
- contradiction-only filter
- curated-only filter
- alias-aware and transliteration-aware entity matching

### Provenance Contract

Every claim/detail payload must include:
- `source_id`
- `segment_id` (or segment locator)
- evidence snippet/locator metadata

### Curation Contract

States:
- `unreviewed`, `shortlisted`, `curated`, `rejected`

Rules:
- state transitions are auditable
- curated filters must be available in retrieval APIs

### Entity Resolution Contract

Required operations:
- reviewer-controlled merge
- reviewer-controlled split
- reversible and audit-logged operations
- alias list and resolver confidence visible in review surfaces

### MCP Contract Policy

- API-first contracts are canonical
- MCP knowledge tools are thin adapters by milestone phase
- no logic divergence vs HTTP pathways

---

## 4) Feature Gate Map (Current Approach Only)

### Gate system

Use only:
- `FICHERO_FEATURE_TIER` (`dev`, `release`)
- existing feature flags
- existing release-gate checklist style

### Promotion criteria

#### 0.0.2 slice promotion (`dev -> release`)
Requires evidence for:
- contract tests (SwiftUI + MCP)
- provenance integrity tests
- undo/snapshot recovery tests
- entity/alias retrieval tests
- reference metadata validation tests

#### 0.0.3 slice promotion
Requires evidence for:
- migration dry-run + rollback verification
- job interruption/recovery validation
- MCP adapter parity tests vs HTTP fixtures

#### 0.0.4 slice promotion
Requires evidence for:
- contradiction triage correctness
- curation workflow integrity
- provenance report/export integrity

#### 0.1.0 slice promotion
Requires evidence for:
- traceable autonomous writes
- rollback path for autonomous changes
- interpretation linkage to supporting claims/sources

### Gate ownership + evidence artifacts

- **Backend owner:** API contract/gate pass evidence (`tests`, endpoint fixtures)
- **SwiftUI owner:** UI curation/review behavior evidence (integration scenarios)
- **MCP owner:** parity evidence between MCP tool outputs and HTTP contract fixtures
- **QA owner:** milestone gate checklist completion with linked artifacts

---

## 5) Backlog Normalization and Dependency Matrix

Legend:
- **Blocking contracts:** required contract family from Section 3
- **Required gates:** minimum gate proof needed for completion
- **Cannot start before:** prerequisite issue(s)

### 0.0.2 issues

| Issue | Blocking Contracts | Required Gates | Cannot Start Before |
|---|---|---|---|
| #364 Canonical FastAPI knowledge write path | Provenance, MCP policy | Contract + provenance | — |
| #365 Source reference metadata contract | Source metadata | Contract + metadata validation | #364 |
| #366 Entity-centric claim retrieval + alias lookup | Claim navigation, Entity resolution, Provenance | Retrieval + alias tests | #364 |
| #367 Reversible merge/split + curation state v1 | Curation, Entity resolution | Undo/snapshot + curation tests | #364, #366 |
| #361 XMP sidecar support | Source metadata | Metadata validation | #365 |
| #362 Undo/rollback baseline | Curation, Entity resolution | Undo/recovery | #364 |
| #363 Snapshot/restore baseline | Provenance, Curation | Snapshot/restore | #362 |
| #381 Gate map using current tier/flags | Gate map policy | Gate checklist signoff | #364, #365, #366, #367, #362, #363 |

### 0.0.3 issues

| Issue | Blocking Contracts | Required Gates | Cannot Start Before |
|---|---|---|---|
| #368 Migration/backfill tooling | Source metadata, Provenance | Dry-run + rollback | #364, #365 |
| #369 Reindex/repair + recompute jobs | Claim navigation, Provenance | Job recovery + parity | #366 |
| #370 Multilingual baseline | Entity resolution, Claim navigation | Cross-language retrieval tests | #366 |
| #371 Thin MCP adapters | MCP policy, Claim navigation | MCP parity vs HTTP | #364, #366 |

### 0.0.4 issues

| Issue | Blocking Contracts | Required Gates | Cannot Start Before |
|---|---|---|---|
| #372 Claim review queue UI | Curation, Provenance | Curation workflow | #367 |
| #373 Contradiction triage UI | Claim navigation, Provenance | Contradiction correctness | #366, #370 |
| #374 Search explanation + metrics panel | Claim navigation | Explanation consistency | #366, #369 |
| #375 Interpretations workspace v1 | Provenance, Interpretation linkage | Linkage integrity | #372, #373 |

### 0.1.0 epistemic issues

| Issue | Blocking Contracts | Required Gates | Cannot Start Before |
|---|---|---|---|
| #376 NetworkX integration | Provenance, Claim navigation | Reproducible derived graph evidence | #369 |
| #377 PyKEEN optional track | Entity resolution, Claim navigation | Predicted-link review + rollback | #376 |
| #378 Embedded IFFY/IIIF server mode | Source metadata, MCP policy | Security/provenance policy checks | #365 |
| #379 Advanced graph/interpretation views | Interpretation linkage, Claim navigation | Graph/interpretation UX acceptance | #375, #376 |
| #380 Human-in-the-loop orchestration policy | Curation, Provenance, MCP policy | Autonomous write traceability + rollback | #376, #377 |

### 0.1.0 legacy/re-enable issues (kept by decision)

Legacy cohort:
- #280, #281, #282, #283, #284, #285, #286, #287
- #256, #257, #258

Policy:
- Must be labeled `legacy-reenable`
- Must not block epistemic acceptance gates unless explicitly linked

---

## 6) Implementation Handoff Queue (0.0.2)

Ordered execution queue:
1. Contract lock + canonical route registration (#364)
2. Reference metadata contract implementation (#365)
3. Entity-centric retrieval + alias lookup (#366)
4. Undo/snapshot safety baseline (#362, #363)
5. Merge/split + curation states (#367)
6. XMP sidecar metadata alignment (#361)
7. Gate map + evidence checklist wiring (#381)

Per-slice acceptance checklist:
- Contract tests green
- Provenance integrity green
- Safety (undo/snapshot) green for mutation slices
- Alias/navigation tests green for retrieval slices
- Gate evidence linked and reviewable

---

## 7) Planning QA Checklist

Plan consistency checks:
- No duplicate/conflicting scope statements across planning docs
- Clear in/out boundary per milestone

Backlog alignment checks:
- Every open issue in `0.0.2/0.0.3/0.0.4/0.1.0` maps to a capability in this spec
- Every mapped issue has gates + prerequisites listed

Interface readiness checks:
- Contract set covers source metadata, claim retrieval, provenance, curation, alias normalization, and MCP policy

Gate readiness checks:
- Each milestone has explicit go/no-go gate criteria and evidence expectations
