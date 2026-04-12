# STATE.md — Fichero

## Current Focus

**Milestone:** 0.0.2 (Search + Semantic Foundation) - PENDING PR REVIEW

**Status:** 16/17 0.0.2 PRs merged ✅, 1 awaiting review ⏳
- All feature/backend PRs (#400-449) merged to 0.0.2 and main
- Issue #364: PR #455 ready for review — canonical FastAPI knowledge mutation paths

## Open Pull Requests

### 0.0.2 Milestone (Pending Review)
| PR | Branch | Status | Description |
|---|---|---|---|
| #455 | feature/issue-364 | **Ready for Review** | Canonical knowledge routes (entities, claims, claim-links) |

### 0.0.3 Milestone (Ready for Review)
| PR | Branch | Status | Description |
|---|---|---|---|
| #456 | feature/issue-368 | **Ready for Review** | Knowledge migration/backfill tooling |
| #457 | feature/issue-369 | **Ready for Review** | Reindex/repair jobs and metrics workers |
| #458 | feature/issue-370 | **Ready for Review** | Multilingual baseline for claims/entities |
| #459 | feature/issue-371 | **Ready for Review** | MCP adapters for canonical knowledge APIs |

### 0.0.1 Legacy Issues
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

### 1. PR Review Queue (with Daniel)

**5 PRs Ready for Review:**

**0.0.2 Milestone:**
- **PR #455**: Canonical knowledge routes (Issue #364)
  - URL: https://github.com/dtubb/fichero/pull/455
  - entities.py, claims.py, claim_links.py with CRUD endpoints

**0.0.3 Milestone (all 4 issues):**
- **PR #456**: Knowledge migration/backfill (Issue #368)
  - URL: https://github.com/dtubb/fichero/pull/456
- **PR #457**: Reindex/repair jobs (Issue #369)
  - URL: https://github.com/dtubb/fichero/pull/457
- **PR #458**: Multilingual baseline (Issue #370)
  - URL: https://github.com/dtubb/fichero/pull/458
- **PR #459**: MCP adapters (Issue #371)
  - URL: https://github.com/dtubb/fichero/pull/459

### 2. After PR Merges

- Close issues #364, #368, #369, #370, #371
- Mark 0.0.2 and 0.0.3 milestones complete
- Begin 0.0.4 milestone work

### 3. Review GitHub Project Board

- **Project**: https://github.com/users/dtubb/projects/5
- **Milestones**: https://github.com/dtubb/fichero/milestones
