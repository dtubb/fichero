"""
Unified media loader that routes to appropriate specialized loaders.

Supported loaders:
- IIIF: URL-based IIIF manifests
- PDF: PyMuPDF for page rendering + text extraction
- Image: PIL + rawpy + system tools for HEIC/JXL
- Document: Kreuzberg for Office docs, EPUBs, plain text
"""

import asyncio
import logging
from pathlib import Path

from fichero_server.loaders.base import MediaContent, MediaLoader
from fichero_server.loaders.document_loader import DocumentLoader, ALL_DOCUMENT_FORMATS
from fichero_server.loaders.image_loader import ImageLoader, ALL_IMAGE_FORMATS
from fichero_server.loaders.iiif_loader import IIIFLoader
from fichero_server.loaders.pdf_loader import PDFLoader, PDF_FORMATS

logger = logging.getLogger(__name__)

# Docling disabled (requires PyTorch which dropped x86_64 macOS support in 2.6.0+)
# Check for optional Docling
# try:
#     from fichero_server.loaders.docling_loader import DoclingLoader, DOCLING_FORMATS
#     _HAS_DOCLING = DoclingLoader.is_available()
# except ImportError:
#     _HAS_DOCLING = False
#     DoclingLoader = None
#     DOCLING_FORMATS = set()

_HAS_DOCLING = False
DoclingLoader = None
DOCLING_FORMATS = set()


class UnifiedLoader:
    """
    Routes media loading to the appropriate specialized loader.

    Automatically detects file type and uses the best loader:
    - Images (JPG, PNG, TIFF, HEIC, RAW, etc.) → ImageLoader
    - PDFs → PDFLoader (PyMuPDF for images + text)
    - Office docs (DOCX, XLSX, PPTX) → DocumentLoader (Kreuzberg)
    - EPUBs → DocumentLoader (Kreuzberg)
    - IIIF manifests → IIIFLoader
    - Plain text (TXT, MD, etc.) → DocumentLoader
    """

    def __init__(
        self,
        pdf_dpi: int = 300,
        iiif_max_dimension: int = 1500,
        # use_docling: bool = True,  # Disabled - requires PyTorch (no x86_64 wheels)
    ):
        """
        Initialize unified loader.

        Args:
            pdf_dpi: Resolution for PDF page rendering
            iiif_max_dimension: Max dimension for IIIF image downloads
        """
        self.loaders: list[MediaLoader] = [
            IIIFLoader(
                max_dimension=iiif_max_dimension
            ),  # Check IIIF first (URL-based)
            PDFLoader(dpi=pdf_dpi),
            ImageLoader(),
        ]

        # Docling disabled (requires PyTorch which dropped x86_64 macOS support)
        # # Add Docling before DocumentLoader if available (default: on)
        # if use_docling and _HAS_DOCLING and DoclingLoader:
        #     self.loaders.append(DoclingLoader())
        #     logger.info("Docling loader enabled for structured document parsing")

        # DocumentLoader (Kreuzberg) handles everything else
        self.loaders.append(DocumentLoader())

    async def load(self, source: str | Path, hint: str | None = None) -> MediaContent:
        """
        Load media from any supported source.

        Args:
            source: File path or URL
            hint: Optional type hint ("image", "pdf", "document", "iiif")

        Returns:
            MediaContent with extracted text/images
        """
        source_str = str(source)

        # If hint provided, use specific loader
        if hint:
            loader = self._get_loader_by_hint(hint)
            if loader:
                logger.info(
                    f"Loading {source_str} with {loader.__class__.__name__} (hint)"
                )
                return await loader.load(source)

        # Auto-detect loader
        for loader in self.loaders:
            if loader.can_handle(source):
                logger.info(f"Loading {source_str} with {loader.__class__.__name__}")
                return await loader.load(source)

        # No loader found
        raise ValueError(
            f"No loader available for: {source_str}\n"
            f"Supported formats: {self._get_supported_formats()}"
        )

    def load_sync(self, source: str | Path, hint: str | None = None) -> MediaContent:
        """
        Synchronous wrapper for load().

        For use in non-async contexts.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Already in async context
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.load(source, hint))
                return future.result()
        else:
            return asyncio.run(self.load(source, hint))

    def can_handle(self, source: str | Path) -> bool:
        """Check if any loader can handle this source."""
        return any(loader.can_handle(source) for loader in self.loaders)

    def _get_loader_by_hint(self, hint: str) -> MediaLoader | None:
        """Get specific loader by type hint."""
        hint_map = {
            "image": ImageLoader,
            "pdf": PDFLoader,
            "document": DocumentLoader,
            "iiif": IIIFLoader,
        }

        # Docling disabled (requires PyTorch which dropped x86_64 macOS support)
        # # Add Docling if available
        # if _HAS_DOCLING and DoclingLoader:
        #     hint_map["docling"] = DoclingLoader

        loader_class = hint_map.get(hint.lower())
        if loader_class:
            for loader in self.loaders:
                if isinstance(loader, loader_class):
                    return loader

        return None

    def _get_supported_formats(self) -> str:
        """Get human-readable list of supported formats."""
        return (
            f"Images: {', '.join(sorted(ALL_IMAGE_FORMATS))}\n"
            f"PDFs: {', '.join(sorted(PDF_FORMATS))}\n"
            f"Documents: {', '.join(sorted(ALL_DOCUMENT_FORMATS))}\n"
            f"IIIF: URLs containing /manifest or /iiif/"
        )


# Convenience function
async def load_media(source: str | Path, hint: str | None = None) -> MediaContent:
    """
    Load media from any supported source.

    Convenience function that creates a UnifiedLoader and loads the content.

    Args:
        source: File path or URL
        hint: Optional type hint ("image", "pdf", "document", "iiif")

    Returns:
        MediaContent with extracted text/images

    Example:
        content = await load_media("/path/to/file.pdf")
        print(f"Pages: {content.page_count}")
        print(f"Text: {content.text[:100]}...")
    """
    loader = UnifiedLoader()
    return await loader.load(source, hint)
