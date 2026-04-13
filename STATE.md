# STATE.md — Fichero

## Current Focus

**Milestone:** 0.0.3 (Migration + Operational Hardening)

**Status:** Issue #368 complete ✅ - Knowledge migration/backfill tooling implemented
- Branch: `feature/issue-368` pushed, ready for PR
- All tests passing (16/16)
- ruff linting clean

## Recently Completed

### Issue #368 - Knowledge Migration/Backfill Tooling
**Commit:** `94b0af03`

**Implementation:**
- CLI script: `fichero-api/scripts/run_migration.py`
- FastAPI routes: `/api/migrations/*`
- Unit tests: `fichero-api/tests/unit/test_migrations.py` (16 tests)

**Features Delivered:**
- Dry-run mode for safe migration previews
- Rollback support via mutation logs
- Data integrity checks for counts and orphaned records
- Batch processing with progress callbacks
- Full audit trail for all operations

**API Endpoints:**
- `GET /api/migrations` - list available migrations
- `POST /api/migrations/run` - run migration with dry-run support
- `POST /api/migrations/validate` - validate migration safety
- `GET /api/migrations/status/{run_id}` - check migration status
- `POST /api/migrations/rollback` - rollback a migration
- `GET /api/migrations/integrity-check` - data integrity checks

## 0.0.3 Milestone Status

**Open Issues:** #371, #370, #369, #368
- #371: Thin MCP adapters for canonical knowledge APIs
- #370: Multilingual baseline for claims/entities
- #369: Reindex/repair jobs and metrics recomputation
- #368: ✅ Complete - Knowledge migration/backfill tooling

## Next Session — Start Here

### 1. Complete 0.0.3 Milestone

**Issue #369** - Reindex/repair jobs:
- Build reindexing workers for search index consistency
- Implement metrics recomputation for knowledge graph
- Add background job scheduling
- Create admin endpoints for job monitoring

### 2. Review GitHub Project Board

- **Project:** https://github.com/users/dtubb/projects/5
- **Milestones:** https://github.com/dtubb/fichero/milestones
- **Issues:** https://github.com/dtubb/fichero/issues

### 3. Other 0.0.3 Priorities

**Issue #370** - Multilingual baseline:
- Cross-language entity linking
- Language detection for claims
- Translation utilities for search

**Issue #371** - MCP adapters:
- Thin adapter layer for knowledge APIs
- MCP tool definitions for claims/entities

---
*Last updated: 2026-04-12* - Issue #368 complete, branch ready for PR
