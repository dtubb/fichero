# Implementation Checklist for TODO-049

## Task: Fix API pytest issues and ensure background tests run properly

### Planning Phase
- [x] Review task requirements and context
- [x] Examine existing test file (test_api_providers.py)
- [x] Examine provider implementation (providers.py)
- [x] Examine API routes (routes/providers.py)
- [x] Identify the main issues:
  1. Provider naming inconsistency: tests use "apple_vision" but implementation uses "apple"
  2. Database lock: tests expect API to be running but it's not
  3. Timeout issues in tests

### Implementation Phase

#### Step 1: Fix provider naming inconsistency
- [x] Update tests to use "apple" instead of "apple_vision" to match actual implementation
- [x] Update test expectations for provider types
- [x] Ensure all references to "apple_vision" are changed to "apple"

#### Step 2: Resolve database lock issue
- [x] Modify test setup to handle cases where API is not running
- [x] Add option to run tests without requiring running API server
- [x] Replace httpx with FastAPI TestClient to avoid needing running server

#### Step 3: Fix timeout issues
- [x] Review timeout values in tests
- [x] Remove timeout parameters from TestClient calls (not supported)
- [x] Add proper error handling for timeout scenarios

#### Step 4: Ensure all API tests pass consistently
- [x] Run tests to verify fixes
- [x] Debug any remaining issues
- [x] Ensure consistent test results - all 20 tests now passing

### Testing Phase
- [ ] Run pytest on test_api_providers.py
- [ ] Verify all tests pass
- [ ] Check for any regressions
- [ ] Test edge cases

### Review Phase
- [ ] Self-review code changes
- [ ] Verify checklist completion
- [ ] Document decisions and changes
- [ ] Create summary of work done

### Finalization
- [ ] Update TODO.md to mark task as completed
- [ ] Commit changes with appropriate message
- [ ] Clean up any temporary files