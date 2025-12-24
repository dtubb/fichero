# TODO-025: Test File/Folder Import Endpoint with all supported file types

## What to do
Test the File/Folder Import Endpoint with all supported file types to ensure proper ingestion, file type detection, and metadata extraction.

## Steps
- [ ] Step 1: Review human_note.md for detailed test requirements
- [ ] Step 2: Create test fixture directory with sample files for all supported types
- [ ] Step 3: Implement file type detection tests
- [ ] Step 4: Test basic ingestion for each major file category
- [ ] Step 5: Verify metadata extraction for each file type
- [ ] Step 6: Test content access after ingestion
- [ ] Step 7: Test edge cases (corrupted files, large files, special characters)
- [ ] Step 8: Document findings and create test report

## Files
- File to change: src/fichero/ingest.py (if bugs found)
- Test files: tests/unit/test_ingest_module.py (add comprehensive tests)
- Test fixtures: tests/fixtures/sample_files/ (create sample files)

## Questions for Human
- [ ] Should we create a test fixture directory with sample files for all supported types?
    Answer: [Space for answer]
- [ ] Are there any specific file types that should be prioritized for testing?
    Answer: [Space for answer]
- [ ] Should we test with real-world sample files or generate synthetic test files?
    Answer: [Space for answer]
- [ ] Are there any security considerations for testing with various file types?
    Answer: [Space for answer]

## Answers and Implementation
- [Summary of decisions made]
- [Implementation approach chosen]

## Need help?
- Ask if anything is unclear
- Keep it simple