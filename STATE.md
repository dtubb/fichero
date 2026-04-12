# STATE.md — Fichero

## Current Focus

**Milestone:** 0.0.3 (Migration + Operational Hardening)

**Status:** Issue #370 complete ✅ - Multilingual baseline for claims/entities
- Branch: `feature/issue-370` pushed to GitHub, ready for PR
- 20 unit tests added, all passing
- ruff linting clean

## Recently Completed (Session 2026-04-12)

### Issue #370 - Multilingual Baseline for Claims/Entities
**Commit:** `71f94f09`

**Implementation:**
- Registered multilingual routes in main.py _CORE_ROUTE_SPECS
- Added comprehensive API-level tests (20 tests)

**Features Delivered:**
- Language detection for 20+ languages (EN, JA, ZH, KO, etc.)
- Language persistence verified in KnowledgeEntity and KnowledgeClaim
- Entity alias/transliteration mapping supported
- Cross-language retrieval test fixtures
- Text normalization for multiple languages
- Stemming support for English

**API Endpoints (already existed, now registered in core):**
- `POST /api/multilingual/detect` - Detect language of text
- `POST /api/multilingual/transliterate` - Get transliteration variants
- `POST /api/multilingual/entities/search` - Cross-language entity search
- `GET /api/multilingual/claims` - Filter claims by language
- `GET /api/multilingual/entities` - Filter entities by language
- `POST /api/multilingual/normalize` - Normalize text for language

## 0.0.3 Milestone Status

**Open Issues:** #371
- #371: Thin MCP adapters for canonical knowledge APIs
- #370: ✅ Complete - Multilingual baseline
- #369: ✅ Complete - Reindex/repair jobs (branch pushed)
- #368: ✅ Complete - Knowledge migration/backfill (branch pushed)

## 0.0.2 Completion Note

**Issue #364** is CLOSED on GitHub - 0.0.2 milestone is complete.
- #364: Canonical FastAPI knowledge write paths - CLOSED

## Next Session — Start Here

### 1. Complete 0.0.3 Milestone

**Issue #371** - Thin MCP adapters:
- Create adapter layer for knowledge APIs
- Implement MCP tool definitions for claims/entities
- Register tools with MCP server
- Add tests for MCP tool invocations

### 2. Review GitHub Project Board

- **Project:** https://github.com/users/dtubb/projects/5
- **Milestones:** https://github.com/dtubb/fichero/milestones
- **Issues:** https://github.com/dtubb/fichero/issues

### 3. Post-0.0.3 Priorities

**Milestone 0.0.4 - Semantic UX + Trust Workflow:**
- Claim review queue UI
- Contradiction triage UX
- Search explanation panel
- Interpretations workspace

---
*Last updated: 2026-04-12* - Issue #370 complete, branch ready for PR
