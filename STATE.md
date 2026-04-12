# STATE.md — Fichero

## Current Focus

**Milestone:** 0.0.2 (Search + Semantic Foundation) - PENDING PR REVIEW

**Status:** 16/17 0.0.2 PRs merged ✅, 1 awaiting review ⏳
- All feature/backend PRs (#400-449) merged to 0.0.2 and main
- Issue #364: PR #455 ready for review — canonical FastAPI knowledge mutation paths

## Open Pull Requests

| PR | Branch | Status | Description |
|---|---|---|---|
| #455 | feature/issue-364 | **Ready for Review** | Canonical knowledge routes (entities, claims, claim-links) |
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

### 1. PR Review and Merge (with Daniel)

**PR #455**: Canonical FastAPI knowledge write path
- Branch: `feature/issue-364`
- URL: https://github.com/dtubb/fichero/pull/455
- Status: Ready for review, 3 commits ahead of main
- Changes:
  - entities.py: Entity CRUD, aliasing, resolution
  - claims.py: Claim CRUD, referential integrity
  - claim_links.py: Bidirectional claim linking
  - Contract tests for all routes

### 2. Complete 0.0.2 Milestone

Once PR #455 merged:
- 0.0.2 milestone complete (17/17 issues resolved)
- Close issue #364
- Update GitHub milestone

### 3. Review GitHub Project Board

- **Project**: https://github.com/users/dtubb/projects/5
- **Milestones**: https://github.com/dtubb/fichero/milestones
- **Issues**: https://github.com/dtubb/fichero/issues
