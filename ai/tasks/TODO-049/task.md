# TODO-049: Fix API pytest issues and ensure background tests run properly

## What to do
Fix database lock issues, provider naming inconsistencies, and timeout problems in API tests

## Steps
- [x] Step 1: Investigate and fix database lock issue preventing tests from running
- [x] Step 2: Resolve provider naming inconsistency (apple_vision vs apple)
- [x] Step 3: Fix timeout issues in API tests
- [x] Step 4: Ensure all API tests pass consistently
- [x] Step 5: Update TODO.md with task details

## Files
- File to change: tests/unit/test_api_providers.py
- File to change: src/fichero/providers.py
- File to change: src/fichero/api/routes/providers.py
- File to change: ai/TODO.md

## Questions for Human
- [ ] Question 1: Should we update tests to use "apple" instead of "apple_vision" or vice versa?
    Answer: Based on code analysis, the provider type is "apple" in providers.py, so tests should be updated to match
- [ ] Question 2: How should we handle the database lock issue in tests?
    Answer: Ensure API server is not running during tests, or use test database

## Answers and Implementation
- Database lock: Kill running API server before tests or use separate test database
- Provider naming: Update tests to use "apple" instead of "apple_vision" to match actual implementation
- Timeouts: Investigate and fix underlying causes (likely related to database lock)

## Need help?
- Ask if anything is unclear
- Keep it simple