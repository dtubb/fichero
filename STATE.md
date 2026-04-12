# STATE.md — Fichero

## Current Focus

**Milestone:** 0.0.3 (Migration + Operational Hardening)

**Status:** Issue #369 complete ✅ - Reindex/repair jobs and metrics recomputation
- Branch: `feature/issue-369` pushed to GitHub, ready for PR
- All tests passing (core functionality)
- ruff linting clean

## Recently Completed (Session 2026-04-12)

### Issue #369 - Reindex/Repair Jobs and Metrics Recomputation Workers
**Commit:** `e5a68f59`

**Implementation:**
- New task types: `VECTOR_REPAIR` and `KG_METRICS`
- Enhanced existing task handlers with idempotent behavior
- Added task system health endpoint at `/api/tasks/health`

**Features Delivered:**
- Jobs recover from interruption (tasks reset to pending on restart)
- Idempotent recomputation behavior
- Admin health endpoints for job status

**Task Types:**
- `REINDEX` - Reindex documents in LanceDB
- `METRICS` - Recompute library document metrics
- `REPAIR` - Repair database inconsistencies (orphaned artifacts, missing embeddings)
- `VECTOR_REPAIR` - Repair LanceDB vector index consistency
- `KG_METRICS` - Recompute knowledge graph metrics (claims, links, entities)

**API Endpoints:**
- `POST /api/tasks/reindex` - Create reindex job
- `POST /api/tasks/metrics` - Create metrics job
- `POST /api/tasks/repair` - Create repair job
- `POST /api/tasks/vector-repair` - Create vector repair job
- `POST /api/tasks/kg-metrics` - Create KG metrics job
- `GET /api/tasks/health` - Task system health status

## 0.0.3 Milestone Status

**Open Issues:** #371, #370, #369
- #371: Thin MCP adapters for canonical knowledge APIs
- #370: Multilingual baseline for claims/entities and cross-language retrieval
- #369: ✅ Complete - Reindex/repair jobs and metrics recomputation

## 0.0.2 Completion Blocker

**Issue #364** is CLOSED on GitHub but STATE.md was not updated:
- #364: Canonical FastAPI knowledge write paths - CLOSED
- **Action needed:** Close 0.0.2 milestone on GitHub

## Next Session — Start Here

### 1. Complete 0.0.3 Milestone

**Issue #370** - Multilingual baseline:
- Add language detection for claims
- Implement cross-language entity linking
- Add translation utilities for search

### 2. Review GitHub Project Board

- **Project:** https://github.com/users/dtubb/projects/5
- **Milestones:** https://github.com/dtubb/fichero/milestones
- **Issues:** https://github.com/dtubb/fichero/issues

### 3. 0.0.3 Final Issue

**Issue #371** - Thin MCP adapters:
- Create adapter layer for knowledge APIs
- Implement MCP tool definitions for claims/entities
- Register tools with MCP server

---
*Last updated: 2026-04-12* - Issue #369 complete, branch ready for PR
