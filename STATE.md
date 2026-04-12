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

**Status:** 16/17 0.0.2 PRs merged ✅
- All feature/backend PRs (#400-449) merged to 0.0.2 and main
- Issue #364 still open: canonical FastAPI knowledge mutation paths

## Open Pull Requests

| PR | Branch | Status | Description |
|---|---|---|---|
| #396 | feature/313-connection-ui-restored | Open | 0.0.1 Library UI fixes |
| #352 | feature/issue-340 | Open | Prompt preview panel |
| #351 | feature/issue-344-thinking-mode-selector | Open | Thinking mode selector |
| #350 | feature/issue-346-settings-defaults-ui | Open | Settings Defaults UI |
| #347 | feature/issue-345-unify-vision-provider | Open | Unify vision engine |
| #338 | feature/issue-330 | Open | Icon view default scale |
| #337 | feature/issue-327 | Open | Folder contents grid |
| #335 | feature/issue-322 | Open | Center image zoom |
| #334 | feature/issue-313 | Open | Connection error banner |
| #321 | feature/issue-317 | Open | Document viewer fixes |

**Note:** All 0.0.2 milestone backend PRs (#400-449) are merged. The 3 open PRs above are pre-existing 0.0.1 UI issues.

## 0.0.2 Milestone Status

**Complete:** All 16 PRs merged
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

**Outstanding Issue:** #364
- Title: "0.0.2: Canonical FastAPI knowledge write path and route surface"
- Status: OPEN
- Task: Implement canonical mutation paths for sources, entities, claims, and claim-links

## Blocked

- (none — all 0.0.2 PRs merged, 1 issue remaining)

## Next Session — Start Here

### 1. Complete 0.0.2 Milestone

**Issue #364** - Canonical FastAPI knowledge write path:
- Review existing routes: `knowledge_graph.py`, `sources.py`, `entities.py`, `claims.py`, `claim_links.py`
- Implement service-layer mutation methods with referential integrity
- Register dedicated knowledge routes in API tier
- Add contract tests for SwiftUI + MCP clients

### 2. Review GitHub Project Board

- **Project**: https://github.com/users/dtubb/projects/5
- **Milestones**: https://github.com/dtubb/fichero/milestones
- **Issues**: https://github.com/dtubb/fichero/issues

### 3. Post-0.0.2 Priorities

**Option A: Re-enable Disabled Features (0.0.1 regressions)**
- #432-434: Re-enable Library/Search splits, Workflow Editor modes, Search/Map/Table views
- #281-386: Various legacy UI issues

**Option B: 0.1.0 Epic**
- #427: Advanced Graph Exploration Views (SwiftUI)
- #428: Optional Embedded IFFY/IIIF Server Mode
- #379-380: Human-in-the-loop orchestration policy

**Option C: 0.0.3/0.0.4/0.0.5 Milestones**
- Various planned backend and UX improvements

### 4. Security PRs Completed

- #400-408: Security fixes merged to 0.0.2 (Daniel's review pending)

## Next Session — Start Here

### 1. Investigate Sources Route Registration (Issue #364)

**Status:** Sources routes implemented but not appearing in running API

**Check First:**
```bash
cd /Users/danieltubb/code/fichero-0.0.2
./scripts/start-backend.sh
curl http://127.0.0.1:8765/api/sources
curl -H "X-Fichero-Library-Path: /Users/danieltubb/Dropbox/fichero-library" http://127.0.0.1:8765/api/sources
curl http://127.0.0.1:8765/openapi.json | grep -A3 '"/api/sources"'
```

**If routes still 404:**
- Debug module import ordering in main.py
- Verify sources.py is being loaded during API startup
- Check if _CORE_ROUTE_SPECS is being properly constructed

### 2. Complete Sources Contract Tests

Once routes are confirmed working:
- Verify POST /api/sources creates Document with document_type="source"
- Verify GET /api/sources lists all sources
- Verify GET/PUT/DELETE work with source id
- Add referential integrity tests for claims linking to sources

### 3. Review GitHub Project Board

- **Project**: https://github.com/users/dtubb/projects/5
- **Milestones**: https://github.com/dtubb/fichero/milestones
- **Issues**: https://github.com/dtubb/fichero/issues

---
*Last updated: 2026-04-12* (Sources routes implemented - runtime registration debugging needed)
