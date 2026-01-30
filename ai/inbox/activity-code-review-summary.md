# Activity View Code Review Summary

**Date:** 2026-01-25
**Reviewer:** Claude Code

---

## Overview

Systematic code review of all Activity-related code across frontend (Swift) and backend (Python), checking against project development standards.

---

## Files Reviewed

| File | Lines | Status |
|------|-------|--------|
| `src/fichero/workflows/activity.py` | 1025 | Acceptable |
| `src/fichero/api/routes/activity.py` | 373 | Good |
| `Fichero/Services/ActivityService.swift` | 606 | Needs work |
| `Fichero/Services/WorkflowStreamService.swift` | 591 | Needs work |
| `Fichero/Services/WorkflowExecutionObserver.swift` | 403 | Good |
| `Fichero/Views/Sidebar/Modes/ActivitySidebarContent.swift` | 582 | Needs split |
| `Fichero/Views/Activity/ActivityDetailView.swift` | 1750 | **Critical** |
| `Fichero/Models/SidebarItem.swift` | 477 | Minor issues |

---

## Critical Issues

### 1. ActivityDetailView.swift is 4x too large (1750 lines)

**Problem:** Contains 9 view structs in one file

**Fix Required:** Split into separate files:
- `ActivityDetailView.swift` - Main view router
- `ActivityOverviewView.swift`
- `ActivityConsoleView.swift`
- `ActivityProgressView.swift`
- `ActivityErrorsView.swift`
- `ActivityGraphView.swift`
- `ActivityLogView.swift`
- `ActivityCodeView.swift`
- `ActivityDiagramView.swift`

### 2. Not using Swift OpenAPI Generator

**Problem:** `ActivityService.swift` uses manual `APIClient` calls instead of generated type-safe client

**Current (fragile):**
```swift
let response: [ActivityItem] = try await apiClient.get("/activity\(queryString)")
```

**Should be:**
```swift
let response = try await client.listActivitiesApiActivityGet(.init(...))
```

**Fix Required:** Either:
1. Add activity endpoints to OpenAPI schema and regenerate
2. Migrate ActivityService to use generated client

---

## Backend Issues

### activity.py (1025 lines)

1. **Line 677-678:** Fire-and-forget async tasks without error tracking
   ```python
   asyncio.create_task(self._save_activity(activity))  # Could silently fail
   ```

2. **Line 977:** Unconventional import pattern
   ```python
   _tracker_lock = __import__('threading').Lock()  # Should import at top
   ```

3. **Line 663:** Inconsistent datetime usage - uses `datetime.now()` but elsewhere uses `datetime.utcnow()`

### activity routes (373 lines)

1. **Fixed:** Metadata now converts values to strings (line 57-58)

2. **Lines 230-238:** Inconsistent error handling - silently ignores invalid types in `/stream` but raises HTTPException in `/`

---

## Frontend Issues (Positive Findings)

### Concurrency Patterns - All Correct

- ✅ All `@MainActor` annotations properly placed
- ✅ `Task.isCancelled` checked in all `.task {}` blocks
- ✅ No `DispatchQueue.main.async` usage (uses Swift concurrency)
- ✅ No `NotificationCenter` usage
- ✅ `@ViewBuilder` used on computed view properties

### State Management - Correct

- ✅ `@State` for local view state
- ✅ `@Environment` for dependency injection
- ✅ Services not created in view bodies

### Logging - Correct

- ✅ Uses OSLog throughout (no NSLog or print)

---

## File Size Issues

| File | Lines | Limit | Over By |
|------|-------|-------|---------|
| ActivityDetailView.swift | 1750 | 400 | 1350 (337%) |
| activity.py | 1025 | 600 | 425 (71%) |
| ActivityService.swift | 606 | 400 | 206 (51%) |
| WorkflowStreamService.swift | 591 | 400 | 191 (48%) |
| ActivitySidebarContent.swift | 582 | 400 | 182 (45%) |
| SidebarItem.swift | 477 | 400 | 77 (19%) |
| WorkflowExecutionObserver.swift | 403 | 400 | 3 (1%) |

---

## Fixes Applied This Session

1. ✅ Fixed metadata decoding error - added `AnyValueAsString` wrapper in Swift
2. ✅ Fixed backend to convert metadata values to strings
3. ✅ Fixed `ActivityServiceGenerated` → `ActivityService` reference
4. ✅ Fixed `isLive` always true - now checks `execution.isRunning`
5. ✅ Fixed status always `.running` - now maps from actual execution status
6. ✅ Added cleanup for completed executions (2-second delay)
7. ✅ Added auto-refresh of history when workflows complete
8. ✅ Added SSE "log" event streaming for live execution logs

---

## Recommended Follow-up Tasks

### Priority 1 (Do Soon)
1. Split `ActivityDetailView.swift` into 9 separate files
2. Add activity endpoints to OpenAPI schema
3. Migrate ActivityService to use generated client

### Priority 2 (Can Wait)
4. Split `ActivitySidebarContent.swift` into multiple files
5. Extract activity types from `SidebarItem.swift` to separate file
6. Fix fire-and-forget tasks in `activity.py`

### Priority 3 (Nice to Have)
7. Add consistent datetime handling in backend (use UTC everywhere)
8. Fix late imports in Python files
9. Add tests for activity streaming

---

## Standards Compliance Summary

| Standard | Backend | Frontend |
|----------|---------|----------|
| Type hints/annotations | ✅ | ✅ |
| Async/await patterns | ✅ | ✅ |
| Error handling | ⚠️ | ✅ |
| Logging (structured) | ✅ | ✅ |
| File size limits | ⚠️ | ❌ |
| Documentation | ✅ | ⚠️ |
| No NotificationCenter | N/A | ✅ |
| No DispatchQueue | N/A | ✅ |
| Task cancellation | N/A | ✅ |
| @ViewBuilder usage | N/A | ✅ |
| @MainActor usage | N/A | ✅ |
| OpenAPI client | N/A | ❌ |
