# Test Text Extraction from Documents

## Issue
Text extraction functionality exists in the ingest module but hasn't been thoroughly tested. We need to verify:

1. **Text extraction from supported formats**:
   - PDF files
   - DOCX files
   - EPUB files
   - Text files (TXT, MD, etc.)

2. **Text extraction quality**:
   - Accuracy of extracted text
   - Formatting preservation
   - Handling of complex documents
   - Language support

3. **Integration with search**:
   - Text content stored in page_content
   - Embedding generation for search
   - Search functionality with extracted text

## Requirements
1. **Create text extraction tests**:
   - Test `extract_text=True` parameter
   - Test text extraction for each supported format
   - Verify page_content is properly populated
   - Test text length and quality

2. **Test with real documents**:
   - Create sample PDF with text
   - Create sample DOCX with formatted text
   - Create sample EPUB with chapters
   - Test with multilingual content

3. **Test search integration**:
   - Verify embeddings are created
   - Test search with extracted text
   - Test relevance and accuracy

## Questions for Human
- Should I create specific test documents for text extraction?
- Any specific text extraction scenarios to prioritize?
- Should I test with complex document structures?
- Any specific languages to test?

## Priority
**P1 - High**: Text extraction is critical for search functionality and needs thorough testing.
