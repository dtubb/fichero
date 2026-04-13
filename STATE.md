# STATE.md — Fichero

## Current Focus

**Milestone:** 0.0.3 (Migration + Operational Hardening) — COMPLETE ✅

**Status:** All 0.0.3 issues completed
- #371: ✅ MCP adapters for canonical knowledge APIs (branch pushed)
- #370: ✅ Multilingual baseline (branch pushed)
- #369: ✅ Reindex/repair jobs (branch pushed)
- #368: ✅ Knowledge migration/backfill (branch pushed)

## Recently Completed (Session 2026-04-12)

### Issue #371 - Thin MCP Adapters for Canonical Knowledge APIs
**Commit:** `408b6f53`

**Implementation:**
- Verified existing MCP tools for knowledge APIs are working
- Added comprehensive MCP knowledge adapter tests (14 tests)

**Adapters Verified:**
- `POST /mcp/tools/knowledge/entities/upsert` - Entity create/update
- `POST /mcp/tools/knowledge/claims/create` - Claim creation
- `GET /mcp/tools/knowledge/entities/{id}` - Entity retrieval
- `GET /mcp/tools/knowledge/claims/{id}` - Claim retrieval
- `DELETE /mcp/tools/knowledge/entities/{id}` - Entity soft-delete
- `DELETE /mcp/tools/knowledge/claims/{id}` - Claim soft-delete
- `GET /mcp/tools/knowledge/entities` - Entity listing with filters
- `GET /mcp/tools/knowledge/claims` - Claim listing with filters

**Test Coverage:**
- Entity upsert/create/update operations
- Claim creation with single and multiple sources
- 1:1 canonical API mapping verification
- Error handling and validation
- Endpoint coverage verification

## 0.0.3 Milestone — COMPLETE

All issues implemented:
- ✅ #368: Knowledge migration/backfill
- ✅ #369: Reindex/repair jobs and metrics recomputation
- ✅ #370: Multilingual baseline for claims/entities
- ✅ #371: Thin MCP adapters for canonical knowledge APIs

## Next Session — Start Here

### 1. Review and Merge 0.0.3 PRs

**Branches ready for PR review:**
- `feature/issue-368` — Knowledge migration/backfill
- `feature/issue-369` — Reindex/repair jobs
- `feature/issue-370` — Multilingual baseline
- `feature/issue-371` — MCP adapters

### 2. Start 0.0.4 Milestone

**Milestone 0.0.4 (Semantic UX + Trust Workflow):**
- Issue #372: Claim review queue UI with curation workflow
- Issue #373: Contradiction triage UI with side-by-side provenance
- Issue #374: Search explanation and metrics visibility panel
- Issue #375: Interpretations workspace v1 linked to claims

**Milestone 0.0.5 (Graph Exploration):**
- Issue #376: Integrate derived graph reasoning runtime (NetworkX)
- Issue #377: Optional latent inference track (PyKEEN)

### 3. Review GitHub Project Board

- **Project:** https://github.com/users/dtubb/projects/5
- **Milestones:** https://github.com/dtubb/fichero/milestones
- **Issues:** https://github.com/dtubb/fichero/issues

---
*Last updated: 2026-04-12* — 0.0.3 milestone complete, ready for PR review
