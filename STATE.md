# STATE.md — Fichero

## Current Focus

**Milestone:** 0.0.2 (Search + Semantic Foundation) - COMPLETE ✅

**Status:** Issue #364 complete - Canonical FastAPI knowledge write path
- Branch: `feature/issue-364` pushed to GitHub, ready for PR
- Dedicated entities.py, claims.py, claim_links.py route modules created
- All routes registered and verified working

## Recently Completed (Session 2026-04-12)

### Issue #364 - Canonical FastAPI Knowledge Write Path
**Commit:** `3373274a`

**Implementation:**
- Created dedicated entities.py route module with:
  - POST /entities, GET /entities, GET /entities/{id}
  - POST /entities/{id}/aliases
  - GET /entities/alias-map, GET /entities/resolve/{value}

- Created dedicated claims.py route module with:
  - POST /claims, GET /claims, GET /claims/{id}, PATCH /claims/{id}
  - Multi-source support (source_ids, source_languages)
  - Claim classification (claim_type, epistemic_status)
  - Referential integrity validation

- Created dedicated claim_links.py route module with:
  - POST /claims/{id}/links, GET /claims/{id}/links
  - GET /claim-links/{id}, PATCH /claim-links/{id}, DELETE /claim-links/{id}
  - GET /claims/{id}/related

- Registered all routes in main.py _CORE_ROUTE_SECS
- Created contract tests for entity/claim/link CRUD operations

## 0.0.2 Milestone Status - COMPLETE ✅

All issues resolved:
- ✅ #364: Canonical FastAPI knowledge write path
- Security: #400, #402, #404, #406, #408
- Migration: #419
- Background Tasks: #420
- Multilingual: #421
- MCP Adapters: #422
- Activity Stream: #425
- Orchestration Policy: #426
- PyKEEN Inference: #429
- NetworkX Reasoning: #430
- Graph Exploration: #431
- Search Explanation: #438
- Contradiction Triage: #436
- Interpretations Workspace: #439
- Review Queue: #440
- MCP Adapters Re-merge: #444

## Next Session — Start Here

### 1. Review and Merge 0.0.2 PR

**Branch ready for PR:**
- `feature/issue-364` — Canonical knowledge write paths

### 2. Complete 0.0.3 Milestone

**Issues to review/merge:**
- #368: Knowledge migration/backfill
- #369: Reindex/repair jobs
- #370: Multilingual baseline
- #371: MCP adapters

### 3. Start 0.0.4 Milestone

**Milestone 0.0.4 (Semantic UX + Trust Workflow):**
- Issue #372: Claim review queue UI with curation workflow
- Issue #373: Contradiction triage UI with side-by-side provenance
- Issue #374: Search explanation and metrics visibility panel
- Issue #375: Interpretations workspace v1 linked to claims

### 4. Review GitHub Project Board

- **Project:** https://github.com/users/dtubb/projects/5
- **Milestones:** https://github.com/dtubb/fichero/milestones
- **Issues:** https://github.com/dtubb/fichero/issues

---
*Last updated: 2026-04-12* — 0.0.2 milestone complete, ready for PR review
