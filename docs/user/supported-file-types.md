<!-- Verified against importers/ingest.py (_FILE_TYPE_MAP, _TEXT_EXTRACTABLE) and models.py (FileType), 2026-07-18. -->

# Supported File Types

The Fichero ingest module maps **56 file extensions** to a `FileType`, based on
the file extension. The authoritative list is `_FILE_TYPE_MAP` in
`fichero-server/src/fichero_server/importers/ingest.py`; the groups below reflect it.

## File Type Categories

### Images (20)

`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.tiff`, `.tif`, `.bmp`, `.heic`,
`.heif`, `.jxl`, `.avif`, `.raw`, `.cr2`, `.cr3`, `.nef`, `.arw`, `.dng`,
`.orf`, `.rw2`

### PDF (1)

`.pdf`

### Text & markup (8)

`.txt`, `.md`, `.markdown`, `.rst`, `.rtf`, `.htm`, `.html`, `.xml`

### Word processing (3)

`.doc`, `.docx`, `.odt`

### Spreadsheets (4)

`.csv`, `.xls`, `.xlsx`, `.ods`

### Presentations (3)

`.ppt`, `.pptx`, `.odp`

### Ebooks (2)

`.epub`, `.mobi`

### Audio (7)

`.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, `.ogg`, `.wma`

### Video (5)

`.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`

### Subtitles / captions (3)

`.srt`, `.vtt`, `.sbv`

## Text Extractable File Types

The following `FileType`s support text extraction for search indexing
(`_TEXT_EXTRACTABLE`):

- `FileType.pdf` - PDF documents
- `FileType.word` - Word documents (.doc, .docx, .odt)
- `FileType.text` - Text files (.txt, .md, .rst, .rtf, and other text/markup)
- `FileType.epub` - EPUB ebooks
- `FileType.spreadsheet` - CSV / XLS / XLSX / ODS
- `FileType.presentation` - PPT / PPTX / ODP

## File Type Detection Algorithm

1. Extract file extension using `path.suffix.lower()`
2. Look up extension in `_FILE_TYPE_MAP` dictionary
3. Return corresponding `FileType` enum value
4. Default to `FileType.other` for unknown extensions

## MIME Type Detection

The system uses Python's `mimetypes` module to detect MIME types:

```python
mime_type, _ = mimetypes.guess_type(str(path))
```

Detected MIME types are stored in document metadata for reference.

## File Type Enum

```python
class FileType(str, Enum):
    image = "image"
    pdf = "pdf"
    audio = "audio"
    video = "video"
    text = "text"
    word = "word"
    docx = "docx"
    epub = "epub"
    spreadsheet = "spreadsheet"
    presentation = "presentation"
    other = "other"
```

## Unsupported File Types

Files with extensions not in the `_FILE_TYPE_MAP` are classified as `FileType.other`. These files can still be ingested but may have limited functionality:

- No specialized metadata extraction
- No text extraction
- Basic file operations only

## File Type Statistics

- **Total supported**: 56 file extensions
- **Image formats**: 20
- **Text/markup + office (word/spreadsheet/presentation)**: 18
- **Text-extractable `FileType`s**: 6 (pdf, word, text, epub, spreadsheet, presentation)
- **Media files**: 12 audio/video + 3 subtitle formats

## Best Practices for File Types

1. **Use standard extensions**: Ensure files have correct extensions for proper detection
2. **Text extraction**: Enable for PDF, Word, and text files to improve searchability
3. **Image metadata**: EXIF data is automatically extracted for supported image formats
4. **Large files**: Consider LINK mode for very large files to save storage space
5. **Unsupported types**: Can still be ingested but with limited functionality