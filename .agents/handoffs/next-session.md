# Session Handoff — Next AI Instructions

**Date:** 2026-04-10  
**From:** Previous session (Code Quality Review Plan creation)  
**Branch:** main (current checkout)

## Current State

### Completed This Session
✅ Created comprehensive code quality review plan  
✅ Created 7 GitHub tracking issues (#410-#416) for 0.0.2 security PRs  
✅ Documented review phases in `.agents/loops/CODE_REVIEW_PLAN.md`

### Security PRs Awaiting Review
- **#399** — SSRF protection implementation (fixes)
- **#409** — HIGH severity CORS/MCP fixes (fixes)
- **#401, #403, #405, #407** — Audit documentation (docs only)

### GitHub Issues for Automated Loop
| Issue | Phase | Description |
|-------|-------|-------------|
| #416 | Master | [TRACKING] Code Quality Review — All Security PRs |
| #410 | Phase 0 | Pre-flight Checklist |
| #411 | Phase 1 | Automated Quality Gates (ruff, tests) |
| #412 | Phase 2 | Architecture Compliance |
| #413 | Phase 3-4 | Code Style & Security Hygiene |
| #414 | Phase 5-6 | Error Handling & Documentation |
| #415 | Phase 7-8 | Test Coverage & Integration |

## What to Do Next

### If Running Automated Code Review Loop:

```bash
# Option 1: Run all phases on all security PRs
cd "$(git rev-parse --show-toplevel)"
./.agents/loops/run_code_review.sh --all

# Option 2: Run specific phase
./.agents/loops/run_code_review.sh --phase 1 --pr 409

# Option 3: Run specific PR through all phases
./.agents/loops/run_code_review.sh --pr 409
```

### Manual Phase Execution:

For each PR, work through issues #410 → #415 in order:

1. **#410 Phase 0** — Check branch status, no conflicts
2. **#411 Phase 1** — Run ruff, run tests, verify pass
3. **#412 Phase 2** — Verify FastAPI patterns, OpenAPI sync
4. **#413 Phase 3-4** — Check style, security hygiene
5. **#414 Phase 5-6** — Error handling, documentation
6. **#415 Phase 7-8** — Test coverage, integration

### Update Issue #416:

After each phase, update the master tracking issue #416 with results.

### Merge Decision Matrix:

From #416 — all these must be true to recommend merge:
- [ ] Phase 0: Pre-flight checks PASS
- [ ] Phase 1: Automated quality PASS  
- [ ] Phase 2: Architecture compliance PASS
- [ ] Phase 4: Security hygiene PASS
- [ ] Phase 7: Test coverage PASS

## Worktrees Available

Use the current checkout only. The retired `~/code/fichero-<version>` pattern no longer applies.

## Critical Files

- Review plan: `.agents/loops/CODE_REVIEW_PLAN.md`
- Master tracking: GitHub issue #416
- First phase: GitHub issue #410

## Daniel's Requirement

**Run the code review automation.** Either:
1. Create the `run_code_review.sh` script if it doesn't exist, OR
2. Run phases manually by updating issues #410-#415

**Goal:** Produce a merge recommendation for all 6 security PRs.
