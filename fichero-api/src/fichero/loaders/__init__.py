"""
Fichero Media Loaders

Unified system for loading various media formats into normalized MediaContent.
Each format uses the optimal library:

- Images (JPG, PNG, TIFF, etc.): PIL/Pillow
- RAW images (CR2, NEF, ARW): rawpy
- HEIC/HEIF (iPhone): heif-convert system tool
- PDFs → Images: PyMuPDF (fast, no poppler dependency)
- PDFs → Text: Kreuzberg (when text extraction is needed)
- Office docs (DOCX, XLSX, PPTX): Kreuzberg
- EPUB: Kreuzberg
- IIIF manifests: Custom HTTP loader
- Audio: Future (Whisper)
- Video: Future (ffmpeg frame extraction)

Usage:
    from fichero.loaders import load_media, MediaContent

    # Load any supported file
    content = await load_media("/path/to/file.pdf")

    # Access normalized output
    print(content.text)      # Extracted text (if any)
    print(content.images)    # List of PIL Images
    print(content.metadata)  # Format-specific metadata
"""

from fichero.loaders.base import MediaContent, MediaLoader
from fichero.loaders.unified import load_media, UnifiedLoader

__all__ = [
    "MediaContent",
    "MediaLoader",
    "load_media",
    "UnifiedLoader",
]
