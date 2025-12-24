# Test Proper Ingest Pipeline with Real Workflow

## Issue
The current tests verify individual file ingestion but don't test the complete ingest pipeline as used in the actual application. We need to test:

1. **Complete workflow testing**:
   - Folder ingestion with nested structure
   - Parent-child relationships
   - Collection creation
   - Bookmark functionality (macOS)
   - Copy mode with APFS cloning

2. **Integration testing**:
   - Database integration
   - Storage integration
   - Bookmark system integration
   - Metadata extraction in real workflow

3. **End-to-end testing**:
   - Full folder import process
   - Error handling in workflow
   - Progress reporting
   - Duplicate detection

## Requirements
1. **Create integration tests** for complete workflow:
   - Test `ingest_folder()` with real folder structures
   - Test both LINK and COPY modes
   - Test parent-child document relationships
   - Test collection creation and hierarchy

2. **Test database integration**:
   - Verify documents are properly saved
   - Test query and retrieval
   - Test metadata storage

3. **Test error handling**:
   - Test with mixed valid/invalid files
   - Test permission errors
   - Test disk space issues

## Questions for Human
- Should I create a separate integration test suite?
- Are there specific workflow scenarios to prioritize?
- Should I test with the actual database or use mocks?
- Any specific error conditions to test?

## Priority
**P1 - High**: This ensures the complete ingest pipeline works as expected in production.
