# TODO-027: Test Proper Ingest Pipeline with Real Workflow

## What to do
Create comprehensive integration tests for the complete ingest pipeline to ensure it works as expected in production.

## Steps
- [ ] Step 1: Analyze current test coverage and identify gaps in ingest pipeline testing
- [ ] Step 2: Create integration test suite for complete workflow testing
- [ ] Step 3: Implement tests for folder ingestion with nested structures
- [ ] Step 4: Test parent-child document relationships and collection creation
- [ ] Step 5: Test both LINK and COPY modes with APFS cloning
- [ ] Step 6: Implement database integration tests
- [ ] Step 7: Test storage integration and metadata extraction
- [ ] Step 8: Implement error handling tests (mixed files, permissions, disk space)
- [ ] Step 9: Test progress reporting and duplicate detection
- [ ] Step 10: Run all tests and verify complete pipeline functionality

## Files
- File to change: tests/integration/__init__.py (new integration test suite)
- File to change: tests/unit/test_ingest_module.py (existing ingest tests)
- File to change: src/fichero/ingest.py (main ingest module)
- File to change: src/fichero/db.py (database integration)
- File to change: src/fichero/storage.py (storage integration)

## Questions for Human
- [x] Question 1: Should I create a separate integration test suite or extend existing tests?
    Answer: Extend existing tests
- [x] Question 2: Are there specific workflow scenarios to prioritize for testing?
    Answer: Not sure, use judgment based on current coverage
- [x] Question 3: Should I test with the actual database or use mocks for integration tests?
    Answer: Use mocks for database
- [ ] Question 4: Any specific error conditions to test beyond what's mentioned?
    Answer: 

## Answers and Implementation
- [Summary of decisions made]
- [Implementation approach chosen]

## Need help?
- Ask if anything is unclear
- Keep it simple