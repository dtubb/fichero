# TODO-029: Test Text Extraction from Documents

## What to do
Test text extraction functionality in the ingest module for supported document formats.

## Steps
- [ ] Step 1: Review current text extraction implementation in ingest module
- [ ] Step 2: Create test documents for each supported format (PDF, DOCX, EPUB, TXT, MD)
- [ ] Step 3: Write unit tests for text extraction with extract_text=True parameter
- [ ] Step 4: Test text extraction quality and accuracy
- [ ] Step 5: Verify page_content is properly populated
- [ ] Step 6: Test integration with search and embedding generation
- [ ] Step 7: Test with multilingual content if applicable
- [ ] Step 8: Document test results and any issues found

## Files
- File to change: src/fichero/ingest.py
- File to change: tests/unit/test_ingest_module.py
- File to create: tests/fixtures/sample_files/ (various test documents)

## Questions for Human
- [ ] Question 1: Should I create specific test documents for text extraction?
    Answer: [Space for answer]
- [ ] Question 2: Any specific text extraction scenarios to prioritize?
    Answer: [Space for answer]
- [ ] Question 3: Should I test with complex document structures?
    Answer: [Space for answer]
- [ ] Question 4: Any specific languages to test?
    Answer: [Space for answer]

## Answers and Implementation
- [Summary of decisions made]
- [Implementation approach chosen]

## Need help?
- Ask if anything is unclear
- Keep it simple