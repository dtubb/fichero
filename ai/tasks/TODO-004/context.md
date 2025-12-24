# Context for TODO-004: File/Folder Import Endpoint Testing

## Background
The File/Folder Import Endpoint is a critical component of the Fichero backend that allows users to import files and folders into their document library. This endpoint is foundational for the application's document management functionality.

## Current State
- The ingest endpoints are already implemented in `src/fichero/api/routes/ingest.py`
- Basic unit tests exist in `tests/unit/test_api.py` (TestIngestRoutes class)
- Comprehensive unit tests for the underlying ingest module exist in `tests/unit/test_ingest_module.py`
- The endpoints support both file and folder ingestion with various options
- **File Type Support**: 7 categories with 50+ file extensions (images, PDF, audio, video, text, word, ebooks)

## Endpoint Details

### File Ingest Endpoint
- **Path**: `/api/ingest/file`
- **Method**: POST
- **Parameters**:
  - `path`: Path to the file to ingest
  - `parent_id`: Optional parent document ID
  - `copy_mode`: Boolean (link vs copy)
  - `extract_text`: Boolean
  - `auto_embed`: Boolean
- **Returns**: Document object immediately

### Folder Ingest Endpoint
- **Path**: `/api/ingest/folder`
- **Method**: POST
- **Parameters**:
  - `path`: Path to the folder to ingest
  - `parent_id`: Optional parent document ID
  - `copy_mode`: Boolean (link vs copy)
  - `recursive`: Boolean
  - `extract_text`: Boolean
  - `auto_embed`: Boolean
- **Returns**: Task object (async processing)

### Status Endpoint
- **Path**: `/api/ingest/status/{task_id}`
- **Method**: GET
- **Returns**: Task status with progress information

## Testing Strategy
The goal is to ensure comprehensive test coverage for:
1. **Happy path scenarios**: Normal file/folder imports
2. **Error handling**: Invalid paths, missing files, permission issues
3. **Edge cases**: Empty folders, large files, special characters in filenames
4. **Parameter validation**: Invalid parameters, missing required fields
5. **Integration**: End-to-end testing with real files (where appropriate)

## File Type Support Details

The ingest endpoint supports comprehensive file type detection and handling:

### Supported Categories
1. **Images**: 20+ formats including JPEG, PNG, TIFF, WEBP, HEIC, RAW formats
2. **PDF**: Standard PDF documents
3. **Audio**: 7+ formats including MP3, WAV, M4A, FLAC
4. **Video**: 5+ formats including MP4, MOV, AVI, MKV
5. **Text**: Plain text and markup formats
6. **Word Documents**: Microsoft Word and OpenDocument formats
7. **Ebooks**: EPUB and MOBI formats

### File Type Detection
- Uses extension-based detection via `_FILE_TYPE_MAP`
- Case-insensitive matching
- Returns `FileType.other` for unknown extensions
- Supports both common and professional formats (e.g., RAW camera files)

## Dependencies
- TODO-004 is a prerequisite for TODO-005 (Document Move Endpoint)
- TODO-004 is a prerequisite for TODO-024 (Frontend Import UI)
- **New Dependency**: TODO-025 (Comprehensive File Type Testing) for validation with actual files

## Success Criteria
- All ingest endpoints are thoroughly tested
- Edge cases are handled properly
- Error messages are clear and helpful
- The endpoints work reliably with real files and folders