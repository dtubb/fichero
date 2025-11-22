"""
Fichero Constants - Centralized configuration values

Defines supported file formats and other application-wide constants.
"""

# ===== SUPPORTED FILE FORMATS =====

# All supported image formats (comprehensive list)
SUPPORTED_IMAGE_EXTENSIONS = {
    # Common formats
    '.jpg', '.jpeg',  # JPEG
    '.png',           # PNG
    '.gif',           # GIF
    '.bmp',           # Bitmap
    '.webp',          # WebP

    # RAW and professional formats
    '.tif', '.tiff',  # TIFF
    '.heic', '.heif', # HEIC/HEIF (iPhone photos)
    '.jxl',           # JPEG XL
    '.raw',           # RAW
    '.cr2', '.nef', '.arw',  # Canon, Nikon, Sony RAW

    # Less common but supported
    '.svg',           # SVG (vector)
    '.ico',           # Icon
    '.tga',           # Targa
    '.psd',           # Photoshop (if PIL supports)
}

# PDF document format
SUPPORTED_PDF_EXTENSIONS = {
    '.pdf'
}

# All document formats that can be processed
SUPPORTED_DOCUMENT_EXTENSIONS = SUPPORTED_PDF_EXTENSIONS | {
    '.docx', '.doc',  # Microsoft Word
    '.xlsx', '.xls',  # Microsoft Excel
    '.pptx', '.ppt',  # Microsoft PowerPoint
    '.txt',           # Plain text
    '.md',            # Markdown
    '.rtf',           # Rich Text Format
}

# All supported file types (images + documents)
SUPPORTED_FILE_EXTENSIONS = (
    SUPPORTED_IMAGE_EXTENSIONS |
    SUPPORTED_PDF_EXTENSIONS |
    SUPPORTED_DOCUMENT_EXTENSIONS
)

# For display/logging
SUPPORTED_FORMATS_DISPLAY = (
    "Images: JPG, PNG, GIF, BMP, WebP, TIFF, HEIC, HEIF, JPEG XL, RAW formats (CR2, NEF, ARW)\n"
    "Documents: PDF, DOCX, DOC, XLSX, XLS, TXT, MD, RTF\n"
    "Vectors: SVG"
)

def is_supported_file(file_path: str) -> bool:
    """
    Check if a file is supported by Fichero.

    Args:
        file_path: Path to file (str or Path)

    Returns:
        True if file extension is in supported list
    """
    from pathlib import Path

    if not file_path:
        return False

    # Convert to Path and get lowercase extension
    ext = Path(file_path).suffix.lower()

    return ext in SUPPORTED_FILE_EXTENSIONS


def is_image_file(file_path: str) -> bool:
    """
    Check if a file is a supported image format.

    Args:
        file_path: Path to file (str or Path)

    Returns:
        True if file is a supported image
    """
    from pathlib import Path

    if not file_path:
        return False

    ext = Path(file_path).suffix.lower()
    return ext in SUPPORTED_IMAGE_EXTENSIONS


def is_pdf_file(file_path: str) -> bool:
    """
    Check if a file is a PDF.

    Args:
        file_path: Path to file (str or Path)

    Returns:
        True if file is a PDF
    """
    from pathlib import Path

    if not file_path:
        return False

    ext = Path(file_path).suffix.lower()
    return ext in SUPPORTED_PDF_EXTENSIONS


def is_document_file(file_path: str) -> bool:
    """
    Check if a file is a supported document format.

    Args:
        file_path: Path to file (str or Path)

    Returns:
        True if file is a supported document
    """
    from pathlib import Path

    if not file_path:
        return False

    ext = Path(file_path).suffix.lower()
    return ext in SUPPORTED_DOCUMENT_EXTENSIONS
