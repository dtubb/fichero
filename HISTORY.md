
## 2026-04-10 — Autonomous Loop Session

- **#390 Phase 4 Agent Research (Layer 0)**: Implemented complete backend for systematic discovery
  - `research_models.py`: Project, Plan, Task, Step, Source, Note, ChecklistItem models
  - `research_agents.py`: 793-line FastAPI route module with full CRUD
  - `test_research_agents_api.py`: 12 comprehensive unit tests (all passing)
  - Sandboxed tool placeholders: web-search, browser-navigate, document-fetch
  - All writes go to Fichero database (no filesystem escape)
  - PR #397 created: https://github.com/dtubb/fichero/pull/397

## 2026-04-07 — Autonomous Loop Session

- **#387 Phase 1 assessment**: Assessed 0.0.2 phase implementation status across all 5 phases
  - Phase 1 (#387): Backend done, PyKEEN route needs wiring + pip install
  - Phase 2 (#388): Backend + SwiftUI done, fully built
  - Phase 3 (#389): Backend done, SwiftUI Mind Palace views missing
  - Phase 4 (#390): Backend done, SwiftUI Research views missing
  - Phase 5 (#391): Not started — MCP adapters + integration
  - 0.0.1 regression bugs (#382-#386) are NOT blockers for 0.0.2 work
- Added `pykeen` to `pyproject.toml` (Briefcase `requires` + `dependencies`)
- Removed stale `BLOCK.md` and `CONTINUE.md`

## 2026-04-03 — Autonomous Loop Session

- **#367**: Reversible entity merge/split + claim curation transitions
  - `POST /entities/merge`: absorbs entities into survivor with alias preservation
  - `POST /entities/split`: distributes aliases across primary + split-off entities
  - `POST /entities/audit/{id}/undo`: reverses any merge/split via audit chain
  - `GET /entities/audit`: lists audit records filtered by entity_id
  - `EntityMergeAudit` model: immutable operation log with reversal linkage
  - `KnowledgeEntity.merged_into_id` used for soft-delete redirect
  - `curated_only=true` convenience filter on GET /claims and GET /claims/filtered

- **#362**: General mutation log with undo/rollback for KG entities
  - `MutationLog` model: before/after state snapshots with `run_id` for AI batch grouping
  - `POST /knowledge-mutations/undo`: undo single mutation or rollback full AI run
  - `GET /knowledge-mutations`: list with filters (entity_type, entity_id, run_id, created_by)
  - `POST|PATCH /claims` now log mutations automatically with run_id/agent_id query params
  - `_log_mutation` helper for wiring mutations into any KG entity

- **#363**: Library snapshots and restore
  - `LibrarySnapshot` model with paths, sizes, retention policy
  - `snapshot_library()`: exports DuckDB tables to Parquet + copies LanceDB vectors
  - `POST /api/storage/snapshots`, `GET /api/storage/snapshots`, `GET /api/storage/snapshots/{id}`
  - `POST /api/storage/snapshots/{id}/restore`, `DELETE /api/storage/snapshots/{id}`, `PATCH /api/storage/snapshots/{id}/pin`
  - Pinned snapshots exempt from auto-retention; auto-expire via `auto_expire_days`

- **#361**: XMP sidecar support for images
  - `xmp_loader.py`: parse XMP sidecars with libxmp + regex fallback
  - Standard namespaces: dc, xmp, photoshop, Iptc4xmpCore, Iptc4xmpExt
  - Custom `ficher:` namespace for entity links, claim links, archive IDs, IIIF manifests
  - `apply_xmp_to_document()` merges into `Document.metadata`
  - Wired into `ingest.py` `_extract_image_metadata()` — runs during normal image ingestion

- **#395**: Fixed 8 SwiftLint violations across 4 SwiftUI view files:
  - Extracted 13 component files from 4 long views
  - Result: 0 violations across 341 Swift files

**All 900 pytest pass. ruff clean. SwiftLint clean.**

## 2026-04-02 — Autonomous Loop Session

- #381: Created `docs/agent-workflow/0.0.2-gate-map.md` — gate map for Layers 0-6
- #365: SourceMetadata model + citation validation (DOI, ISBN-13/10, ISSN, arXiv) + ProvenanceInfo + 36 unit tests
- #366: GET /entities/alias-map + GET /claims?entity=X filter + 2 unit tests
- #392: Added 4 MCP tools — generate/apply predictions, circle navigation
- OpenAPI sync: 46 endpoints across 16 resources — regenerated Swift client
- SwiftLint: auto-fixed 88 sorted_imports violations (101 files), 6 identifier_name violations
- rules.json: agent rules configuration committed
- Phase 1 SwiftUI: ClaimInspectorView, OntologyBrowserView, EpistemologyGraphView, PredictionReviewView

## 2026-04-10 — Session Summary

- **Session Start Assessment**: Reviewed #388 (Hermeneutics Phase 2) state — work was stopped at user request
- **Git State Observation**: codex/0.0.2-planning branch, skills relocated to plugins, .venv untracked
- **Planning branch issue**: Active work should happen on main or feature branch, not planning branch

## 2026-04-10 — #390 0.0.2 Phase 4: Agent Research (Layer 0)

- PR: https://github.com/dtubb/fichero/pull/397
- Branch: feature/issue-390
- Task completed in session

## 2026-04-10 — Phase 4 Agent Research SSRF Security Audit Complete

- **Issue #398**: Phase 4 (Agent Research) SSRF security review completed
  - Created SECURITY_FINDINGS_398.md with complete vulnerability report
  - Identified CRITICAL: Open redirect SSRF, internal IP blocking gaps
  - Created test_research_ssrf_security.py with 53 security tests
  - 45 tests FAIL (demonstrating current vulnerabilities)
  - Branch: feature/issue-398 pushed to origin
  - Next: Implement IP validation, redirect chain security, resource limits

## 2026-04-10 — Phase 4 SSRF Security Fixes Implemented (#398)

- **SSRF Fixes**: Implemented comprehensive security validation for research tools
  - Added _is_internal_ip() and _is_safe_url() to both files:
    - fichero-api/src/fichero/api/routes/research_agents.py
    - fichero-api/src/fichero/workflows/tools/research.py
  - Validation covers: RFC1918 IPs, loopback, link-local, cloud metadata
  - Case-insensitive scheme checking (http/https only)
  - DNS resolution-time validation
  - Credentials-in-URL blocking
- **Test Results**: 48 of 53 security tests passing (45 previously failing now pass)
- **Accepted Risks**: 5 remaining failures documented (open redirects, query strings)
- **Branch**: feature/issue-398 — pushed, ready for PR review

## 2026-04-10 — Session Complete: PR #399 Created

- **PR Created**: #399 — Security: Implement SSRF protection for Phase 4 research tools
  - Branch: feature/issue-398 → 0.0.2
  - 70 tests passing (22 existing + 48 security tests)
  - 5 accepted risk failures (open redirects, query strings)
  - All linting clean (ruff)
- **Issue #398**: Ready to close after PR review/merge
- **Next**: Daniel reviews PR #399

## 2026-04-10 — Phase 5 Integration Security Audit Complete (#400)

- **Issue #400**: Phase 5 Integration security review completed
  - SECURITY_FINDINGS_400.md with CORS and MCP vulnerabilities
  - test_integration_security.py with 13 tests (4 FAILING)
  - HIGH: CORS wildcard + credentials enabled
  - HIGH: MCP server missing authorization
  - Branch: feature/issue-400 pushed, PR #401 created
- **PRs**: #399 (Phase 4 fixes), #401 (Phase 5 findings) both awaiting review
