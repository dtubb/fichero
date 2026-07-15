"""
Document loader using Kreuzberg for Office documents and EPUBs.

Handles: DOCX, XLSX, PPTX, EPUB, RTF, ODT, ODS, ODP
"""

import logging
import re
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
TEXT_FORMATS = {
    ".txt", ".md", ".markdown", ".rst", ".html", ".htm", ".xml", ".csv",
    # Subtitle / transcript files — plain text with timestamp markers.
    # Timestamps become indexable noise, but the dialog/transcript text
    # is what users search for.
    ".srt", ".vtt", ".sbv",
}

ALL_DOCUMENT_FORMATS = OFFICE_FORMATS | EBOOK_FORMATS | TEXT_FORMATS

# RTF header groups whose content should be discarded (they're tables/metadata,
# not body text).  Keys must be lowercase control words.
_RTF_SKIP_GROUP_WORDS = frozenset(
    {
        "fonttbl", "colortbl", "stylesheet", "info", "pict", "shppict",
        "wshad", "filetbl", "listtable", "listoverridetable",
    }
)

# Matches RTF hex-escape sequences: \'XX where XX are two hex digits.
_RTF_HEX_FULL_RE = re.compile(r"\\'([0-9a-fA-F]{2})")
_RTF_HEX_RUN_RE = re.compile(r"(?:\\'[0-9a-fA-F]{2})+")
_RTF_UNICODE_RE = re.compile(r"\\u(-?\d+)\?")


def _decode_rtf_hex_byte(m: "re.Match[str]") -> str:
    """Decode a single RTF \'XX byte via cp1252 (Windows-1252 / Latin-1 superset)."""
    try:
        return bytes([int(m.group(1), 16)]).decode("cp1252")
    except (UnicodeDecodeError, ValueError):
        return m.group(0)


def _strip_rtf(text: str) -> str:
    """Convert raw RTF markup to plain text.

    Uses a character-by-character state machine so nested groups ({\fonttbl
    {\f0 Arial;}}) are handled correctly without a new dependency.  Returns
    the string unchanged when it doesn't look like RTF.
    """
    stripped = text.lstrip()
    if not stripped.startswith("{\\rtf"):
        return text

    # Decode \'XX hex escapes BEFORE the state machine strips control chars.
    # Without this, \'f3 (ó) becomes bare "f3" because the state machine
    # consumes ' as an unknown control symbol and outputs the hex digits as
    # plain text.  Only the full \'XX form is decoded; the bare 'XX form
    # (no backslash) is NOT decoded because it matches legitimate apostrophes
    # in plain text ("class of '92", "the '49ers") and corrupts them. (#2505)
    def _decode_unicode(match: "re.Match[str]") -> str:
        value = int(match.group(1))
        return chr(value if value >= 0 else value + 65536)

    stripped = _RTF_UNICODE_RE.sub(_decode_unicode, stripped)
    codepage = re.search(r"\\ansicpg(\d+)", stripped)
    encoding = f"cp{codepage.group(1)}" if codepage else "cp1252"

    def _decode_hex_run(match: "re.Match[str]") -> str:
        raw = bytes(int(value, 16) for value in _RTF_HEX_FULL_RE.findall(match.group()))
        try:
            return raw.decode(encoding)
        except LookupError:
            return raw.decode("cp1252", errors="replace")
        except UnicodeDecodeError:
            return raw.decode(encoding, errors="replace")

    stripped = _RTF_HEX_RUN_RE.sub(_decode_hex_run, stripped)

    output: list[str] = []
    # skip_until_depth > 0: skip content until depth drops below this value.
    # Set when a header-group control word (\fonttbl etc.) is encountered;
    # cleared when the matching closing } brings depth back below that level.
    skip_until_depth = 0
    depth = 0
    i = 0
    n = len(stripped)

    while i < n:
        ch = stripped[i]

        if ch == "{":
            depth += 1
            i += 1

        elif ch == "}":
            depth -= 1
            if skip_until_depth and depth < skip_until_depth:
                skip_until_depth = 0
            i += 1

        elif ch == "\\":
            i += 1
            if i >= n:
                break

            if stripped[i].isalpha():
                # Control word: \word[-N][ ]
                j = i
                while j < n and stripped[j].isalpha():
                    j += 1
                word = stripped[i:j].lower()
                i = j
                # Skip optional numeric parameter
                if i < n and (stripped[i].isdigit() or stripped[i] == "-"):
                    while i < n and stripped[i] in "0123456789-":
                        i += 1
                # Skip optional single space delimiter
                if i < n and stripped[i] == " ":
                    i += 1

                if skip_until_depth:
                    continue

                if word in _RTF_SKIP_GROUP_WORDS:
                    # depth already incremented by the preceding {;
                    # skip everything until depth drops below current level.
                    skip_until_depth = depth
                elif word in ("par", "pard", "sect", "page"):
                    output.append("\n")
                elif word == "line":
                    output.append("\n")
                elif word == "tab":
                    output.append("\t")
                # All other control words (font, size, bold…) are formatting — skip.

            else:
                # Control symbol (\\, \{, \}, \~, \-, …)
                sym = stripped[i]
                i += 1
                if not skip_until_depth:
                    if sym == "\\":
                        output.append("\\")
                    elif sym == "{":
                        output.append("{")
                    elif sym == "}":
                        output.append("}")
                    elif sym == "~":
                        output.append(" ")  # non-breaking space
                    elif sym == "-":
                        output.append("­")  # soft hyphen
                    # Other control symbols are ignored

        else:
            if not skip_until_depth and depth >= 1:
                output.append(ch)
            i += 1

    result = "".join(output)
    result = re.sub(r" {2,}", " ", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


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
                from fichero.loaders.kreuzberg_artifacts import (
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
