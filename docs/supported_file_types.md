(AI generated. Not reviewed.)

# Supported File Types

The Fichero ingest module supports 37 different file types across multiple categories. File type detection is based on file extensions.

## File Type Categories

### Images (17 formats)

- `.jpg`, `.jpeg` - JPEG images
- `.png` - Portable Network Graphics
- `.gif` - Graphics Interchange Format
- `.webp` - WebP images
- `.tiff`, `.tif` - Tagged Image File Format
- `.bmp` - Bitmap images
- `.heic`, `.heif` - High Efficiency Image Format
- `.jxl` - JPEG XL images
- `.avif` - AV1 Image File Format
- `.raw` - RAW image format
- `.cr2`, `.cr3` - Canon RAW formats
- `.nef` - Nikon Electronic Format
- `.arw` - Sony Alpha RAW
- `.dng` - Digital Negative
- `.orf` - Olympus RAW Format
- `.rw2` - Panasonic RAW Format

### Documents (4 formats)

- `.pdf` - Portable Document Format
- `.txt` - Plain text files
- `.md` - Markdown files
- `.rst` - reStructuredText files
- `.rtf` - Rich Text Format

### Word Processing (3 formats)

- `.doc` - Microsoft Word 97-2003
- `.docx` - Microsoft Word (Office Open XML)
- `.odt` - OpenDocument Text

### Ebooks (2 formats)

- `.epub` - Electronic Publication
- `.mobi` - Mobipocket eBook

### Audio (7 formats)

- `.mp3` - MPEG Audio Layer III
- `.wav` - Waveform Audio File Format
- `.m4a` - MPEG-4 Audio
- `.aac` - Advanced Audio Coding
- `.flac` - Free Lossless Audio Codec
- `.ogg` - Ogg Vorbis
- `.wma` - Windows Media Audio

### Video (4 formats)

- `.mp4` - MPEG-4 Video
- `.mov` - QuickTime Movie
- `.avi` - Audio Video Interleave
- `.mkv` - Matroska Video
- `.webm` - WebM Video

## Text Extractable File Types

The following file types support text extraction for search indexing:

- `FileType.pdf` - PDF documents
- `FileType.word` - Word documents (.doc, .docx, .odt)
- `FileType.text` - Text files (.txt, .md, .rst, .rtf)
- `FileType.epub` - EPUB ebooks

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
    epub = "epub"
    other = "other"
```

## Unsupported File Types

Files with extensions not in the `_FILE_TYPE_MAP` are classified as `FileType.other`. These files can still be ingested but may have limited functionality:

- No specialized metadata extraction
- No text extraction
- Basic file operations only

## File Type Statistics

- **Total supported**: 37 file extensions
- **Image formats**: 17 (46% of total)
- **Document formats**: 4 (11% of total)
- **Text extractable**: 4 file types
- **Media files**: 11 audio/video formats (30% of total)

## Best Practices for File Types

1. **Use standard extensions**: Ensure files have correct extensions for proper detection
2. **Text extraction**: Enable for PDF, Word, and text files to improve searchability
3. **Image metadata**: EXIF data is automatically extracted for supported image formats
4. **Large files**: Consider LINK mode for very large files to save storage space
5. **Unsupported types**: Can still be ingested but with limited functionality