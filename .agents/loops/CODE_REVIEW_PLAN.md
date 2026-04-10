# Automated Code Quality Review Loop — Fichero

**Version:** 0.2.0  
**Last Updated:** 2026-04-10  
**Purpose:** Systematic code quality review before any PR merge  
**Tracking Issue:** #416 (Master tracking for 0.0.2 security PRs)

## Quick Start — Run Full Review

```bash
# Automated execution
./.agents/loops/run_code_review.sh --all

# Or specific PR
./.agents/loops/run_code_review.sh 409
```

## GitHub Issues (0.0.2 Milestone)

| Phase | Issue | Status | Blocker? |
|-------|-------|--------|----------|
| Phase 0 | #410 | ⬜ | YES |
| Phase 1 | #411 | ⬜ | YES |
| Phase 2 | #412 | ⬜ | YES |
| Phases 3-4 | #413 | ⬜ | YES (P4) |
| Phases 5-6 | #414 | ⬜ | NO |
| Phases 7-8 | #415 | ⬜ | YES (P7) |
| **Master** | #416 | ⬜ | — |

---

## Overview

This plan provides a step-by-step checklist for comprehensive code quality review. Run this as an automatic loop on every PR before requesting human review.

---

## Phase 0: Pre-Flight Checklist

**Goal:** Ensure the branch is in a reviewable state

```bash
# P0.1: Branch status check
gh pr view <PR_NUMBER> --json mergeStateStatus,mergeable,headRefName,baseRefName

# PASS if: mergeStateStatus is "CLEAN" or "HAS_HOOKS"
# FAIL if: "BEHIND" (needs rebase), "BLOCKED" (conflicts), "DIRTY"
```

**Checks:**
- [ ] PR targets correct base branch (0.0.2 for security fixes)
- [ ] No merge conflicts with base branch
- [ ] Branch is not behind base by >10 commits (rebase if so)
- [ ] PR has descriptive title following conventional commits
- [ ] PR description explains WHAT and WHY

---

## Phase 1: Automated Quality Gates

**Goal:** Verify code passes all automated tools

### 1.1 Python Code Quality (Fichero API)

```bash
cd <PR_WORKTREE>

# P1.1.1: Ruff linting
PYTHONPATH=fichero-api/src .venv/bin/ruff check fichero-api/src/
PYTHONPATH=fichero-api/src .venv/bin/ruff check fichero-api/tests/

# PASS if: "All checks passed!"
# FAIL if: Any violations

# P1.1.2: Ruff formatting check (no changes needed)
PYTHONPATH=fichero-api/src .venv/bin/ruff format --check fichero-api/src/

# PASS if: No files would be reformatted
# FAIL if: Files need formatting
```

**Checks:**
- [ ] `ruff check fichero-api/src/` passes
- [ ] `ruff check fichero-api/tests/` passes
- [ ] `ruff format --check` passes (no formatting changes needed)

### 1.2 Swift Code Quality (Fichero SwiftUI)

```bash
# P1.2.1: SwiftLint (if Swift files changed)
swiftlint lint fichero-swiftui/fichero-swiftui/

# PASS if: No violations or warnings
# FAIL if: Any violations
```

**Checks:**
- [ ] SwiftLint passes (if Swift files in PR)
- [ ] No Swift files exceed 1,000 lines
- [ ] No type bodies exceed 250 lines
- [ ] No functions exceed 50 lines

### 1.3 Test Execution

```bash
# P1.3.1: Python unit tests
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ \
  --ignore=fichero-api/tests/unit/_archived -v \
  --tb=short 2>&1 | tail -30

# PASS if: All tests pass or only expected failures
# FAIL if: Unexpected test failures

# P1.3.2: Security tests (if security PR)
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/test_*_security.py -v

# PASS if: 80%+ tests passing (some accepted risk OK for security)
```

**Checks:**
- [ ] Python unit tests pass
- [ ] Security tests pass (if applicable)
- [ ] No test coverage regressions

---

## Phase 2: Architecture Compliance Review

**Goal:** Verify code follows project architecture patterns

### 2.1 FastAPI Route Standards

**For any new/modified routes in `api/routes/':**

```
CHECKLIST:
□ Uses APIRouter with proper prefix
□ All endpoints have type hints
□ Uses Pydantic models for request/response
□ Proper HTTPException with status codes
□ Async functions where I/O occurs
□ Database access via Depends(get_library_database)
□ No direct DuckDB/LanceDB queries
```

**Example verification:**
```python
# ✓ GOOD: Follows patterns
@router.post("/items", response_model=ItemResponse)
async def create_item(
    request: ItemRequest,
    db: Database = Depends(get_library_database),
) -> ItemResponse:
    """Create a new item."""
    try:
        item = await db.create(request.data)
        return ItemResponse.from_model(item)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

### 2.2 Pydantic Model Standards

**For any new/modified models:**

```
CHECKLIST:
□ Uses Pydantic v2 (BaseModel, Field)
□ Has docstrings for complex models
□ Uses Field() for metadata, not default values
□ Proper type hints (str | None, not Optional[str])
□ Field validators for complex validation
□ No circular imports
```

### 2.3 Database Access Patterns

**Verify:**

```
CHECKLIST:
□ All DB operations go through db.py
□ Uses Database class, not raw SQL
□ Proper error handling for DB errors
□ Connection management (no leaks)
```

### 2.4 OpenAPI Schema Sync (CRITICAL)

**If any API routes changed:**

```bash
# P2.4.1: Check if OpenAPI needs regeneration
./fichero-api/scripts/sync_openapi_schema.sh

# P2.4.2: Check git status for generated files
git status --porcelain fichero-api-client/
git status --porcelain fichero-swiftui/fichero-swiftui/Sources/Generated/

# PASS if: No changes OR changes committed
# FAIL if: Uncommitted generated file changes
```

**Checks:**
- [ ] If routes changed, OpenAPI schema regenerated
- [ ] Swift generated files in sync
- [ ] No manual edits to *Generated.swift files

---

## Phase 3: Code Style Review

**Goal:** Verify conformance to style guidelines

### 3.1 Python Style

**Check for:**

```
□ Black-compatible formatting (4 spaces, 88 char line length)
□ Imports sorted (stdlib, third-party, local)
□ Type annotations on all public functions
□ Trailing commas in multi-line collections
□ No bare except: clauses
□ F-strings for string formatting (not % or .format())
□ Docstrings for complex functions (Google style)
□ Constants in UPPER_CASE at module level
```

### 3.2 Naming Conventions

```
□ Modules: lowercase_with_underscores.py
□ Classes: PascalCase
□ Functions/variables: lowercase_with_underscores
□ Constants: UPPER_CASE_WITH_UNDERSCORES
□ Private methods: _leading_underscore
□ Type variables: PascalCase or _T suffix
```

---

## Phase 4: Security Hygiene Review

**Goal:** Catch security anti-patterns

```
CHECKLIST:
□ No hardcoded passwords/API keys in source
□ No debug=True in production code paths
□ Input validation on all user inputs (SQL injection, XSS)
□ Proper authorization checks (403 vs 401 distinction)
□ No eval() or exec() with user input
□ No debug endpoints in production
□ Error messages don't leak sensitive info
□ Environment variables for secrets (not hardcoded)
```

**Special for Security PRs:**
```
□ Tests demonstrate vulnerability and fix
□ No accepted risk without documentation
□ Security findings documented in SECURITY_FINDINGS_*.md
□ CVSS scores documented for HIGH/CRITICAL
```

---

## Phase 5: Error Handling & Robustness

**Goal:** Verify proper error handling

```
CHECKLIST:
□ All async functions have try/catch where needed
□ HTTP exceptions return proper status codes (400, 404, 500)
□ Database errors caught and converted to HTTPException
□ No silent failures (at minimum log errors)
□ Graceful degradation (not crash on missing data)
□ Input validation returns helpful error messages
□ No bare except: clauses (always catch specific exceptions)
```

---

## Phase 6: Documentation Review

**Goal:** Verify code is properly documented

```
CHECKLIST:
□ Complex functions have docstrings
□ Module-level docstrings for new modules
□ Pydantic models have field descriptions (Field(description="..."))
□ API routes have summary/description
□ Security implications documented
□ README updated if behavior changed
□ CLAUDE.md updated if patterns changed
```

---

## Phase 7: Test Coverage Review

**Goal:** Verify adequate test coverage

### 7.1 Test Quality

```
CHECKLIST:
□ New features have unit tests
□ Bug fixes have regression tests
□ Security fixes have security tests
□ Tests use descriptive names (test_<what>_<condition>)
□ Tests are independent (no shared state)
□ Fixtures/mock data extracted, not duplicated
□ Async tests use pytest-asyncio properly
```

### 7.2 Test Execution

```bash
# Run specific test files for changed code
PYTHONPATH=fichero-api/src .venv/bin/pytest \
  <changed_test_files> -v --tb=short

# Verify no test isolation issues
PYTHONPATH=fichero-api/src .venv/bin/pytest \
  fichero-api/tests/unit/ -x --tb=short
```

---

## Phase 8: Integration & Dependencies

**Goal:** Verify external dependencies work

```
CHECKLIST:
□ No new dependencies without approval
□ Dependencies pinned in requirements.txt or pyproject.toml
□ No version conflicts with existing deps
□ Swift package dependencies resolved (if Swift changes)
□ No unused imports
```

---

## Final Decision Matrix

| Phase | Status | Blocker? |
|-------|--------|----------|
| P0: Pre-flight | ☐ PASS / ☐ FAIL | YES |
| P1: Automated Quality | ☐ PASS / ☐ FAIL | YES |
| P2: Architecture | ☐ PASS / ☐ FAIL | YES |
| P3: Code Style | ☐ PASS / ☐ FAIL | NO (can fix) |
| P4: Security Hygiene | ☐ PASS / ☐ FAIL | YES |
| P5: Error Handling | ☐ PASS / ☐ FAIL | NO |
| P6: Documentation | ☐ PASS / ☐ FAIL | NO |
| P7: Test Coverage | ☐ PASS / ☐ FAIL | YES |
| P8: Integration | ☐ PASS / ☐ FAIL | YES |

**Merge Criteria:**
- **ALL** blocker checks (P0, P1, P2, P4, P7, P8) must pass
- **MOST** non-blocker checks (P3, P5, P6) should pass
- Any failures require human review decision

---

## Review Output Template

```markdown
## Code Quality Review: PR #<NUMBER>

**Branch:** feature/issue-XXX -> 0.0.2  
**Reviewer:** Automated Review Loop  
**Date:** YYYY-MM-DD

### Summary
- Status: ☐ APPROVED / ☐ CHANGES_REQUESTED / ☐ NEEDS_DISCUSSION
- Total Files Changed: <N>
- Python Files: <N>
- Swift Files: <N>
- Test Files: <N>

### Phase Results

| Phase | Status | Notes |
|-------|--------|-------|
| P0: Pre-flight | ☐ PASS / ☐ FAIL | |
| P1: Automated | ☐ PASS / ☐ FAIL | ruff: X issues |
| P2: Architecture | ☐ PASS / ☐ FAIL | |
| P3: Style | ☐ PASS / ☐ FAIL | |
| P4: Security | ☐ PASS / ☐ FAIL | |
| P5: Error Handling | ☐ PASS / ☐ FAIL | |
| P6: Documentation | ☐ PASS / ☐ FAIL | |
| P7: Test Coverage | ☐ PASS / ☐ FAIL | X tests pass |
| P8: Integration | ☐ PASS / ☐ FAIL | |

### Issues Found

**Blockers (must fix):**
1. [ ] Issue description

**Recommendations (should fix):**
1. [ ] Issue description

**Suggestions (nice to have):**
1. [ ] Issue description

### Merge Recommendation
☐ MERGE — All blockers resolved  
☐ MERGE_WITH_NOTES — Minor issues acceptable  
☐ DON'T_MERGE — Blockers require fix  
```

---

## One-Line Execution

For automated runs:

```bash
# Run full review on PR
./.agents/loops/run_code_review.sh <PR_NUMBER>

# Or for specific branch
./.agents/loops/run_code_review.sh --branch feature/issue-408
```
