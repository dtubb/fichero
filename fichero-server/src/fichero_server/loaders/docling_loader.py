"""
Docling loader for structured document parsing.

Docling (IBM) provides:
- PDF parsing with layout analysis
- Table extraction with structure
- Document hierarchy understanding
- Multi-format support (PDF, DOCX, PPTX, etc.)

Docling is optimized for structured document understanding where
layout and structure matter (forms, reports, contracts).

For simpler text extraction, Kreuzberg (via DocumentLoader) may be sufficient.

Usage:
    from fichero_server.loaders.docling_loader import DoclingLoader

    loader = DoclingLoader()

    # Check if available
    if loader.is_available():
        content = await loader.load(Path("document.pdf"))
        print(content.text)  # Structured markdown
        print(content.metadata["tables"])  # Extracted tables
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fichero_server.loaders.base import MediaLoader, MediaContent

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Formats Docling handles well (structured documents)
DOCLING_FORMATS = {
    ".pdf",
    ".docx",
    ".doc",
    ".pptx",
    ".ppt",
    ".xlsx",
    ".xls",
    ".html",
    ".htm",
    ".md",
    ".asciidoc",
}

# Optional extras Docling can handle with additional dependencies
DOCLING_OPTIONAL_FORMATS = {
    ".epub",
    ".rtf",
}


# =============================================================================
# Docling Loader
# =============================================================================


class DoclingLoader(MediaLoader):
    """Document loader using IBM Docling for structured extraction.

    Features:
    - Layout-aware PDF parsing
    - Table extraction with structure preservation
    - Multi-column document handling
    - Document hierarchy extraction
    - Output as Markdown or structured data

    Comparison with Kreuzberg:
    - Docling: Better for structured documents (forms, tables, layout)
    - Kreuzberg: Better for simple text extraction, broader format support
    """

    def __init__(
        self,
        extract_tables: bool = True,
        extract_images: bool = False,
        output_format: str = "markdown",  # "markdown", "json"
    ):
        """Initialize Docling loader.

        Args:
            extract_tables: If True, extract tables with structure
            extract_images: If True, extract embedded images
            output_format: Output format for text ("markdown" or "json")
        """
        self.extract_tables = extract_tables
        self.extract_images = extract_images
        self.output_format = output_format
        self._converter = None

    @property
    def supported_formats(self) -> set[str]:
        """Return supported file formats."""
        return DOCLING_FORMATS

    def can_handle(self, source: str | Path) -> bool:
        """Check if this loader can handle the given source.

        Args:
            source: File path or URL

        Returns:
            True if this loader can handle the source
        """
        if isinstance(source, str):
            if source.startswith("http"):
                return False
            source = Path(source)
        return source.suffix.lower() in DOCLING_FORMATS

    @staticmethod
    def is_available() -> bool:
        """Check if Docling is installed and available."""
        try:
            from docling.document_converter import DocumentConverter  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_converter(self):
        """Get or create the DocumentConverter instance."""
        if self._converter is None:
            try:
                from docling.document_converter import DocumentConverter

                self._converter = DocumentConverter()
            except ImportError:
                raise ImportError(
                    "Docling not installed. Install with: pip install docling"
                )
        return self._converter

    async def load(self, source: str | Path) -> MediaContent:
        """Load and parse a document.

        Args:
            source: Path to document

        Returns:
            MediaContent with extracted text and metadata
        """
        path = Path(source).resolve()

        if not path.exists():
            raise FileNotFoundError(f"Document not found: {path}")

        # Run synchronous Docling in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._load_sync, path)

    def _load_sync(self, path: Path) -> MediaContent:
        """Synchronous document loading."""
        converter = self._get_converter()

        try:
            # Convert document
            result = converter.convert(str(path))
            doc = result.document

            # Extract text based on output format
            if self.output_format == "json":
                text = doc.export_to_json()
            else:
                text = doc.export_to_markdown()

            # Extract tables if requested
            tables = []
            if self.extract_tables:
                tables = self._extract_tables(doc)

            # Build metadata
            metadata: dict[str, Any] = {
                "source": str(path),
                "filename": path.name,
                "format": path.suffix.lower(),
            }

            # Document properties
            if hasattr(doc, "title") and doc.title:
                metadata["title"] = doc.title
            if hasattr(doc, "authors") and doc.authors:
                metadata["authors"] = doc.authors
            if hasattr(doc, "pages"):
                metadata["num_pages"] = len(doc.pages)

            # Add tables to metadata
            if tables:
                metadata["tables"] = tables
                metadata["table_count"] = len(tables)

            # Extract images if requested
            images = []
            if self.extract_images:
                images = self._extract_images(doc)

            logger.info(
                f"Docling loaded: {path.name} "
                f"({metadata.get('num_pages', 'N/A')} pages, "
                f"{len(tables)} tables)"
            )

            return MediaContent(
                source=str(path),
                text=text,
                images=images,
                metadata=metadata,
                mime_type=self._get_mime_type(path),
                needs_vlm=False,  # Docling extracts text directly
            )

        except Exception as e:
            logger.error(f"Docling failed for {path}: {e}")
            raise

    def _extract_tables(self, doc) -> list[dict]:
        """Extract tables from document.

        Returns list of table dicts with structure and data.
        """
        tables = []

        try:
            if not hasattr(doc, "tables"):
                return tables

            for i, table in enumerate(doc.tables):
                table_data: dict[str, Any] = {
                    "index": i,
                }

                # Get DataFrame if available
                if hasattr(table, "export_to_dataframe"):
                    try:
                        df = table.export_to_dataframe()
                        table_data["data"] = df.to_dict(orient="records")
                        table_data["columns"] = list(df.columns)
                        table_data["rows"] = len(df)
                    except Exception:
                        pass

                # Get caption if available
                if hasattr(table, "caption") and table.caption:
                    table_data["caption"] = table.caption

                # Get bounding box if available
                if hasattr(table, "bbox") and table.bbox:
                    table_data["bbox"] = table.bbox

                tables.append(table_data)

        except Exception as e:
            logger.warning(f"Table extraction failed: {e}")

        return tables

    def _extract_images(self, doc) -> list:
        """Extract images from document."""
        images = []

        try:
            if not hasattr(doc, "pictures"):
                return images

            for picture in doc.pictures:
                if hasattr(picture, "image") and picture.image:
                    images.append(picture.image)

        except Exception as e:
            logger.warning(f"Image extraction failed: {e}")

        return images

    def _get_mime_type(self, path: Path) -> str:
        """Get MIME type for file."""
        suffix = path.suffix.lower()
        mime_map = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".ppt": "application/vnd.ms-powerpoint",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".html": "text/html",
            ".htm": "text/html",
            ".md": "text/markdown",
        }
        return mime_map.get(suffix, "application/octet-stream")


# =============================================================================
# Convenience Functions
# =============================================================================


async def load_with_docling(
    path: Path,
    extract_tables: bool = True,
    output_format: str = "markdown",
) -> MediaContent:
    """Convenience function to load a document with Docling.

    Args:
        path: Path to document
        extract_tables: If True, extract tables
        output_format: "markdown" or "json"

    Returns:
        MediaContent
    """
    loader = DoclingLoader(
        extract_tables=extract_tables,
        output_format=output_format,
    )
    return await loader.load(path)


def load_with_docling_sync(
    path: Path,
    extract_tables: bool = True,
    output_format: str = "markdown",
) -> MediaContent:
    """Synchronous convenience function.

    Args:
        path: Path to document
        extract_tables: If True, extract tables
        output_format: "markdown" or "json"

    Returns:
        MediaContent
    """
    loader = DoclingLoader(
        extract_tables=extract_tables,
        output_format=output_format,
    )
    return loader._load_sync(Path(path))


__all__ = [
    "DoclingLoader",
    "DOCLING_FORMATS",
    "load_with_docling",
    "load_with_docling_sync",
]
