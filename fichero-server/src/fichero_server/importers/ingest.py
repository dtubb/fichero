"""
File ingestion for Fichero.

Two modes:
- LINK: Reference external files with macOS bookmarks (default)
- COPY: Import files into library storage (uses APFS clones when possible)

Text extraction:
- extract_text=True uses loaders to extract text from PDFs, DOCX, etc.
- Extracted text goes into doc.page_content for search indexing

Usage:
    from fichero_server.importers.ingest import ingest_file, ingest_folder, IngestMode

    # Link external file (default - uses bookmarks)
    doc = ingest_file(Path("/Users/bob/docs/letter.pdf"))

    # With text extraction for search
    doc = ingest_file(Path("/path/to/doc.pdf"), extract_text=True)

    # Copy into library
    doc = ingest_file(Path("/path/to/file.jpg"), mode=IngestMode.COPY)

    # Batch import folder
    docs = ingest_folder(Path("/path/to/folder"), mode=IngestMode.LINK)

    # Ingest with specific parent folder
    folder = db.query(Document, doc_type=DocType.folder)[0]
    doc = ingest_file(path, parent_id=folder.id)
"""

from __future__ import annotations

import asyncio
import base64
import ctypes
import hashlib
import json
import logging
import mimetypes
import os
import shutil
import time
from datetime import datetime
from fichero_server.core.timeutil import utc_now
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Iterator
from uuid import uuid4

from fichero_server.importers.dataless import require_local_bytes
from fichero_server.models import Artifact, Document, DocType, FileType, Status

if TYPE_CHECKING:
    from fichero_server.db import Database

logger = logging.getLogger(__name__)


class _KreuzbergUnavailableError(RuntimeError):
    """Kreuzberg is not installed for PDF page extraction."""


class _KreuzbergExtractionError(RuntimeError):
    """Kreuzberg failed while extracting PDF pages."""


# File types that support text extraction via loaders
_TEXT_EXTRACTABLE = {
    FileType.pdf,
    FileType.word,
    FileType.text,
    FileType.epub,
    FileType.spreadsheet,
    FileType.presentation,
}


# =============================================================================
# Enums
# =============================================================================


class IngestMode(str, Enum):
    """How to handle file ingestion."""

    LINK = "link"  # Reference with macOS bookmark (file stays in place)
    COPY = "copy"  # Copy into library storage (file duplicated)
    MOVE = "move"  # Move into library storage (file relocated, original deleted)


# =============================================================================
# File Type Detection
# =============================================================================

# Extension to FileType mapping
_FILE_TYPE_MAP = {
    # Images
    ".jpg": FileType.image,
    ".jpeg": FileType.image,
    ".png": FileType.image,
    ".gif": FileType.image,
    ".webp": FileType.image,
    ".tiff": FileType.image,
    ".tif": FileType.image,
    ".bmp": FileType.image,
    ".heic": FileType.image,
    ".heif": FileType.image,
    ".jxl": FileType.image,
    ".avif": FileType.image,
    ".jp2": FileType.image,
    ".j2k": FileType.image,
    ".jpf": FileType.image,
    ".jpx": FileType.image,
    # RAW formats
    ".raw": FileType.image,
    ".cr2": FileType.image,
    ".cr3": FileType.image,
    ".nef": FileType.image,
    ".arw": FileType.image,
    ".dng": FileType.image,
    ".orf": FileType.image,
    ".rw2": FileType.image,
    # PDF
    ".pdf": FileType.pdf,
    # Audio
    ".mp3": FileType.audio,
    ".wav": FileType.audio,
    ".m4a": FileType.audio,
    ".aac": FileType.audio,
    ".flac": FileType.audio,
    ".ogg": FileType.audio,
    ".wma": FileType.audio,
    # Video
    ".mp4": FileType.video,
    ".mov": FileType.video,
    ".avi": FileType.video,
    ".mkv": FileType.video,
    ".webm": FileType.video,
    # Text. \\\`.rtf\\\` reads as text — Kreuzberg's RTF loader extracts plain
    # body text, no rich formatting passes through, but for full-text
    # search that's exactly what we want. \\\`.html\\\` / \\\`.htm\\\` / \\\`.xml\\\`
    # also map here so the loader extracts the textual content via
    # the document_loader pipeline.
    ".txt": FileType.text,
    ".md": FileType.text,
    ".markdown": FileType.text,
    ".rst": FileType.text,
    ".rtf": FileType.text,
    ".html": FileType.text,
    ".htm": FileType.text,
    ".xml": FileType.text,
    ".jsonl": FileType.text,
    # Subtitles / transcripts — searchable as plain text
    ".srt": FileType.text,
    ".vtt": FileType.text,
    ".sbv": FileType.text,
    # Word
    ".doc": FileType.word,
    ".docx": FileType.word,
    ".odt": FileType.word,
    # Spreadsheets
    ".csv": FileType.spreadsheet,
    ".xlsx": FileType.spreadsheet,
    ".xls": FileType.spreadsheet,
    ".ods": FileType.spreadsheet,
    # Presentations
    ".pptx": FileType.presentation,
    ".ppt": FileType.presentation,
    ".odp": FileType.presentation,
    # Ebooks
    ".epub": FileType.epub,
    ".mobi": FileType.epub,
}


def detect_file_type(path: Path) -> FileType:
    """Detect file type from extension.

    Args:
        path: Path to file

    Returns:
        Detected FileType, or FileType.other if unknown
    """
    suffix = path.suffix.lower()
    file_type = _FILE_TYPE_MAP.get(suffix, FileType.other)
    logger.debug(
        f"Detected file type for {path.name}: suffix='{suffix}' -> type={file_type.value}"
    )
    return file_type


# =============================================================================
# Single File Ingestion
# =============================================================================


def _resolve_default_db() -> Any:
    """
    Resolve legacy module-level db fallback for callers/tests that do not
    pass an explicit db argument.
    """
    from fichero_server import db as db_module

    candidate = getattr(db_module, "db", None)
    return candidate if hasattr(candidate, "save") else None


def ingest_file(
    path: Path,
    mode: IngestMode = IngestMode.LINK,
    parent_id: str | None = None,
    extract_metadata: bool = True,
    extract_text: bool = True,
    auto_embed: bool = True,
    save: bool = True,
    db: "Database | None" = None,
    package_path: Path | None = None,
    original_filename: str | None = None,
    known_checksum: str | None = None,
) -> Document:
    """Ingest a single file.

    Args:
        path: Path to file
        mode: LINK (bookmark) or COPY (import)
        parent_id: Parent collection ID
        extract_metadata: Run metadata extraction (size, checksum, etc.)
        extract_text: Use loaders to extract text content for search. Defaults
            to True so .md / .txt / .docx / .pdf-with-text files are searchable
            immediately after ingest without requiring an explicit workflow run
            (#881). The extraction is keyed on _TEXT_EXTRACTABLE so image-only
            files like .jpg / .png correctly skip the loader and need the
            Transcribe / OCR workflow path. Override to False for batch
            imports where text extraction is deferred to a later workflow.
        auto_embed: Create vector embedding in LanceDB after saving, so the
            doc is immediately reachable via semantic search. Defaults to
            True (#881 follow-up) — paired with the extract_text default,
            this means dropping a .md file in makes it both keyword AND
            semantically searchable without any further user action. Embedding
            runs only when `doc.page_content` is non-empty, so image-only
            files (no extracted text yet) don't get pointless empty vectors.
            Override to False for batch imports where embeddings are
            deferred to a background job.
        save: If True, save to database
        db: Database instance (required if save=True)
        package_path: Library package path for COPY mode (stores files in {package}/files/)

    Returns:
        Created Document
    """
    from fichero_server.bookmarks import create_bookmark

    raw_path = Path(path)
    if raw_path.is_symlink():
        raise ValueError(f"Refusing to ingest symlinked file: {raw_path}")
    path = raw_path.resolve()

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not path.is_file():
        raise ValueError(f"Not a file: {path}")

    # A cloud placeholder passes every check above — it "exists", and stat
    # reports the full logical size — but its bytes are not on this machine
    # (#4233). Refuse HERE so the failure is attributable to this one file and
    # lands in its ingest error, instead of surfacing later as a document that
    # will never render. LINK mode copies nothing, so nothing else would catch
    # it at all.
    require_local_bytes(path)

    if save and db is None:
        db = _resolve_default_db()
    if save and db is None:
        raise ValueError("db parameter required when save=True")

    # Determine file type
    file_type = detect_file_type(path)

    # Import bibliographic sidecars early so canonical citation data is
    # available before any LLM-based metadata extraction runs.
    companion_metadata = _load_companion_json(path) or {}
    bibliography_metadata = _load_bibliography_sidecar(path) or {}
    sidecar_metadata = {**companion_metadata, **bibliography_metadata} or None

    # Build metadata. Always record the ingest_mode explicitly (#603 Part 2)
    # so the frontend can show LINK / COPY / MOVE badges and branch the
    # delete-confirmation copy. Pre-fix docs without this key fall back to
    # bookmark presence: bookmark → LINK, no bookmark → COPY.
    # ``original_filename`` (#4471): set when ``path`` is a server-side TEMP
    # file for an upload — the real name the user's file had. The source name
    # is PROVENANCE in an archival tool: a page recorded as
    # ``fichero_upload_<random>.pdf`` has lost the fact that connects it to
    # the physical original, and nobody can cite a tempfile. When set, the
    # display name comes from it (BEFORE page children are created, so pages
    # inherit the real name too) and the temp path is NOT recorded as
    # source_path/source_folder/source_mtime — those would describe the
    # server's temp dir, which is a lie about origin, not provenance.
    display_name = original_filename or path.name
    metadata: dict = {"ingest_mode": mode.value}
    if original_filename:
        metadata["source_filename"] = original_filename
    else:
        metadata["source_path"] = str(path)
        try:
            stat = path.stat()
            metadata["source_folder"] = str(path.parent)
            metadata["source_mtime"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
        except Exception as exc:
            logger.debug("Could not record filesystem provenance for %s: %s", path, exc)

    if mode in (IngestMode.COPY, IngestMode.MOVE):
        # Copy file into library storage
        dest = (
            _copy_to_library(path)
            if package_path is None
            else _copy_to_library(path, package_path)
        )
        if save and db is not None and db.in_transaction:
            def remove_rolled_back_copy() -> None:
                try:
                    dest.unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning("Could not remove rolled-back copy %s: %s", dest, exc)

            db.add_after_rollback_hook(remove_rolled_back_copy)
        # Store the path RELATIVE to the library package root (e.g.
        # "files/nc/<id>_<name>.jpg") whenever the bytes land inside the
        # package. An absolute path bakes in the package's current name, so it
        # breaks the moment the user renames or moves the .fichero bundle
        # (#1663). A relative path is re-rooted against the live library root at
        # serve time by storage.resolve_source(). When there is no package
        # (legacy global storage), keep the absolute path.
        stored_path = str(dest)
        if package_path is not None:
            try:
                stored_path = str(dest.relative_to(Path(package_path)))
            except ValueError:
                # dest somehow landed outside the package — keep absolute.
                stored_path = str(dest)
        doc = Document(
            name=display_name,
            path=stored_path,
            doc_type=DocType.file,
            file_type=file_type,
            parent_id=parent_id,
            metadata=metadata,
            status=Status.pending,
        )
        content_path = dest

    else:
        # Link with bookmark
        bookmark = create_bookmark(path)
        if bookmark:
            metadata["bookmark"] = base64.b64encode(bookmark).decode()

        doc = Document(
            name=display_name,
            path=str(path),
            doc_type=DocType.file,
            file_type=file_type,
            parent_id=parent_id,
            metadata=metadata,
            status=Status.pending,
        )
        content_path = path

    # Extract metadata if requested
    if extract_metadata:
        _extract_file_metadata(
            doc, content_path, sidecar_path=path, known_checksum=known_checksum
        )

    if sidecar_metadata:
        doc.source_metadata = sidecar_metadata

    # Extract text content using loaders.  On failure _extract_text_content
    # sets doc.status=Status.failed and re-raises so we can still persist
    # the document with its error metadata (#881: fail loud, not silent None).
    text_extraction_failed = False
    if extract_text and file_type in _TEXT_EXTRACTABLE:
        try:
            _extract_text_content(doc, content_path)
        except Exception as _text_exc:
            # Ensure the document always reflects the failure even if the
            # exception was raised before _extract_text_content could set
            # these fields (e.g., during testing with a mock).
            text_extraction_failed = True
            doc.status = Status.failed
            doc.metadata.setdefault("text_extracted", False)
            doc.metadata.setdefault("text_extraction_error", str(_text_exc))

    if save:
        db.save(doc)
        if text_extraction_failed:
            logger.warning(
                "Saved document with failed text extraction: %s", path.name
            )
        else:
            logger.info("Ingested: %s (%s)", path.name, mode.value)

        # Persist any structured outputs Kreuzberg surfaced alongside the
        # primary text (tables, slide text, image descriptions, transcripts).
        # (#885)
        _save_pending_artifacts(doc, db)

        # Create embedding for search (only when text extraction succeeded)
        if auto_embed and doc.page_content:
            db.embed(doc)

        # PDFs are containers of pages. Create a child Document for each page
        # so workflows (transcribe, extract, etc.) can fan out per-page and
        # each page is searchable on its own.
        if file_type == FileType.pdf and not text_extraction_failed:
            _create_pdf_page_children(doc, content_path, db, auto_embed=auto_embed)

        _touch_ancestor_documents(db, doc.parent_id)

        # MOVE becomes destructive only after every database write for this
        # file commits. If extraction, page creation, embedding, or commit
        # fails, the source remains available for a safe retry (#4203).
        if mode == IngestMode.MOVE:
            def delete_original() -> None:
                try:
                    path.unlink()
                    logger.info("Moved file (original deleted): %s", path)
                except Exception as exc:
                    logger.warning("Failed to delete original file after move: %s", exc)
                    doc.status = Status.failed
                    doc.metadata["ingest_error"] = (
                        f"Stored copy committed, but the source could not be deleted: {exc}"
                    )
                    try:
                        db.save(doc)
                    except Exception as save_exc:  # pragma: no cover - last-resort log
                        logger.error(
                            "Could not persist move cleanup failure for %s: %s",
                            path,
                            save_exc,
                        )

            db.add_after_commit_hook(delete_original)

    return doc


def _load_bibliography_sidecar(path: Path) -> dict[str, Any] | None:
    """Load a same-stem bibliography sidecar if one exists."""
    from fichero_server.bibliography.importers import read_folder_sidecars, read_sidecar

    entries = read_sidecar(path)
    if entries:
        return entries[0]

    # Folder-level sidecar fallback (references.bib / zotero-export.json).
    entries = read_folder_sidecars(path)
    if not entries:
        return None

    target_name = path.name.lower()
    target_stem = path.stem.lower()
    for entry in entries:
        metadata = entry.get("metadata") if isinstance(entry, dict) else None
        filename = ""
        if isinstance(metadata, dict):
            filename = str(metadata.get("filename") or "").strip().lower()
        title = str(entry.get("title") or "").strip().lower() if isinstance(entry, dict) else ""
        if filename and filename == target_name:
            return entry
        if title and (title == target_stem or target_stem in title):
            return entry

    return None


def _load_companion_json(path: Path) -> dict[str, Any] | None:
    """Load downloader metadata stored as ``<primary filename>.json``."""
    sidecar = path.with_name(f"{path.name}.json")
    if not sidecar.is_file():
        return None
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
        logger.warning("Ignoring non-object companion metadata: %s", sidecar)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        logger.warning("Failed to parse companion metadata %s: %s", sidecar, exc)
    return None


def _kreuzberg_pdf_pages(path: Path) -> list[dict[str, Any]]:
    """Extract per-page records from a PDF via Kreuzberg.

    Returns a list of page dicts (``page_number``, ``content``, ``is_blank``,
    …). Missing Kreuzberg and extractor failures raise distinct internal
    errors so callers can surface the real reason instead of collapsing them
    into "no pages" (#3135).
    """
    try:
        from kreuzberg import ExtractionConfig, PageConfig, extract_file_sync
    except ImportError as exc:
        raise _KreuzbergUnavailableError(str(exc)) from exc

    try:
        cfg = ExtractionConfig(pages=PageConfig(extract_pages=True))
        result = extract_file_sync(str(path), None, cfg)
    except Exception as exc:
        raise _KreuzbergExtractionError(str(exc)) from exc

    return result.pages or []


def _page_records_have_text(records: list[dict[str, Any]]) -> int:
    """How many of these page records carry non-empty text."""
    return sum(1 for record in records if (record.get("content") or "").strip())


def _choose_pdf_page_records(
    kreuzberg_records: list[dict[str, Any]],
    fitz_records: list[dict[str, Any]],
    kreuzberg_reason: str = "returned no pages",
) -> tuple[list[dict[str, Any]], str | None]:
    """Pick the usable split, and say when the first extractor failed (#4555).

    "No pages" is not the only way Kreuzberg fails. The shipped app extracts
    its bundled pdfium to ``Data/tmp/kreuzberg-pdfium/`` and dlopens it, which
    Gatekeeper blocks; extraction then returns the right NUMBER of page records
    with EMPTY content. The old gate was ``not page_records``, false in that
    case, so the fitz fallback never ran: every page was stamped
    ``is_blank: true``, the PDF had no searchable text, and per-page
    transcription had nothing to work from.

    The distinction that must be preserved is a genuine SCAN, which also has no
    text layer and for which ``is_blank: true`` is the correct answer. The two
    are told apart by asking fitz. Text where Kreuzberg found none means
    Kreuzberg failed; no text from either means the page really is imagery and
    NOTHING should be reported as broken — a warning on every scan trains
    everyone to ignore the warning that matters.

    Returns ``(records, reason)`` where a non-nil ``reason`` is the loud line
    the caller must log.
    """
    kreuzberg_text = _page_records_have_text(kreuzberg_records)
    fitz_text = _page_records_have_text(fitz_records)

    if not kreuzberg_records:
        if fitz_records:
            return fitz_records, f"Kreuzberg {kreuzberg_reason}"
        return [], None

    if kreuzberg_text > 0:
        return kreuzberg_records, None

    # Kreuzberg returned pages but no text on any of them.
    if fitz_text > 0:
        return fitz_records, (
            f"Kreuzberg returned {len(kreuzberg_records)} page(s) with NO text "
            f"on any of them; fitz recovered text on {fitz_text}/"
            f"{len(fitz_records)} page(s)"
        )

    # Both agree: no text layer. That is a fact about the pages, not a defect.
    # Keep Kreuzberg's records — they may carry per-page artifacts fitz never
    # produced.
    return kreuzberg_records, None


def _create_pdf_page_children(
    parent_doc: Document,
    path: Path,
    db: Database,
    *,
    auto_embed: bool = False,
) -> list[Document]:
    """Create one child Document per PDF page with extracted per-page text.

    Each child has:
        - doc_type = DocType.page
        - parent_id = parent PDF Document id
        - sequence = 1-based page number
        - page_content = extracted text for that page

    Pages are real DB entities so workflows can iterate per-page, search can
    index per-page, and future features (highlights, annotations) have a
    place to hang off.

    Full-size page thumbnails are rendered on-demand client-side via PDFKit
    rather than at ingest time (avoids ~200 pages × ~500ms × large disk use
    for archival PDFs).
    """
    # Open the PDF once with fitz (PyMuPDF) up front: it provides page labels,
    # the authoritative page count, AND a second splitter to fall back on when
    # Kreuzberg fails. A PDF is a CONTAINER of pages — a multi-page PDF left
    # unsplit would later be transcribed whole-doc onto the parent (#2430), so
    # the split must never fail silently. (no-silent-fallback)
    pdf_doc = None
    pdf_has_named_labels = False
    fitz_page_count = 0
    try:
        import fitz  # PyMuPDF

        pdf_doc = fitz.open(str(path))
        pdf_has_named_labels = bool(pdf_doc.get_page_labels())
    except Exception as exc:
        logger.debug("fitz unavailable for %s: %s", path, exc)
    if pdf_doc is not None:
        try:
            fitz_page_count = pdf_doc.page_count
        except Exception as exc:
            logger.debug("fitz page_count unavailable for %s: %s", path, exc)

    kreuzberg_reason = "returned no pages"
    try:
        page_records = _kreuzberg_pdf_pages(path)
    except _KreuzbergUnavailableError as exc:
        kreuzberg_reason = f"dependency missing ({exc})"
        page_records = []
    except _KreuzbergExtractionError as exc:
        kreuzberg_reason = f"extraction failed ({exc})"
        page_records = []

    # #4555: build the fitz split whenever Kreuzberg gave us nothing usable —
    # no pages at all, or pages with no text on any of them — then let
    # `_choose_pdf_page_records` decide which to keep and whether anything
    # actually failed. The all-blank case is the shipped-app pdfium block:
    # Gatekeeper refuses the copy kreuzberg extracts to Data/tmp/, and
    # extraction returns the right page COUNT with empty content.
    _kreuzberg_records = page_records
    _fitz_records: list[dict[str, Any]] = []
    if (
        _page_records_have_text(_kreuzberg_records) == 0
        and pdf_doc is not None
        and fitz_page_count >= 1
    ):
        for _i in range(fitz_page_count):
            try:
                _content = pdf_doc[_i].get_text() or ""
            except Exception as _pexc:
                logger.debug(
                    "fitz text extract failed for %s p%d: %s",
                    path.name,
                    _i + 1,
                    _pexc,
                )
                _content = ""
            _fitz_records.append(
                {
                    "page_number": _i + 1,
                    "content": _content,
                    "is_blank": not _content.strip(),
                }
            )

    page_records, _fallback_reason = _choose_pdf_page_records(
        _kreuzberg_records, _fitz_records, kreuzberg_reason
    )
    if _fallback_reason:
        logger.warning(
            "%s for %s — using the fitz split instead "
            "(no-silent-fallback, #2430/#4555)",
            _fallback_reason,
            path.name,
        )

    if not page_records:
        # Both splitters failed. Surface loudly and stamp the parent so the
        # failure is diagnosable; downstream per-page tools refuse to transcribe
        # an unsplit multi-page PDF onto the parent (#2430).
        logger.error(
            "PDF page-splitting FAILED for %s (Kreuzberg + fitz both produced "
            "no pages); leaving unsplit. Per-page tools will refuse whole-doc "
            "transcription onto the parent (#2430).",
            path.name,
        )
        if isinstance(parent_doc.metadata, dict):
            parent_doc.metadata["pdf_page_split_failed"] = True
            try:
                db.save(parent_doc)
            except Exception as _serr:
                logger.debug(
                    "Could not stamp pdf_page_split_failed on %s: %s",
                    parent_doc.id,
                    _serr,
                )
        if pdf_doc is not None:
            pdf_doc.close()
        return []

    pages: list[Document] = []
    # #4395: count embedding OUTCOMES BY REASON, not just successes. One
    # warning per document is thousands of unread lines on a real import;
    # a single line naming the causes is what answers "are embeddings
    # working?" without anyone reading code.
    embed_counts: dict[str, int] = {"embedded": 0}
    try:
        for page_index, page_dict in enumerate(page_records):
            page_number = page_dict.get("page_number") or (len(pages) + 1)
            page_label = (
                _page_label_for(pdf_doc, page_index)
                if pdf_doc is not None and pdf_has_named_labels
                else None
            )
            content = page_dict.get("content") or ""
            page_doc = Document(
                parent_id=parent_doc.id,
                doc_type=DocType.page,
                file_type=None,  # a page is not a file in itself
                name=f"{parent_doc.name} - Page {page_number}",
                sequence=page_number,
                page_label=page_label,
                status=Status.completed,
                page_content=content if content else None,
                metadata={
                    "pdf_parent_id": parent_doc.id,
                    "pdf_parent_name": parent_doc.name,
                    "pdf_path": str(path),  # so frontend can render page thumbnail locally
                    "page_number": page_number,
                    "is_blank": bool(page_dict.get("is_blank")),
                    "text_extracted": bool(content),
                    "text_length": len(content),
                },
            )
            db.save(page_doc)

            # Persist per-page structured outputs (tables, image OCR /
            # descriptions) as artifacts on the page Document. (#885)
            _save_pdf_page_artifacts(page_doc, page_dict, db)

            # Capture the page's existing text-layer geometry (#4418). Free:
            # the rectangles are already in the file and we are already
            # holding the page open.
            _save_pdf_text_layer_geometry(page_doc, pdf_doc, page_index, db)

            if auto_embed and page_doc.page_content:
                try:
                    if db.embed(page_doc):
                        embed_counts["embedded"] += 1
                    else:
                        outcome = getattr(db, "last_embed_outcome", None)
                        reason = getattr(outcome, "reason", None) or "unknown"
                        embed_counts[reason] = embed_counts.get(reason, 0) + 1
                except Exception as exc:
                    logger.debug("Embedding failed for page %s: %s", page_number, exc)
                    embed_counts["embedding_failed"] = (
                        embed_counts.get("embedding_failed", 0) + 1
                    )

            _touch_ancestor_documents(db, page_doc.parent_id)

            pages.append(page_doc)
    finally:
        if pdf_doc is not None:
            pdf_doc.close()

    _log_embed_summary(embed_counts, path.name, len(pages), auto_embed=auto_embed)
    logger.info("Created %d page children for PDF %s", len(pages), path.name)
    return pages


def _log_embed_summary(
    counts: dict[str, int],
    source_name: str,
    page_count: int,
    *,
    auto_embed: bool,
) -> None:
    """Report embedding outcomes for one import, by reason (#4395).

    A library reached 669 documents with text and 12 embeddings without
    anything saying so, because every failure was one `logger.warning` the
    caller discarded. This states the outcome once per import, and escalates
    when the shape says the LIBRARY is broken rather than a document being
    unsuitable: if pages were meant to be embedded and NONE were, that is not
    a partially successful import, and it must not read like one.
    """
    if not auto_embed:
        return
    embedded = counts.get("embedded", 0)
    failures = {k: v for k, v in counts.items() if k != "embedded" and v}
    attempted = embedded + sum(failures.values())
    if not attempted:
        return

    detail = ", ".join(f"{reason}={count}" for reason, count in sorted(failures.items()))
    if embedded == 0:
        logger.error(
            "EMBEDDINGS: %s — 0 of %d page(s) embedded (%s). Nothing imported "
            "from this file is semantically searchable. This is an "
            "infrastructure failure, not a per-document skip.",
            source_name,
            attempted,
            detail or "no reason recorded",
        )
    elif failures:
        logger.warning(
            "EMBEDDINGS: %s — %d/%d page(s) embedded; %s",
            source_name,
            embedded,
            attempted,
            detail,
        )
    else:
        logger.info(
            "EMBEDDINGS: %s — %d/%d page(s) embedded",
            source_name,
            embedded,
            page_count,
        )


#: Artifact type carrying a page's text-region geometry (#4418).
PDF_TEXT_GEOMETRY_ARTIFACT = "text_geometry"


def _save_pdf_text_layer_geometry(
    page_doc: Document,
    pdf_doc: Any,
    page_index: int,
    db: Database,
) -> None:
    """Persist the page's text-layer regions as a geometry artifact (#4418).

    A PDF with a text layer already carries every word and its rectangle; the
    loader flattened that to a string and dropped the coordinates. Reading it
    here costs nothing — the document is already open — and gives the preview
    overlay a real data source for born-digital PDFs without any model,
    workflow or new pipeline.

    An artifact is written even when the page has NO text layer, carrying zero
    boxes and ``pdf_text_layer_present = False``. That is deliberate: absence
    of the artifact then means "never processed", while its presence with the
    flag false means "no geometry available for this page" — a scan. Writing
    nothing in both cases would make a scanned page indistinguishable from an
    unprocessed one, and the overlay could only show an empty box list, which
    reads as "nothing was recognised" (#4418).

    Best-effort: geometry is a bonus on the import path and must never fail an
    import that otherwise succeeded.
    """
    if pdf_doc is None:
        return
    try:
        from fichero_server.media.ocr_geometry import from_pymupdf_page

        geometry = from_pymupdf_page(pdf_doc[page_index], page_index=page_index)
        db.save(
            Artifact(
                document_id=page_doc.id,
                artifact_type=PDF_TEXT_GEOMETRY_ARTIFACT,
                content=geometry.text,
                data={"box_count": len(geometry.boxes)},
                ocr_geometry=geometry,
                provider="pymupdf",
            )
        )
    except Exception as exc:
        logger.warning(
            "text-layer geometry capture failed for %s page %d (import "
            "continues; the page simply has no geometry artifact): %s",
            page_doc.id,
            page_index + 1,
            exc,
        )


def _page_label_for(pdf_doc: Any, page_index: int) -> str | None:
    """Return the PDF-defined label for a page, or ``None`` when unavailable."""
    try:
        label = pdf_doc[page_index].get_label()
    except Exception as exc:
        logger.debug("Failed to read PDF page label for index %d: %s", page_index, exc)
        return None

    if not isinstance(label, str):
        return None

    label = label.strip()
    return label or None


def _copy_to_library(source: Path, package_path: Path | None = None) -> Path:
    """Copy file to library storage.

    Uses APFS clonefile() for instant copies on same volume.
    Falls back to shutil.copy2() for cross-volume copies.

    Args:
        source: Source file path
        package_path: Library package path (stores in {package}/files/)
                     If None, falls back to global storage for backward compat

    Returns:
        Destination path in library
    """
    from fichero_server.db.storage import settings

    # Create sharded destination directory
    shard = source.stem[:2].lower() if len(source.stem) >= 2 else "00"

    if package_path:
        # Multi-library: Store in package
        dest_dir = package_path / "files" / shard
    else:
        # Backward compatibility: Global storage
        dest_dir = settings.base_path / "imported" / shard

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    unique_prefix = uuid4().hex[:8]
    prefix = f"{unique_prefix}_"
    name_max = os.pathconf(dest_dir, "PC_NAME_MAX")
    suffix = source.suffix
    stem_budget = name_max - len(os.fsencode(prefix + suffix))
    stored_stem = ""
    for character in source.stem:
        if len(os.fsencode(stored_stem + character)) > stem_budget:
            break
        stored_stem += character
    dest = dest_dir / f"{prefix}{stored_stem}{suffix}"

    # Try APFS clone first (macOS only, instant, no disk space until modified)
    if _try_apfs_clone(source, dest):
        logger.debug("APFS clone: %s", source.name)
        _verify_copied(source, dest)
        return dest

    # Fallback to regular copy
    shutil.copy2(source, dest)
    logger.debug("Copied: %s", source.name)
    _verify_copied(source, dest)
    return dest


def _verify_copied(source: Path, dest: Path) -> None:
    """Confirm the copy actually landed, by size (#4218).

    Nothing checked this before: `shutil.copy2` returning without raising was
    treated as proof, and `clonefile` returning 0 likewise. Neither is. On a
    slow or dropping network volume a copy can end short without raising, and
    the consequence is worse than a bad checksum — the checksum is computed
    from the DESTINATION, so a truncated copy is hashed as-is and recorded as
    authoritative. The record is internally consistent and silently wrong;
    there is no notion of a correct checksum to disagree with.

    Raising here is what makes the failure REACHABLE: the folder walk already
    catches it, marks the document `Status.failed` with an `ingest_error`, and
    the #4203 retry picks it up. That machinery existed and this class of
    failure never got to it.

    Size, deliberately NOT a checksum comparison: re-reading both files would
    double read I/O on the path just taken to 926 files/sec, to catch what a
    size check already catches nearly always. Do not "upgrade" this to a hash.
    """
    try:
        source_size = source.stat().st_size
        dest_size = dest.stat().st_size
    except OSError as exc:
        raise OSError(f"copy verification failed for {source.name}: {exc}") from exc

    if source_size != dest_size:
        raise OSError(
            f"copy of {source.name} is incomplete: source {source_size} bytes, "
            f"destination {dest_size} bytes"
        )


def _try_apfs_clone(source: Path, dest: Path) -> bool:
    """Attempt APFS clonefile() for instant copy.

    Returns True if successful, False otherwise.
    """
    try:
        libc = ctypes.CDLL("libc.dylib")
        # clonefile(const char *src, const char *dst, int flags)
        result = libc.clonefile(
            str(source).encode(),
            str(dest).encode(),
            0,  # flags = 0
        )
        return result == 0
    except Exception:
        return False


def _extract_file_metadata(
    doc: Document,
    path: Path,
    *,
    sidecar_path: Path | None = None,
    known_checksum: str | None = None,
) -> None:
    """Extract basic metadata from file.

    Updates doc.metadata in place.
    """
    # The file being absent or unreadable is NOT a metadata problem, and must
    # not be swallowed (#4218). Previously the broad `except` below caught it,
    # logged a warning and returned normally, so the document was saved with
    # `Status.pending`, no checksum and no error metadata — a database row
    # pointing at a file that is not there, indistinguishable from a healthy
    # import. Raising routes it to the same failed-stub + retry path as any
    # other ingest error.
    stat = path.stat()
    doc.metadata["file_size"] = stat.st_size
    # Folder ingest already hashed this file for the skip test — reuse it
    # (2026-08-09): the double SHA-256 was a full second read of every file.
    doc.metadata["checksum"] = known_checksum or _file_checksum(path)

    # Everything below is genuinely best-effort: a corrupt EXIF block or an
    # unparseable header should not fail an import whose bytes are fine.
    try:
        mime_type, _ = mimetypes.guess_type(str(path))
        if mime_type:
            doc.metadata["mime_type"] = mime_type

        # Image dimensions (if applicable)
        if doc.file_type == FileType.image:
            _extract_image_metadata(doc, path, sidecar_path=sidecar_path)

    except ValueError:
        raise
    except Exception as e:
        logger.warning("Metadata extraction failed for %s: %s", path, e)


def _file_checksum(path: Path, algorithm: str = "sha256") -> str:
    """Calculate file checksum.

    Reads file in chunks to handle large files.
    """
    hasher = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _extract_image_metadata(
    doc: Document, path: Path, *, sidecar_path: Path | None = None
) -> None:
    """Extract image dimensions and XMP sidecar metadata.

    Updates doc.metadata in place.
    """
    try:
        from fichero_server.loaders.image_loader import UnsafeImageError, open_image_checked
        from fichero_server.loaders.xmp_loader import parse_xmp_sidecar, apply_xmp_to_document

        with open_image_checked(path) as img:
            doc.metadata["width"] = img.width
            doc.metadata["height"] = img.height

            # EXIF data
            if hasattr(img, "_getexif") and img._getexif():
                exif = img._getexif()
                if exif:
                    # Extract common EXIF fields
                    # 306 = DateTime, 271 = Make, 272 = Model
                    if 306 in exif:
                        doc.metadata["exif_datetime"] = exif[306]
                    if 271 in exif:
                        doc.metadata["exif_make"] = exif[271]
                    if 272 in exif:
                        doc.metadata["exif_model"] = exif[272]

        companion = sidecar_path or path

        # Parse XMP sidecar if present
        xmp_data = parse_xmp_sidecar(companion)
        if xmp_data:
            apply_xmp_to_document(doc, xmp_data)
            logger.debug(
                f"Applied XMP sidecar for {path.name}: {list(xmp_data.keys())}"
            )

        # Parse .iffy.json sidecar if present
        iffy_data = _parse_iffy_sidecar(companion)
        if iffy_data:
            _apply_iffy_to_document(doc, iffy_data)
            logger.debug(
                f"Applied .iffy.json sidecar for {path.name}: {list(iffy_data.keys())}"
            )

    except ImportError:
        logger.debug("Pillow not available for image metadata")
    except UnsafeImageError:
        raise
    except Exception as e:
        logger.debug("Image metadata extraction failed: %s", e)


def _extract_text_content(doc: Document, path: Path) -> None:
    """Extract text content using loaders.

    Uses the unified loader system to extract text from PDFs, DOCX, etc.
    Sets doc.page_content with extracted text.
    """
    try:
        from fichero_server.loaders import load_media

        # Run async loader in sync context
        content = _run_async(load_media(path))

        if content and content.text:
            doc.page_content = content.text
            doc.metadata["text_extracted"] = True
            doc.metadata["text_length"] = len(content.text)
            logger.debug("Extracted %s chars from %s", len(content.text), path.name)
        else:
            doc.metadata["text_extracted"] = False

        # Stash structured artifact payloads (Kreuzberg tables, slide text,
        # transcripts, image descriptions) for post-save persistence; we
        # need doc.id to exist before we can attach Artifact rows. (#885)
        if content and content.metadata:
            payloads = content.metadata.get("_kreuzberg_artifacts")
            if payloads:
                doc.metadata["_pending_artifacts"] = payloads

    except ImportError as e:
        logger.debug("Loader not available: %s", e)
    except Exception as e:
        # Fail loud (#881): record the error on the document so callers and the
        # DB can surface it rather than silently leaving page_content=None.
        logger.warning("Text extraction failed for %s: %s", path, e)
        doc.metadata["text_extracted"] = False
        doc.metadata["text_extraction_error"] = str(e)
        doc.status = Status.failed
        raise  # propagate so ingest_file / ingest_folder can react


def _save_pending_artifacts(doc: Document, db: Database) -> int:
    """Persist any artifact payloads pinned to ``doc.metadata`` as Artifact rows.

    Payloads come from Kreuzberg's structured outputs (tables, slide text,
    transcripts, image descriptions, …) — see
    :mod:`fichero_server.loaders.kreuzberg_artifacts`. Strictly additive: primary
    text save behaviour is unchanged. (#885)
    """
    payloads = doc.metadata.pop("_pending_artifacts", None)
    if not payloads:
        return 0

    from fichero_server.models import Artifact

    saved = 0
    for payload in payloads:
        try:
            db.save(
                Artifact(
                    document_id=doc.id,
                    artifact_type=payload.get("artifact_type", "kreuzberg_unknown"),
                    content=payload.get("content"),
                    data=payload.get("data"),
                    provider="kreuzberg",
                )
            )
            saved += 1
        except Exception as exc:
            logger.warning(
                "Failed to save kreuzberg artifact (%s) for %s: %s",
                payload.get("artifact_type"),
                doc.id,
                exc,
            )
    if saved:
        logger.debug("Saved %d kreuzberg artifacts for %s", saved, doc.name)
    return saved


def _save_pdf_page_artifacts(
    page_doc: Document,
    page_dict: dict[str, Any],
    db: Database,
) -> int:
    """Persist per-page Kreuzberg structured outputs as Artifact rows.

    ``page_dict`` is a Kreuzberg ``PageContent`` (TypedDict). Translates
    its ``tables`` and ``images`` (OCR / description) into ``Artifact`` rows
    on the page ``Document``. (#885)
    """
    from fichero_server.loaders.kreuzberg_artifacts import (
        KREUZBERG_IMAGE_DESCRIPTION,
        KREUZBERG_TABLE,
    )
    from fichero_server.models import Artifact

    saved = 0
    tables = page_dict.get("tables") or []
    for idx, table in enumerate(tables):
        cells = getattr(table, "cells", None)
        markdown = getattr(table, "markdown", None)
        page_number = getattr(table, "page_number", page_dict.get("page_number"))
        if not cells and not markdown:
            continue
        try:
            db.save(
                Artifact(
                    document_id=page_doc.id,
                    artifact_type=KREUZBERG_TABLE,
                    content=markdown if isinstance(markdown, str) else None,
                    data={
                        "table_index": idx,
                        "page_number": page_number,
                        "cells": cells,
                        "markdown": markdown,
                    },
                    provider="kreuzberg",
                )
            )
            saved += 1
        except Exception as exc:
            logger.warning("Failed to save page table artifact: %s", exc)

    images = page_dict.get("images") or []
    for idx, image in enumerate(images):
        description = image.get("description") if isinstance(image, dict) else None
        ocr_result = image.get("ocr_result") if isinstance(image, dict) else None
        ocr_text = getattr(ocr_result, "content", None) if ocr_result else None
        if not description and not ocr_text:
            continue
        parts = [p for p in (description, ocr_text) if p]
        try:
            db.save(
                Artifact(
                    document_id=page_doc.id,
                    artifact_type=KREUZBERG_IMAGE_DESCRIPTION,
                    content="\n\n".join(parts) if parts else None,
                    data={
                        "image_index": idx,
                        "page_number": page_dict.get("page_number"),
                        "description": description,
                        "ocr_text": ocr_text,
                    },
                    provider="kreuzberg",
                )
            )
            saved += 1
        except Exception as exc:
            logger.warning("Failed to save page image artifact: %s", exc)

    return saved


def _run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run async coroutine in sync context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        # Already in async context - use thread pool
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


# =============================================================================
# Folder Ingestion
# =============================================================================


_INGEST_BATCH_SIZE = 100


def ingest_folder(
    folder: Path,
    mode: IngestMode = IngestMode.LINK,
    parent_id: str | None = None,
    recursive: bool = True,
    create_collection: bool = True,
    extract_text: bool = True,
    auto_embed: bool = True,
    on_progress: Callable[[int, int], None] | None = None,
    on_document: "Callable[[Document], None] | None" = None,
    should_cancel: Callable[[], bool] | None = None,
    db: "Database | None" = None,
    package_path: Path | None = None,
) -> list[Document]:
    """Ingest all files from a folder.

    Args:
        folder: Folder to ingest
        mode: LINK or COPY
        parent_id: Parent collection ID (overrides create_collection)
        recursive: If True, ingest subdirectories
        create_collection: If True, create a collection for the folder
        extract_text: Extract text content using loaders
        auto_embed: Create embeddings for search
        on_progress: Progress callback (current, total) — invoked after every
            file (successful, skipped, or failed) so the caller can advance a
            progress bar.
        on_document: Per-document callback invoked once for each persisted
            folder, file, or failed-file stub. The folder
            ingest route uses this to emit a ``document.created`` change event
            per file so the sidebar populates incrementally instead of waiting
            for the whole import to finish (#4065). Skipped unchanged files do
            not fire it.
        should_cancel: Checked between files. Already committed documents remain
            coherent and a retry skips their unchanged source checksums.
        db: Database instance (required)
        package_path: Library package path for COPY mode

    Returns:
        List of created Documents
    """
    raw_folder = Path(folder)
    if raw_folder.is_symlink():
        raise ValueError(f"Refusing to ingest symlinked folder: {raw_folder}")
    folder = raw_folder.resolve()

    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")

    if not folder.is_dir():
        raise ValueError(f"Not a folder: {folder}")

    if db is None:
        db = _resolve_default_db()
    if db is None:
        raise ValueError("db parameter is required")

    if should_cancel and should_cancel():
        return []

    def notify_document(doc: Document) -> None:
        if on_document is None:
            return
        try:
            on_document(doc)
        except Exception as exc:  # pragma: no cover - defensive callback seam
            logger.warning("on_document callback failed: %s", exc)

    # Create folder Document, nested under the caller's parent_id if
    # one was given. Previously the `and not parent_id` guard caused
    # folder drops with a target to import files FLAT into the target
    # (#610): dropping `myFolder/` onto `Inbox/` landed the files
    # directly in Inbox without a container row. Now the folder always
    # gets its own Document when `create_collection=True`; callers that
    # explicitly want files imported flat can pass `create_collection=False`.
    folder_id = parent_id
    if create_collection:
        existing_roots = db.query(Document, parent_id=parent_id, name=folder.name)
        folder_doc = next(
            (
                doc
                for doc in existing_roots
                if doc.doc_type == DocType.folder and doc.path == str(folder)
            ),
            None,
        )
        if folder_doc is None:
            folder_doc = Document(
                name=folder.name,
                path=str(folder),
                doc_type=DocType.folder,
                status=Status.completed,
                parent_id=parent_id,
            )
            with db.transaction():
                db.save(folder_doc)
                _touch_ancestor_documents(db, folder_doc.parent_id)
            notify_document(folder_doc)
        folder_id = folder_doc.id
        logger.info(
            f"Created folder: {folder.name} "
            f"(parent_id={parent_id or 'root'})"
        )

    total = count_files(folder, recursive=recursive)
    if on_progress:
        on_progress(0, total)
    documents: list[Document] = []
    existing_hashes: set[tuple[str, str]] = set()
    library_path = package_path or getattr(db, "path", None)
    # Timed (2026-08-09): this pre-scan materialises EVERY document row into
    # Pydantic objects before the first file is touched — on a large library
    # it was the silent multi-minute 'frozen with no progress' phase. A
    # targeted SELECT of (source_path, checksum) is the queued upgrade.
    _prescan_started = time.monotonic()
    try:
        for existing in db.all(Document):
            if existing.status == Status.failed:
                continue
            source_path = (
                (existing.metadata or {}).get("source_path")
                or existing.path
            )
            checksum = (existing.metadata or {}).get("checksum")
            if isinstance(source_path, str) and isinstance(checksum, str):
                existing_hashes.add((source_path, checksum))
        logger.info(
            "ingest.folder.prescan existing=%d elapsed_ms=%d",
            len(existing_hashes), int((time.monotonic() - _prescan_started) * 1000),
        )
    except Exception as exc:
        logger.warning(
            "Could not pre-index existing checksums for skip logic in %s: %s",
            library_path,
            exc,
        )

    files = (
        path
        for path in discover_files(folder, recursive=recursive)
        if not _is_sidecar_file(path)
    )
    pending_links: list[tuple[Document, str, str]] = []

    def flush_pending_links() -> None:
        nonlocal pending_links
        if not pending_links:
            return
        batch, pending_links = pending_links, []
        try:
            db.save_many([doc for doc, _, _ in batch])
            saved = batch
        except Exception as batch_exc:
            # Preserve per-file failure isolation if one unexpected row rejects
            # the native bulk statement; the ordinary path identifies survivors.
            logger.warning("Bulk ingest save failed; retrying per file: %s", batch_exc)
            saved = []
            failed_saves: list[str] = []
            for item in batch:
                try:
                    with db.transaction():
                        db.save(item[0])
                    saved.append(item)
                except Exception as save_exc:
                    logger.error("Could not persist %s: %s", item[0].name, save_exc)
                    failed_saves.append(f"{item[0].name}: {save_exc}")
        else:
            failed_saves = []

        parent_ids = {doc.parent_id for doc, _, _ in saved if doc.parent_id}
        if parent_ids:
            with db.transaction():
                for saved_parent_id in parent_ids:
                    _touch_ancestor_documents(db, saved_parent_id)

        for doc, source_key, checksum in saved:
            documents.append(doc)
            actual_checksum = (doc.metadata or {}).get("checksum")
            existing_hashes.add(
                (
                    source_key,
                    actual_checksum if isinstance(actual_checksum, str) else checksum,
                )
            )
            notify_document(doc)
        if failed_saves:
            raise RuntimeError("; ".join(failed_saves))

    for i, file_path in enumerate(files):
        if should_cancel and should_cancel():
            flush_pending_links()
            break
        subfolder_id = folder_id
        created_folders: list[Document] = []
        try:
            if file_path.is_symlink():
                raise ValueError(f"Refusing to ingest symlinked file: {file_path}")
            checksum = _file_checksum(file_path)
            source_key = str(file_path)
            if (source_key, checksum) in existing_hashes:
                logger.info("Skipping unchanged file (hash match): %s", file_path)
                if on_progress:
                    on_progress(i + 1, total)
                continue

            # Folder rows commit first so a failed child can still point at a
            # real, visible parent rather than an ID rolled back with the file.
            if recursive and file_path.parent != folder:
                with db.transaction():
                    subfolder_id = _ensure_folder_hierarchy(
                        file_path.parent,
                        folder,
                        folder_id,
                        db,
                        created=created_folders,
                    )
                for created_folder in created_folders:
                    notify_document(created_folder)

            file_type = detect_file_type(file_path)
            batchable_link = mode == IngestMode.LINK and (
                not extract_text or file_type not in _TEXT_EXTRACTABLE
            ) and file_type != FileType.pdf
            if batchable_link:
                doc = ingest_file(
                    file_path,
                    mode=mode,
                    parent_id=subfolder_id,
                    extract_metadata=True,
                    extract_text=extract_text,
                    auto_embed=auto_embed,
                    save=False,
                    db=db,
                    package_path=package_path,
                )
                actual_checksum = (doc.metadata or {}).get("checksum")
                if isinstance(actual_checksum, str) and actual_checksum != checksum:
                    raise RuntimeError(f"File changed while being ingested: {file_path}")
                pending_links.append((doc, source_key, checksum))
            else:
                with db.transaction():
                    doc = ingest_file(
                        file_path,
                        mode=mode,
                        parent_id=subfolder_id,
                        extract_metadata=True,
                        extract_text=extract_text,
                        auto_embed=auto_embed,
                        save=True,
                        db=db,
                        package_path=package_path,
                        # Reuse the skip-test hash EXCEPT for LINK mode, where
                        # the recompute is the changed-while-ingesting tamper
                        # check below (2026-08-09).
                        known_checksum=None if mode == IngestMode.LINK else checksum,
                    )
                    actual_checksum = (doc.metadata or {}).get("checksum")
                    if (
                        mode == IngestMode.LINK
                        and isinstance(actual_checksum, str)
                        and actual_checksum != checksum
                    ):
                        raise RuntimeError(
                            f"File changed while being ingested: {file_path}"
                        )

                documents.append(doc)
                actual_checksum = (doc.metadata or {}).get("checksum")
                existing_hashes.add(
                    (
                        source_key,
                        actual_checksum
                        if isinstance(actual_checksum, str)
                        else checksum,
                    )
                )
                notify_document(doc)

        except Exception as e:
            # Fail loud (#881/#1216): persist a failed-status stub so the
            # failure is visible in the DB / UI rather than silently dropped.
            logger.warning(f"Failed to ingest {file_path}: {e}")
            try:
                stub = Document(
                    name=file_path.name,
                    path=str(file_path),
                    doc_type=DocType.file,
                    file_type=detect_file_type(file_path),
                    parent_id=subfolder_id,
                    status=Status.failed,
                    metadata={
                        "ingest_error": str(e),
                        "source_path": str(file_path),
                    },
                )
                with db.transaction():
                    db.save(stub)
                notify_document(stub)
            except Exception as save_err:
                logger.error(
                    "Could not persist failed-ingest stub for %s: %s",
                    file_path,
                    save_err,
                )
            if on_progress:
                on_progress(i + 1, total)
        else:
            if on_progress:
                on_progress(i + 1, total)
        if len(pending_links) >= _INGEST_BATCH_SIZE:
            flush_pending_links()

    flush_pending_links()
    logger.info(f"Ingested {len(documents)} files from {folder.name}")
    return documents


def _is_sidecar_file(path: Path) -> bool:
    """Return True when ``path`` is a metadata sidecar, not a primary document."""
    suffix = path.suffix.lower()
    name = path.name.lower()
    return (
        suffix == ".xmp"
        or name.endswith(".iffy.json")
        or (suffix == ".json" and path.with_suffix("").is_file())
    )


_ANCESTOR_MAX_DEPTH = 64


def _touch_ancestor_documents(db: "Database", parent_id: str | None) -> None:
    """Refresh updated_at on the ancestor chain for a newly ingested child.

    Guards against infinite loops caused by cyclic parent_id references or
    unexpectedly deep trees: stops when a doc id is seen a second time (cycle)
    or after _ANCESTOR_MAX_DEPTH hops.
    """
    current_parent_id = parent_id if isinstance(parent_id, str) else None
    visited: set[str] = set()
    depth = 0
    while current_parent_id:
        if not isinstance(current_parent_id, str):
            logger.warning(
                "Non-string ancestor id %r encountered — stopping walk",
                current_parent_id,
            )
            break
        if current_parent_id in visited:
            logger.warning(
                "Cycle detected in ancestor chain at doc id %s — stopping walk",
                current_parent_id,
            )
            break
        if depth >= _ANCESTOR_MAX_DEPTH:
            logger.warning(
                "Ancestor chain exceeded max depth (%d) at doc id %s — stopping walk",
                _ANCESTOR_MAX_DEPTH,
                current_parent_id,
            )
            break
        visited.add(current_parent_id)
        depth += 1
        parent = db.get(Document, current_parent_id)
        if not parent:
            break
        parent.updated_at = utc_now()
        db.save(parent)
        next_parent_id = getattr(parent, "parent_id", None)
        current_parent_id = next_parent_id if isinstance(next_parent_id, str) else None


def _ensure_folder_hierarchy(
    subfolder: Path,
    base_folder: Path,
    base_id: str,
    db: "Database",
    created: list[Document] | None = None,
) -> str:
    """Ensure folder hierarchy exists in database.

    Args:
        subfolder: Path to subfolder
        base_folder: Base folder path
        base_id: ID of base folder document
        db: Database instance

    Returns:
        The ID of the deepest folder Document.
    """

    # Get relative path
    rel_path = subfolder.relative_to(base_folder)

    current_parent = base_id
    for part in rel_path.parts:
        # Check if folder already exists
        existing = db.query(Document, parent_id=current_parent, name=part)
        if existing:
            current_parent = existing[0].id
        else:
            # Create folder
            folder_doc = Document(
                name=part,
                doc_type=DocType.folder,
                parent_id=current_parent,
                status=Status.completed,
            )
            db.save(folder_doc)
            if created is not None:
                created.append(folder_doc)
            current_parent = folder_doc.id

    return current_parent


# =============================================================================
# File Discovery
# =============================================================================


def discover_files(
    folder: Path,
    extensions: set[str] | None = None,
    recursive: bool = True,
) -> Iterator[Path]:
    """Discover files in a folder.

    Args:
        folder: Folder to search
        extensions: Set of extensions to include (e.g., {".jpg", ".png"})
        recursive: If True, search subdirectories

    Yields:
        Path objects for each matching file
    """
    folder = Path(folder)

    if recursive:
        pattern = "**/*"
    else:
        pattern = "*"

    for path in folder.glob(pattern):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if extensions and path.suffix.lower() not in extensions:
            continue
        yield path


def count_files(
    folder: Path,
    extensions: set[str] | None = None,
    recursive: bool = True,
) -> int:
    """Count files in a folder.

    Args:
        folder: Folder to count
        extensions: Set of extensions to include
        recursive: If True, count subdirectories

    Returns:
        Number of matching files
    """
    return sum(
        1
        for path in discover_files(folder, extensions, recursive)
        if not _is_sidecar_file(path)
    )


# =============================================================================
# .iffy.json Sidecar Support
# =============================================================================

def _parse_iffy_sidecar(image_path: Path) -> dict[str, Any] | None:
    """Parse an .iffy.json sidecar file for a document.

    Two naming conventions exist side by side in the same archive, and BOTH
    must be tried (#4206):

    * ``x.jpg.iffy.json`` — FULL NAME, extension included
    * ``x.iffy.json``     — STEM only, extension stripped

    Only the stem form was looked for before, so the full-name form silently
    resolved to nothing: 110 files in the reference corpus imported without their
    title / original_date / repository / identifier / record_url, with no
    warning. Silence is what made it expensive to find.

    Full name is tried FIRST because it is unambiguous. The stem form cannot
    distinguish ``x.png`` from ``x.tif`` when both sit in one directory — 10
    such collisions exist in that corpus, where the sidecar legitimately
    describes both renditions, so the stem form stays a fallback rather than
    an error.

    Args:
        image_path: Path to the document file

    Returns:
        Dict of extracted .iffy.json fields, or None if no sidecar found
    """
    # Don't create sidecar for sidecar files
    if image_path.suffix == ".json" and image_path.stem.endswith(".iffy"):
        return None

    sidecar = next(
        (
            candidate
            for candidate in (
                image_path.parent / f"{image_path.name}.iffy.json",
                image_path.parent / f"{image_path.stem}.iffy.json",
            )
            if candidate.exists()
        ),
        None,
    )
    if sidecar is None:
        return None

    try:
        with open(sidecar, "r", encoding="utf-8") as f:
            iffy_data = json.load(f)

        # Map .iffy.json fields to our metadata keys
        result: dict[str, Any] = {}
        field_map = {
            "status": "iffy_status",
            "record_type": "iffy_record_type",
            "source_archive": "iffy_source_archive",
            "repository": "iffy_repository",
            "identifier": "iffy_identifier",
            "record_url": "iffy_record_url",
            "iiif_manifest": "iffy_iiif_manifest",
            "discovered_date": "iffy_discovered_date",
            "original_date": "iffy_original_date",
            "notes": "iffy_notes",
        }

        for iffy_key, metadata_key in field_map.items():
            if iffy_key in iffy_data:
                value = iffy_data[iffy_key]
                # Special handling for notes - convert list to comma-separated string
                if iffy_key == "notes" and isinstance(value, list):
                    result[metadata_key] = ", ".join(str(item) for item in value)
                else:
                    result[metadata_key] = value

        return result
    except Exception as e:
        logger.warning(f"Failed to parse .iffy.json sidecar {sidecar}: {e}")
        return None


def _apply_iffy_to_document(
    doc: "Document",
    iffy_data: dict[str, Any],
) -> "Document":
    """Apply parsed .iffy.json data to a Document's metadata.

    Merges .iffy.json fields into doc.metadata without overwriting existing
    values (existing values take precedence for conflict resolution).

    Args:
        doc: Document to update
        iffy_data: Output from _parse_iffy_sidecar

    Returns:
        Updated Document (mutates in place and returns same instance)
    """
    if not iffy_data:
        return doc

    if doc.metadata is None:
        doc.metadata = {}

    # Merge: .iffy.json values fill in gaps, don't overwrite existing metadata
    for iffy_key, value in iffy_data.items():
        if iffy_key not in doc.metadata or not doc.metadata[iffy_key]:
            doc.metadata[iffy_key] = value

    # Mark that this document has .iffy.json sidecar
    doc.metadata["_iffy_sidecar"] = True

    return doc


# =============================================================================
# Deduplication
# =============================================================================


def find_duplicates(documents: list[Document]) -> dict[str, list[Document]]:
    """Find duplicate documents by checksum.

    Args:
        documents: List of documents to check

    Returns:
        Dict mapping checksum to list of duplicate documents
    """
    by_checksum: dict[str, list[Document]] = {}

    for doc in documents:
        checksum = doc.metadata.get("checksum")
        if checksum:
            if checksum not in by_checksum:
                by_checksum[checksum] = []
            by_checksum[checksum].append(doc)

    # Return only actual duplicates (more than one document)
    return {k: v for k, v in by_checksum.items() if len(v) > 1}


__all__ = [
    'Any',
    'Callable',
    'Coroutine',
    'DocType',
    'Document',
    'Enum',
    'FileType',
    'IngestMode',
    'Iterator',
    'Path',
    'Status',
    'TYPE_CHECKING',
    '_ANCESTOR_MAX_DEPTH',
    '_FILE_TYPE_MAP',
    '_TEXT_EXTRACTABLE',
    '_apply_iffy_to_document',
    '_copy_to_library',
    '_create_pdf_page_children',
    '_ensure_folder_hierarchy',
    '_extract_file_metadata',
    '_extract_image_metadata',
    '_extract_text_content',
    '_file_checksum',
    '_is_sidecar_file',
    '_kreuzberg_pdf_pages',
    '_load_bibliography_sidecar',
    '_load_companion_json',
    '_page_label_for',
    '_parse_iffy_sidecar',
    '_resolve_default_db',
    '_run_async',
    '_save_pdf_page_artifacts',
    '_save_pending_artifacts',
    '_touch_ancestor_documents',
    '_try_apfs_clone',
    'annotations',
    'asyncio',
    'base64',
    'count_files',
    'ctypes',
    'datetime',
    'detect_file_type',
    'discover_files',
    'find_duplicates',
    'hashlib',
    'ingest_file',
    'ingest_folder',
    'json',
    'logger',
    'logging',
    'mimetypes',
    'shutil',
    'uuid4',
]
