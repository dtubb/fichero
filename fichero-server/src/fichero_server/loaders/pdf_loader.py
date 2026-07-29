"""
PDF loader using PyMuPDF.

Primary use: Convert PDF pages to images for VLM processing.
Secondary use: Extract text from digital PDFs (selectable text).

PyMuPDF is fast and has no system dependencies (unlike pdf2image which needs poppler).
"""

import logging
from pathlib import Path

from PIL import Image

from fichero_server.loaders import kreuzberg_cache  # noqa: F401 — env-var side effect
from fichero_server.loaders.base import MediaContent, MediaLoader

logger = logging.getLogger(__name__)

PDF_FORMATS = {".pdf"}


class PDFLoader(MediaLoader):
    """
    Loader for PDF files using PyMuPDF.

    Renders PDF pages to images at configurable DPI.
    Also extracts text if the PDF has selectable text.
    """

    def __init__(self, dpi: int = 300, extract_text: bool = True):
        """
        Initialize PDF loader.

        Args:
            dpi: Resolution for page rendering (default 300 for archival quality)
            extract_text: Whether to also extract text from the PDF
        """
        self.dpi = dpi
        self.extract_text = extract_text

    def can_handle(self, source: str | Path) -> bool:
        """Check if source is a PDF."""
        return Path(source).suffix.lower() in PDF_FORMATS

    async def load(self, source: str | Path) -> MediaContent:
        """Load PDF and convert pages to images."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError(
                "PDF support requires PyMuPDF. Install with: pip install pymupdf"
            )

        path = Path(source)
        images = []
        text_parts = []

        metadata = {
            "original_format": "pdf",
            "filename": path.name,
            "dpi": self.dpi,
        }

        try:
            doc = fitz.open(str(path))
            metadata["page_count"] = len(doc)
            pdf_metadata = getattr(doc, "metadata", None)
            metadata["pdf_metadata"] = dict(pdf_metadata) if pdf_metadata else {}

            # Calculate zoom factor for desired DPI (PyMuPDF default is 72 DPI)
            zoom = self.dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)

            for page_num, page in enumerate(doc):
                # Render page to image
                pix = page.get_pixmap(matrix=matrix)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                images.append(img)

                # Extract text if enabled
                if self.extract_text:
                    page_text = page.get_text()
                    if page_text.strip():
                        text_parts.append(f"--- Page {page_num + 1} ---\n{page_text}")

            doc.close()

            # Combine extracted text
            extracted_text = "\n\n".join(text_parts) if text_parts else None

            # Determine if VLM is needed
            # If we got good text extraction, VLM may not be needed
            needs_vlm = True
            if extracted_text and len(extracted_text.strip()) > 100:
                # Decent amount of text extracted - probably a digital PDF
                metadata["text_extraction"] = "success"
                needs_vlm = False  # Can skip VLM if text is good
            else:
                metadata["text_extraction"] = "minimal"  # Likely scanned

            return MediaContent(
                source=str(path),
                text=extracted_text,
                images=images,
                metadata=metadata,
                mime_type="application/pdf",
                needs_vlm=needs_vlm,
            )

        except Exception as e:
            logger.error(f"Failed to load PDF {path}: {e}")
            raise


class PDFTextLoader(MediaLoader):
    """
    Alternative PDF loader focused on text extraction using Kreuzberg.

    Use this when you want high-quality text extraction from digital PDFs
    without needing images. Kreuzberg handles complex layouts better than
    simple PyMuPDF text extraction.
    """

    def can_handle(self, source: str | Path) -> bool:
        """Check if source is a PDF."""
        return Path(source).suffix.lower() in PDF_FORMATS

    async def load(self, source: str | Path) -> MediaContent:
        """Extract text from PDF using Kreuzberg."""
        try:
            import kreuzberg
        except ImportError:
            raise RuntimeError(
                "Text extraction requires kreuzberg. Install with: pip install kreuzberg"
            )

        path = Path(source)

        try:
            # Use Kreuzberg for text extraction
            # Disable OCR since we're just extracting digital text
            try:
                config = kreuzberg.ExtractionConfig(
                    force_ocr=False,
                    extract_tables=True,  # Kreuzberg can extract tables
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
                "original_format": "pdf",
                "filename": path.name,
                "extractor": "kreuzberg",
            }

            # Preserve structured outputs (tables, annotations, image
            # descriptions, keywords, …) so ingest can persist them as
            # Artifact rows. Primary text save behaviour is unchanged.
            # (#885)
            try:
                from fichero_server.loaders.kreuzberg_artifacts import (
                    extract_artifact_payloads,
                )

                payloads = extract_artifact_payloads(result)
                if payloads:
                    metadata["_kreuzberg_artifacts"] = payloads
            except Exception as exc:  # pragma: no cover — defensive
                logger.debug("Kreuzberg artifact extraction failed: %s", exc)

            # If we got good text, no VLM needed
            needs_vlm = len(result.content.strip()) < 100

            return MediaContent(
                source=str(path),
                text=result.content,
                images=[],  # No images - text only
                metadata=metadata,
                mime_type="application/pdf",
                needs_vlm=needs_vlm,
            )

        except Exception as e:
            logger.error(f"Failed to extract text from PDF {path}: {e}")
            raise
