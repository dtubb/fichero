# Fichero Supported File Formats

**Last Updated**: November 21, 2025

Fichero now supports a comprehensive range of file formats for import and processing.

## Supported Image Formats

### Common Formats
- **JPEG** (`.jpg`, `.jpeg`)
- **PNG** (`.png`)
- **GIF** (`.gif`)
- **BMP** (`.bmp`)
- **WebP** (`.webp`)

### Professional & RAW Formats
- **TIFF** (`.tif`, `.tiff`)
- **HEIC/HEIF** (`.heic`, `.heif`) - iPhone/iOS photos
- **JPEG XL** (`.jxl`) - Next-generation image format
- **RAW** (`.raw`) - Generic RAW
- **Canon RAW** (`.cr2`)
- **Nikon RAW** (`.nef`)
- **Sony RAW** (`.arw`)

### Vector & Specialized Formats
- **SVG** (`.svg`) - Scalable Vector Graphics
- **ICO** (`.ico`) - Icon files
- **TGA** (`.tga`) - Targa
- **PSD** (`.psd`) - Photoshop (if Pillow supports)

**Total Image Formats**: 20+

## Supported Document Formats

### PDF
- **PDF** (`.pdf`) - Portable Document Format
  - Multi-page PDFs are supported
  - Pages can be extracted and processed individually

### Microsoft Office
- **Word** (`.docx`, `.doc`)
- **Excel** (`.xlsx`, `.xls`)
- **PowerPoint** (`.pptx`, `.ppt`)

### Text & Markup
- **Plain Text** (`.txt`)
- **Markdown** (`.md`)
- **Rich Text** (`.rtf`)

**Total Document Formats**: 10+

## Total Supported Formats: 29+

## Format Detection

Fichero automatically detects file types based on file extensions (case-insensitive). All format checking is centralized in `/src/fichero/constants.py`.

## Import Capabilities

You can import:
- ✅ **Individual files** (any supported format)
- ✅ **Folders** containing supported files
- ✅ **Nested folders** (folders within folders)
- ✅ **Mixed content** (images + PDFs + documents in same folder)
- ✅ **URLs** pointing to images/documents
- ✅ **ZIP archives** containing supported files

## Processing Notes

### Images
- All image formats are rendered using the `UniversalImageRenderer`
- Images can be cropped, enhanced, rotated, segmented, etc.
- RAW formats are converted to standard formats during processing

### PDFs ✨ NEW!
- **Multi-page PDFs are fully supported**
- **Automatic conversion**: PDFs are automatically converted to high-quality JPG images (300 DPI)
- **Page splitting**: Each PDF page becomes a separate image file
  - Single-page PDF: `document.pdf` → `document.jpg`
  - Multi-page PDF: `report.pdf` → `report_page_001.jpg`, `report_page_002.jpg`, etc.
- **Full OCR pipeline**: Converted pages go through the complete transcription workflow
- **PDF metadata preserved**: Document title, author, and page count tracked in manifest
- **Requirements**:
  - Desktop only (macOS, Linux, Windows)
  - Requires Poppler system library (install with `brew install poppler` on macOS)
  - Uses `pdf2image` Python library (already in dependencies)

### HEIC/HEIF
- iPhone photos in HEIC format are fully supported
- Automatically converted to JPEG for processing if needed

### RAW Formats
- Professional camera RAW files (CR2, NEF, ARW, etc.) are supported
- Requires `libraw` or `rawpy` to be installed
- RAW files are converted to TIFF/JPEG for processing

## Configuration

All supported formats are defined in:
```python
src/fichero/constants.py
```

To add a new format:
1. Add the extension to the appropriate set in `constants.py`
2. No other changes needed - the system automatically picks up the new format

## Helper Functions

```python
from fichero.constants import (
    is_supported_file,  # Check if any file is supported
    is_image_file,      # Check if file is an image
    is_pdf_file,        # Check if file is a PDF
    is_document_file    # Check if file is a document
)

# Usage
if is_supported_file("photo.heic"):
    print("✅ HEIC photos are supported!")

if is_image_file("IMG_1234.CR2"):
    print("✅ Canon RAW files are supported!")

if is_pdf_file("document.pdf"):
    print("✅ PDFs are supported!")
```

## PDF Processing Workflow

When you import a PDF:

1. **Import**: PDF added to collection
   ```bash
   fichero library add "Legal Documents" --source /path/to/pdfs
   ```

2. **Preparation** (`prepare_images` step):
   - PDF converted to 300 DPI images
   - Each page becomes separate JPG file
   - EXIF rotation applied if needed
   - Compressed to 85% quality

3. **Transcription** (`transcribe` step):
   - Each page image processed through OCR
   - Text extracted using AI models
   - Transcriptions saved as JSON

4. **Output** (`convert_to_word` step):
   - All pages combined into Word document
   - Side-by-side image + transcription layout

### Example Output Structure

```
Input:
  documents/contract.pdf (3 pages)

After prepare_images:
  assets/prepared/contract_page_001.jpg  (2480 x 3508 px)
  assets/prepared/contract_page_002.jpg
  assets/prepared/contract_page_003.jpg

After transcription:
  assets/transcriptions/contract_page_001.json
  assets/transcriptions/contract_page_002.json
  assets/transcriptions/contract_page_003.json

Final output:
  contract.docx (combined document with all pages)
```

## Troubleshooting

### PDF Conversion Errors

**Error**: "PDF support requires pdf2image library"
- **Solution**: Desktop platforms only. PDFs not supported on mobile.

**Error**: "Unable to get page count. Is poppler installed?"
- **Solution**: Install Poppler:
  - macOS: `brew install poppler`
  - Linux: `apt-get install poppler-utils`
  - Windows: Download from https://github.com/oschwartz10612/poppler-windows/releases/

### HEIC/HEIF Errors

**Error**: "HEIC support requires heif-convert system tool"
- **Solution**: Install libheif:
  - macOS: `brew install libheif`
  - Linux: `apt-get install libheif-examples`

## Future Enhancements

Potential future format support:
- **Audio** (`.mp3`, `.wav`, `.m4a`) for transcription
- **Video** (`.mp4`, `.mov`) for frame extraction
- **eBooks** (`.epub`, `.mobi`)
- **Archives** (`.tar`, `.7z`)
- **Multi-page TIFF** (already supported by PIL, just needs testing)
