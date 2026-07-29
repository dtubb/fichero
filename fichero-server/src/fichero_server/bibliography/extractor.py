"""Bibliographic metadata extractor (#908).

Three layers of progressively richer info:

1. ``extract_from_pdf_metadata(path)`` — instant, free. PyMuPDF reads
   author / title / keywords from the PDF info dictionary the
   publisher embedded.
2. ``extract_from_first_page(text, llm_config)`` — LLM-driven. Reads
   the first page text and structured-outputs a ``SourceMetadata``
   shape. ~3-5 seconds on Apple Intelligence.
3. ``extract_full(document, llm_config=None)`` — orchestrator. Calls
   layer 1, then layer 2 if the LLM is available, then merges with
   existing metadata so user corrections survive.

DOI / ISBN online lookup is a peer module (#910) — call
``fichero_server.bibliography.doi_lookup.resolve_doi(doi)`` after this to
enrich the result.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:  # pragma: no cover
    from fichero_server.llm import LLMConfig
    from fichero_server.models import Document

logger = logging.getLogger(__name__)


def extract_from_pdf_metadata(path: str | Path) -> dict[str, Any]:
    """Pull author / title / keywords from a PDF's info dictionary.

    Returns a dict shaped like ``SourceMetadata`` fields — keys that
    PyMuPDF doesn't supply are absent. Empty dict on non-PDF input
    or read failure.
    """
    if not path:
        return {}

    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF not available; PDF metadata extraction skipped")
        return {}

    path = Path(path)
    if not path.exists() or path.suffix.lower() != ".pdf":
        return {}

    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        logger.warning("PyMuPDF open failed for %s: %s", path, exc)
        return {}

    info = doc.metadata or {}
    doc.close()

    out: dict[str, Any] = {}
    title = (info.get("title") or "").strip()
    if title:
        out["title"] = title
    author_raw = (info.get("author") or "").strip()
    if author_raw:
        # PDF info usually stores authors as a single string —
        # split on common separators.
        parts = [
            p.strip()
            for p in author_raw.replace(";", ",").split(",")
            if p.strip()
        ]
        out["authors"] = parts
    subject = (info.get("subject") or "").strip()
    if subject:
        out.setdefault("metadata", {})["pdf_subject"] = subject
    keywords = (info.get("keywords") or "").strip()
    if keywords:
        out.setdefault("metadata", {})["pdf_keywords"] = keywords
    # PDF creation date — best-effort year.
    creation_date = (info.get("creationDate") or "").strip()
    if creation_date:
        # PDF dates look like D:20200315120000+00'00'; pull the first
        # 4-digit run as the year. (No \b anchors: the year is embedded
        # in a longer digit run, so word boundaries never match here.)
        import re

        m = re.search(r"(\d{4})", creation_date)
        if m:
            out["date"] = m.group(1)

    return out


def _gather_cover_pages_text(document: "Document", n_pages: int = 4) -> str:
    """Return the joined first-N page_content for a document.

    For PDFs each page is its own ``Document`` row with sequence
    number. We query page children, sort by sequence, take the
    first ``n_pages``, and join their page_content.

    For text / markdown documents that have a single page_content
    blob, return the leading slice that approximates n_pages worth
    of content (~3000 chars per page).
    """
    if document.page_content and document.doc_type.value != "file":
        # The document itself carries text; just return its content.
        return document.page_content

    # Try to fetch page children via the global db_manager (per-library
    # database). The path lives on the parent doc; pages share its
    # path but have their own sequence + page_content.
    try:
        from fichero_server.db import db_manager
        from fichero_server.models import Document as DocModel
        from fichero_server.settings import settings

        db = db_manager.get_database(settings.db_path)
        children = db.query(DocModel, parent_id=document.id)
        pages = [c for c in children if c.doc_type.value == "page" and c.page_content]
        pages.sort(key=lambda p: p.sequence or 0)
        if pages:
            return "\n\n".join(p.page_content for p in pages[:n_pages])
    except Exception as exc:
        logger.debug("_gather_cover_pages_text: page-children fallback failed: %s", exc)

    # Final fallback — the parent's own page_content if present.
    return document.page_content or ""


async def extract_from_first_pages(
    pages_text: str,
    llm_config: "LLMConfig",
    max_chars: int = 12000,
) -> dict[str, Any]:
    """LLM-driven cover-pages extraction.

    Sends the first ~4 pages worth of text to a structured-output LLM
    call asking for the SourceMetadata fields. 12k chars ≈ 3-4 academic
    pages, enough to catch:
    - cover + title page + author affiliations on the verso
    - copyright + publication info page (year, publisher, ISBN, DOI)
    - table of contents / first acknowledgement page where dates
      and journal references often appear

    Truncate at ``max_chars`` to fit Apple Intelligence's window.

    Returns a dict; empty on error.
    """
    from pydantic import BaseModel, Field

    from fichero_server.llm import chat_structured_with_fallback

    class _Biblio(BaseModel):
        title: str = Field(default="", description="Full document title")
        authors: list[str] = Field(
            default_factory=list,
            description="Authors in 'Last, First' format; one entry per author.",
        )
        date: str = Field(
            default="",
            description="Publication date. Year only is fine, e.g. '2020'.",
        )
        publisher: str = Field(default="", description="Publishing house or journal name.")
        journal: str = Field(
            default="",
            description="Journal name if this is an article; else empty.",
        )
        volume: str = Field(default="")
        issue: str = Field(default="")
        pages: str = Field(default="")
        doi: str = Field(default="", description="DOI if visible on the page, e.g. '10.1234/abc'.")
        isbn: str = Field(default="", description="ISBN if visible on the page.")
        abstract: str = Field(default="", description="Brief summary if shown in the document.")
        language: str = Field(
            default="",
            description="ISO 639-1 language code (en / es / fr / …) if determinable.",
        )

    prompt = (
        "Extract bibliographic metadata from the cover page / first "
        "page of a document. Be conservative — leave a field empty "
        "if it isn't clearly stated. Author order matters; preserve it."
    )

    try:
        result = await chat_structured_with_fallback(
            prompt=pages_text[:max_chars],
            schema=_Biblio,
            config=llm_config,
            system=prompt,
            include_schema_in_prompt=False,
        )
    except Exception as exc:
        logger.warning("cover-pages biblio extraction failed: %s", exc)
        return {}

    out: dict[str, Any] = {}
    for field in (
        "title",
        "date",
        "publisher",
        "journal",
        "volume",
        "issue",
        "pages",
        "abstract",
        "language",
    ):
        value = getattr(result, field, "")
        if value:
            out[field] = value
    if getattr(result, "authors", None):
        out["authors"] = result.authors
    if getattr(result, "doi", "").strip():
        out["doi"] = result.doi.strip()
    if getattr(result, "isbn", "").strip():
        isbn_clean = result.isbn.replace("-", "").strip()
        if len(isbn_clean) == 13:
            out["isbn_13"] = isbn_clean
        elif len(isbn_clean) == 10:
            out["isbn_10"] = isbn_clean

    return out


def _merge_metadata(base: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Merge two metadata dicts; ``base`` values win on conflict.

    The base is typically the user-curated existing metadata; new
    is the freshly-extracted layer. We never clobber a curated
    field, only fill in absent ones.
    """
    merged = dict(base)
    for key, value in new.items():
        if not value:
            continue
        if key in merged and merged[key]:
            continue
        merged[key] = value
    return merged


async def extract_full(
    document: "Document",
    llm_config: Optional["LLMConfig"] = None,
) -> dict[str, Any]:
    """End-to-end: PDF metadata + (optional) LLM first-page + merge.

    Returns the resulting metadata dict (shape: SourceMetadata
    fields). Caller writes back to ``document.source_metadata``.
    """
    existing = document.source_metadata or {}
    pdf_layer: dict[str, Any] = {}
    if document.path:
        pdf_layer = extract_from_pdf_metadata(document.path)

    llm_layer: dict[str, Any] = {}
    if llm_config is not None:
        # Build the cover-pages text from either page_content (text
        # docs) or the joined first-N page children for PDFs.
        cover_text = _gather_cover_pages_text(document)
        if cover_text:
            llm_layer = await extract_from_first_pages(cover_text, llm_config)

    # Merge order: existing (user-curated) > PDF > LLM. So PDF only
    # fills gaps and LLM fills any remaining gaps.
    intermediate = _merge_metadata(existing, pdf_layer)
    final = _merge_metadata(intermediate, llm_layer)
    return final
