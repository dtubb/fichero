# Appendix A: Supported File Types


Fichero’s import system maps 61 file extensions to a file type.

| Category | Extensions | Text extraction |
|----|----|----|
| Images (16) | `.jpg` `.jpeg` `.png` `.gif` `.webp` `.tiff` `.tif` `.bmp` `.heic` `.heif` `.jxl` `.avif` `.jp2` `.j2k` `.jpf` `.jpx` | — |
| RAW images (8) | `.raw` `.cr2` `.cr3` `.nef` `.arw` `.dng` `.orf` `.rw2` | — |
| PDF (1) | `.pdf` | Yes |
| Text & markup (9) | `.txt` `.md` `.markdown` `.rst` `.rtf` `.html` `.htm` `.xml` `.jsonl` | Yes |
| Subtitles / transcripts (3) | `.srt` `.vtt` `.sbv` | Yes (as text) |
| Word processing (3) | `.doc` `.docx` `.odt` | Yes |
| Spreadsheets (4) | `.csv` `.xlsx` `.xls` `.ods` | Yes |
| Presentations (3) | `.pptx` `.ppt` `.odp` | Yes |
| Ebooks (2) | `.epub` `.mobi` | Yes (EPUB) |
| Audio (7) | `.mp3` `.wav` `.m4a` `.aac` `.flac` `.ogg` `.wma` | — |
| Video (5) | `.mp4` `.mov` `.avi` `.mkv` `.webm` | — |

Notes:

– RTF, HTML, and XML are read as text: the loader extracts the plain body text, which is exactly what full-text search needs.

– EXIF metadata is extracted automatically for supported image formats.

– Files with extensions not in the list can still be imported, classified as “other,” but get no text extraction and no specialized metadata.

– For very large files, consider **Link Files…** so the library does not duplicate them.
