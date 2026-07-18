<!-- Verified against fichero/importers/ingest.py (2026-07-18). Describes only what is built. -->

# Ingest Module Overview

The ingest module is a core component of Fichero that handles file import, metadata extraction, and storage. It provides a unified interface for bringing external files into the Fichero document management system.

## Key Features

- **Three Ingestion Modes**: LINK (bookmark-based), COPY (file import), and MOVE (import then delete the original)
- **Comprehensive File Support**: Maps 50+ file extensions (`_FILE_TYPE_MAP`) to document, image, audio, and video types
- **Metadata Extraction**: Automatically extracts file metadata including size, checksums, and type-specific information
- **Text Extraction**: Extracts searchable text content from supported document formats
- **Folder Processing**: Recursive folder ingestion with automatic hierarchy creation
- **APFS Optimization**: Uses macOS APFS cloning for efficient file copying when available

## Architecture

```
External Files → Ingest Module → Database Storage
                      ↓
              Metadata Extraction
                      ↓
              Text Extraction (optional)
                      ↓
              Embedding Generation (optional)
```

## Core Components

### Ingestion Modes

- **LINK Mode**: Creates macOS bookmarks to reference external files without copying
- **COPY Mode**: Imports files into Fichero's library storage using APFS cloning when possible
- **MOVE Mode**: Imports the file into library storage, then deletes the original

### File Type Detection

- Extension-based mapping (`_FILE_TYPE_MAP`, 50+ extensions) to document/image/audio/video types
- Automatic MIME type detection
- Specialized handling for different content types

### Metadata Extraction

- Basic file metadata (size, checksums, MIME types)
- Image-specific metadata (dimensions, EXIF data)
- Document-specific metadata (text length, extraction status)
- Watch-folder provenance for camera intake:
  - `source_path` keeps the original absolute file path
  - `source_folder` records the ingest directory for DSLR / SD-card drops
  - `source_mtime` preserves the filesystem modification timestamp

### Text Extraction

- Uses unified loader system for PDF, DOCX, EPUB, and text files
- Extracts searchable content for indexing
- Stores extracted text in document.page_content

## Usage Patterns

The ingest module is designed for both simple and complex usage scenarios:

- Single file ingestion with minimal configuration
- Batch folder processing with recursive hierarchy creation
- Advanced options for text extraction and embedding
- Progress tracking for large operations

For camera and DSLR watched-folder intake, pair folder ingest with the built-in
`Rotate / Auto-Orient Images` preset. It is tagged as a capture preset for
import folders and keeps source provenance in document metadata while leaving
the original files untouched.

## Performance Considerations

- APFS cloning provides near-instant file copying on supported volumes
- Checksum-based deduplication prevents duplicate imports
- Asynchronous text extraction for non-blocking operations
- Memory-efficient processing of large files

## Error Handling

- Comprehensive validation of input paths
- Graceful handling of unsupported file types
- Detailed logging for troubleshooting
- Progress tracking with error reporting

## Integration Points

The ingest module integrates with:

- Database layer for document storage
- Bookmark system for external file references
- Loader system for text extraction
- Embedding system for search functionality
- Storage system for file organization
