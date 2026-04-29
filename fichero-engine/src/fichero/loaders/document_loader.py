"""
Document loader using Kreuzberg for Office documents and EPUBs.

Handles: DOCX, XLSX, PPTX, EPUB, RTF, ODT, ODS, ODP
"""

import logging
from pathlib import Path

from fichero.loaders import kreuzberg_cache  # noqa: F401 — env-var side effect
from fichero.loaders.base import MediaContent, MediaLoader

logger = logging.getLogger(__name__)

# Office document formats
OFFICE_FORMATS = {
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".pptx",
    ".ppt",
    ".rtf",
    ".odt",
    ".ods",
    ".odp",
}

# E-book formats
EBOOK_FORMATS = {".epub", ".mobi"}

# Plain text formats (including CSV which is structured plain text)
TEXT_FORMATS = {".txt", ".md", ".markdown", ".rst", ".html", ".htm", ".xml", ".csv"}

ALL_DOCUMENT_FORMATS = OFFICE_FORMATS | EBOOK_FORMATS | TEXT_FORMATS


class DocumentLoader(MediaLoader):
    """
    Loader for Office documents and EPUBs using Kreuzberg.

    Kreuzberg handles 56+ document formats and provides:
    - Text extraction with layout preservation
    - Table extraction
    - Metadata extraction
    """

    def __init__(self, extract_tables: bool = True):
        """
        Initialize document loader.

        Args:
            extract_tables: Whether to extract tables from documents
        """
        self.extract_tables = extract_tables

    def can_handle(self, source: str | Path) -> bool:
        """Check if source is a supported document format."""
        return Path(source).suffix.lower() in ALL_DOCUMENT_FORMATS

    async def load(self, source: str | Path) -> MediaContent:
        """Load document and extract text using Kreuzberg."""
        path = Path(source)
        suffix = path.suffix.lower()

        # For plain text, just read the file directly
        if suffix in TEXT_FORMATS:
            return await self._load_text_file(path)

        # For Office/EPUB, use Kreuzberg
        return await self._load_with_kreuzberg(path)

    async def _load_text_file(self, path: Path) -> MediaContent:
        """Load plain text file directly."""
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Try other encodings
            for encoding in ["latin-1", "cp1252", "iso-8859-1"]:
                try:
                    text = path.read_text(encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                text = path.read_bytes().decode("utf-8", errors="replace")

        return MediaContent(
            source=str(path),
            text=text,
            images=[],
            metadata={
                "original_format": path.suffix.lstrip("."),
                "filename": path.name,
                "size_bytes": path.stat().st_size,
            },
            mime_type=self._get_mime_type(path.suffix.lower()),
            needs_vlm=False,  # Plain text doesn't need VLM
        )

    async def _load_with_kreuzberg(self, path: Path) -> MediaContent:
        """Load document using Kreuzberg."""
        try:
            import kreuzberg
        except ImportError:
            raise RuntimeError(
                "Document extraction requires kreuzberg. "
                "Install with: pip install kreuzberg"
            )

        suffix = path.suffix.lower()

        try:
            # Kreuzberg API signatures vary across versions.
            try:
                config = kreuzberg.ExtractionConfig(
                    force_ocr=False,
                    extract_tables=self.extract_tables,
                    extract_images=False,
                )
            except TypeError:
                try:
                    config = kreuzberg.ExtractionConfig(
                        force_ocr=False,
                    )
                except TypeError:
                    config = kreuzberg.ExtractionConfig()

            result = await kreuzberg.extract_file(str(path), config=config)

            metadata = {
                "original_format": suffix.lstrip("."),
                "filename": path.name,
                "extractor": "kreuzberg",
                "size_bytes": path.stat().st_size,
            }

            # Add table info if extracted
            if hasattr(result, "tables") and result.tables:
                metadata["table_count"] = len(result.tables)

            return MediaContent(
                source=str(path),
                text=result.content,
                images=[],
                metadata=metadata,
                mime_type=result.mime_type or self._get_mime_type(suffix),
                needs_vlm=False,  # Text documents don't need VLM
            )

        except Exception as e:
            logger.error(f"Failed to extract document {path}: {e}")
            raise

    def _get_mime_type(self, suffix: str) -> str:
        """Get MIME type for document format."""
        mime_types = {
            # Office
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".ppt": "application/vnd.ms-powerpoint",
            ".rtf": "application/rtf",
            # OpenDocument
            ".odt": "application/vnd.oasis.opendocument.text",
            ".ods": "application/vnd.oasis.opendocument.spreadsheet",
            ".odp": "application/vnd.oasis.opendocument.presentation",
            # E-books
            ".epub": "application/epub+zip",
            ".mobi": "application/x-mobipocket-ebook",
            # Text
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".markdown": "text/markdown",
            ".rst": "text/x-rst",
            ".html": "text/html",
            ".htm": "text/html",
            ".xml": "application/xml",
        }
        return mime_types.get(suffix, "application/octet-stream")
