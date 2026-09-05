"""
Document loader using Kreuzberg for Office documents and EPUBs.

Handles: DOCX, XLSX, PPTX, EPUB, RTF, ODT, ODS, ODP
"""

import logging
from pathlib import Path

from fichero_server.loaders import kreuzberg_cache  # noqa: F401 — env-var side effect
from fichero_server.loaders.base import MediaContent, MediaLoader
# RTF → text conversion lives in `rtf_text` so callers that only need the
# converter do not import Kreuzberg/pdfium with it (#4666). Re-exported here
# because importers, the views route, and the loader tests already name it.
from fichero_server.loaders.rtf_text import (  # noqa: F401
    _RTF_HEX_FULL_RE,
    _RTF_HEX_RUN_RE,
    _RTF_SKIP_GROUP_WORDS,
    _RTF_UNICODE_RE,
    _decode_rtf_hex_byte,
    _looks_like_text,
    _strip_rtf,
    decode_rtf_hex_escapes,
    to_plain_text,
)

# Bind pdfium and pre-import kreuzberg's FFI-callback dependencies before any
# extraction in this module can reach the Rust pipeline. Module scope on
# purpose: it must precede the lazy `import kreuzberg` below, and this module
# is NOT imported at engine startup, so the cost stays off the launch path.
kreuzberg_cache.prewarm_for_extraction()

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
TEXT_FORMATS = {
    ".txt", ".md", ".markdown", ".rst", ".html", ".htm", ".xml", ".csv", ".jsonl",
    # Subtitle / transcript files — plain text with timestamp markers.
    # Timestamps become indexable noise, but the dialog/transcript text
    # is what users search for.
    ".srt", ".vtt", ".sbv",
}

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
        raw = path.read_bytes()
        try:
            encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            text = raw.decode("cp1252")

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

            # Capture structured outputs (tables, slide text, image
            # descriptions, transcripts, …) so ingest can persist them as
            # Artifact rows. Strictly additive — primary text save is
            # unchanged. (#885)
            try:
                from fichero_server.loaders.kreuzberg_artifacts import (
                    extract_artifact_payloads,
                )

                payloads = extract_artifact_payloads(result)
                if payloads:
                    metadata["_kreuzberg_artifacts"] = payloads
            except Exception as exc:  # pragma: no cover — defensive
                logger.debug("Kreuzberg artifact extraction failed: %s", exc)

            content = result.content
            # Guard against Kreuzberg returning raw RTF markup for .rtf files
            # (observed when the internal extractor falls back on unsupported
            # variants).  _strip_rtf is a no-op on already-plain text.
            if suffix == ".rtf":
                content = _strip_rtf(content)

            return MediaContent(
                source=str(path),
                text=content,
                images=[],
                metadata=metadata,
                mime_type=result.mime_type or self._get_mime_type(suffix),
                needs_vlm=False,  # Text documents don't need VLM
            )

        except Exception as e:
            # Legacy binary Word is the one format where the primary extractor
            # rejects files the platform itself reads (#4215). Try textutil
            # before giving up; anything else raises exactly as before.
            if suffix == ".doc":
                fallback = self._load_with_textutil(path, primary_error=e)
                if fallback is not None:
                    return fallback
            logger.error(f"Failed to extract document {path}: {e}")
            raise

    def _load_with_textutil(
        self, path: Path, *, primary_error: Exception
    ) -> MediaContent | None:
        """macOS fallback for legacy OLE2 .doc, or None if it cannot help.

        kreuzberg rejects VALID pre-2007 .doc files with "Malformed MiniFAT
        (mini sector 0 pointed to twice)" — verified on a file macOS
        ``textutil`` both WROTE and reads back correctly, so the file is valid
        enough for the platform's own tooling and the objection is a
        strictness difference in the OLE container reader, not corruption.

        ``textutil`` ships with macOS: no new dependency, and it is the same
        component that produced the file. Non-macOS engines simply keep the
        original error — .doc is exactly what older archival material tends to
        be, so being able to read it on the platform Fichero targets is worth
        more than uniformity.
        """
        import subprocess

        textutil = Path("/usr/bin/textutil")
        if not textutil.exists():
            return None
        try:
            completed = subprocess.run(
                [str(textutil), "-convert", "txt", "-stdout", str(path)],
                capture_output=True,
                timeout=60,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            # Loud: the primary extractor already failed, so a silent second
            # failure would leave an empty extraction with no explanation.
            logger.warning(
                "textutil could not read legacy .doc %s (%s); original error: %s",
                path,
                exc,
                primary_error,
            )
            return None

        text = completed.stdout.decode("utf-8", errors="replace").strip()
        if not text or not _looks_like_text(text):
            # textutil treats input it cannot parse as PLAIN TEXT and happily
            # echoes the raw bytes back, so a genuinely corrupt .doc "succeeds"
            # with a screenful of NULs. Accepting that would be exactly the
            # silent substitution this fallback exists to avoid: keep the
            # primary error instead.
            logger.warning(
                "textutil returned no usable text for %s; original error: %s",
                path,
                primary_error,
            )
            return None

        logger.info(
            "Extracted legacy .doc %s via textutil after kreuzberg failed: %s",
            path.name,
            primary_error,
        )
        return MediaContent(
            source=str(path),
            text=text,
            images=[],
            metadata={
                "original_format": "doc",
                "filename": path.name,
                "extractor": "textutil",
                "extractor_fallback_reason": str(primary_error),
                "size_bytes": path.stat().st_size,
            },
            mime_type=self._get_mime_type(".doc"),
            needs_vlm=False,
        )

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
            ".jsonl": "application/x-ndjson",
        }
        return mime_types.get(suffix, "application/octet-stream")
