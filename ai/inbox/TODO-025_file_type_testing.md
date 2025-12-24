Test the File/Folder Import Endpoint with all supported file types to ensure proper ingestion, file type detection, and metadata extraction.

The ingest endpoint claims to support a wide variety of file types, but comprehensive testing with actual files of each type has not been performed. We need to verify that:

1. All supported file types are correctly detected
2. Files are properly ingested without errors
3. Metadata is correctly extracted for each file type
4. File content can be accessed after ingestion

## Supported File Types (from ingest.py)

### Images (FileType.image)
- `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.tiff`, `.tif`, `.bmp`
- `.heic`, `.heif`, `.jxl`, `.avif`
- RAW formats: `.raw`, `.cr2`, `.cr3`, `.nef`, `.arw`, `.dng`, `.orf`, `.rw2`

### PDF (FileType.pdf)
- `.pdf`

### Audio (FileType.audio)
- `.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, `.ogg`, `.wma`

### Video (FileType.video)
- `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`

### Text (FileType.text)
- `.txt`, `.md`, `.rst`, `.rtf`

### Word Documents (FileType.word)
- `.doc`, `.docx`, `.odt`

### Ebooks (FileType.epub)
- `.epub`, `.mobi`

## Test Plan

### Phase 1: File Type Detection Testing
- Search online to create test files for each supported extension. Or download them from internet. 
 - Create a testing folder.
- Verify `detect_file_type()` function returns correct FileType
- Test case-insensitive extensions (e.g., `.JPG`, `.PNG`)

### Phase 2: Basic Ingestion Testing
- Test ingestion of sample files for each major category:
  - Images: JPEG, PNG, TIFF, WEBP, HEIC
  - PDF: Simple PDF with text
  - Audio: MP3, WAV, M4A
  - Video: MP4, MOV
  - Text: TXT, MD
  - Word: DOCX
  - Ebooks: EPUB

### Phase 3: Metadata Extraction Testing
- Verify metadata is correctly extracted for each file type:
  - File size
  - Checksum
  - Dimensions (for images)
  - Duration (for audio/video)
  - Page count (for PDF)
  - MIME type

### Phase 4: Content Access Testing
- Test that file content can be accessed after ingestion:
  - Image thumbnails can be generated
  - Text can be extracted from PDFs and documents
  - Audio/video metadata is accessible

### Phase 5: Edge Case Testing
- Test with corrupted files
- Test with very large files
- Test with files containing special characters in names
- Test with files in nested directories

## Required Test Files

### Sample Files Needed
1. **Images**:
   - `test.jpg` (standard JPEG)
   - `test.png` (PNG with transparency)
   - `test.tiff` (TIFF image)
   - `test.webp` (WebP image)
   - `test.heic` (HEIC image)

2. **Documents**:
   - `test.pdf` (PDF with text)
   - `test.docx` (Word document)
   - `test.txt` (plain text)
   - `test.md` (Markdown)

3. **Media**:
   - `test.mp3` (MP3 audio)
   - `test.wav` (WAV audio)
   - `test.mp4` (MP4 video)

4. **Ebooks**:
   - `test.epub` (EPUB ebook)

### File Creation Strategy
- Backend shoudl already be able to handle these. This task is to see what works.


## Expected Outcomes

### Success Criteria
- ✅ All supported file types are correctly detected
- ✅ Files are ingested without errors
- ✅ Metadata is properly extracted for each file type
- ✅ File content is accessible after ingestion
- ✅ Error handling works for unsupported/corrupted files

### Deliverables
- Comprehensive test suite covering all file types
- Test report documenting results for each file type
- Any bug fixes or improvements needed
- Updated documentation if file type support changes

## Questions for Human
- [ ] Should we create a test fixture directory with sample files for all supported types?
- [ ] Are there any specific file types that should be prioritized for testing?
- [ ] Should we test with real-world sample files or generate synthetic test files?
- [ ] Are there any security considerations for testing with various file types?

## Next Steps
1. Create test fixture directory with sample files
2. Implement comprehensive file type detection tests
3. Add ingestion tests for each major file category
4. Verify metadata extraction and content access
5. Document findings and create test report

## Priority
**P1 - High Priority**: This testing is essential to ensure the ingest endpoint works reliably with all claimed file types before users rely on it for their document management needs.