"""Tests for #2452: search returns page-level doc IDs, not parent PDFs.

Verifies two code paths:
1. _project_pdf_file_hits_to_pages  — legacy: file-level hit → best page
2. _enrich_page_results_with_parent_info — modern: page-level hit → enriched metadata
"""

from __future__ import annotations

import pytest

from fichero_server.api.routes.search import (
    _enrich_page_results_with_parent_info,
    _project_pdf_file_hits_to_pages,
)
from fichero_server.db import SearchResult
from fichero_server.models import DocType, Document, FileType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pdf(db, pdf_id: str = "pdf-1", name: str = "report.pdf") -> Document:
    pdf = Document(
        id=pdf_id,
        name=name,
        doc_type=DocType.file,
        file_type=FileType.pdf,
        page_content=None,
    )
    db.save(pdf)
    return pdf


def _make_page(
    db,
    page_id: str,
    parent_id: str,
    sequence: int,
    content: str,
    page_label: str | None = None,
) -> Document:
    page = Document(
        id=page_id,
        name=f"Page {sequence}",
        doc_type=DocType.page,
        file_type=FileType.pdf,
        parent_id=parent_id,
        sequence=sequence,
        page_label=page_label,
        page_content=content,
    )
    db.save(page)
    return page


def _file_hit(doc: Document, score: float = 0.8) -> SearchResult:
    return SearchResult(
        document_id=doc.id,
        score=score,
        content_preview="",
        metadata={
            "name": doc.name,
            "doc_type": doc.doc_type.value,
            "file_type": doc.file_type.value if doc.file_type else None,
        },
        highlights=[],
    )


def _page_hit(page: Document, score: float = 0.8) -> SearchResult:
    return SearchResult(
        document_id=page.id,
        score=score,
        content_preview=page.page_content or "",
        metadata={
            "name": page.name,
            "doc_type": page.doc_type.value,
            "file_type": page.file_type.value if page.file_type else None,
        },
        highlights=[],
    )


# ---------------------------------------------------------------------------
# _project_pdf_file_hits_to_pages — legacy file-level hits
# ---------------------------------------------------------------------------


class TestProjectPdfFileHitsToPages:
    def test_returns_page_id_not_pdf_id(self, db):
        """A query matching page 4's text must return page-4's doc id, not the PDF's.

        Page 4 has the highest term frequency so the heuristic must pick it,
        not the parent PDF.
        """
        pdf = _make_pdf(db)
        # page-1 and page-7 have no query terms — page-4 is the only hit.
        _make_page(db, "page-1", pdf.id, 1, "Introduction to colonial administration")
        _make_page(db, "page-4", pdf.id, 4, "Habeas corpus writs, habeas corpus petitions, habeas corpus rights")
        _make_page(db, "page-7", pdf.id, 7, "Conclusion of the proceedings")

        results = _project_pdf_file_hits_to_pages(db, [_file_hit(pdf)], "habeas corpus")

        assert len(results) == 1
        assert results[0].document_id == "page-4", (
            f"Expected page-4 (best content match), got {results[0].document_id}"
        )

    def test_enriches_with_page_number_and_label(self, db):
        """Projected page result must carry pdf_parent_id, page_number, page_label."""
        pdf = _make_pdf(db)
        _make_page(db, "page-3", pdf.id, 3, "habeas corpus text here", page_label="iii")

        results = _project_pdf_file_hits_to_pages(db, [_file_hit(pdf)], "habeas corpus")

        meta = results[0].metadata
        assert meta.get("pdf_parent_id") == pdf.id
        assert meta.get("page_number") == 3
        assert meta.get("page_label") == "iii"

    def test_non_pdf_results_pass_through(self, db):
        """Non-PDF results are returned unchanged."""
        txt = Document(
            id="txt-1",
            name="notes.txt",
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content="some notes",
        )
        db.save(txt)
        hit = SearchResult(
            document_id=txt.id,
            score=0.9,
            content_preview="some notes",
            metadata={"name": "notes.txt", "doc_type": "file", "file_type": "text"},
            highlights=[],
        )
        results = _project_pdf_file_hits_to_pages(db, [hit], "notes")
        assert results[0].document_id == "txt-1"


# ---------------------------------------------------------------------------
# _enrich_page_results_with_parent_info — modern page-level hits
# ---------------------------------------------------------------------------


class TestEnrichPageResultsWithParentInfo:
    def test_page_result_gets_parent_id_and_page_label(self, db):
        """A raw page hit (from index) must be enriched with pdf_parent_id and page_label."""
        pdf = _make_pdf(db, name="archive.pdf")
        page = _make_page(db, "page-5", pdf.id, 5, "On liberty and necessity", page_label="v")

        result = _page_hit(page)
        enriched = _enrich_page_results_with_parent_info(db, [result])

        assert len(enriched) == 1
        meta = enriched[0].metadata
        assert meta.get("pdf_parent_id") == pdf.id
        assert meta.get("page_number") == 5
        assert meta.get("page_label") == "v"
        assert meta.get("parent_name") == "archive.pdf"
        # document_id must still be the page's id
        assert enriched[0].document_id == "page-5"

    def test_page_result_without_explicit_label_uses_sequence(self, db):
        """When page_label is None, page_label in metadata falls back to str(sequence)."""
        pdf = _make_pdf(db)
        page = _make_page(db, "page-2", pdf.id, 2, "content on page two", page_label=None)

        result = _page_hit(page)
        enriched = _enrich_page_results_with_parent_info(db, [result])

        meta = enriched[0].metadata
        assert meta.get("page_label") == "2"

    def test_already_enriched_results_are_not_modified(self, db):
        """Results that already carry pdf_parent_id (from projection) are left unchanged."""
        page = Document(id="page-x", name="p", doc_type=DocType.page)
        db.save(page)

        already_enriched = SearchResult(
            document_id="page-x",
            score=0.75,
            content_preview="",
            metadata={
                "doc_type": "page",
                "pdf_parent_id": "pdf-already-set",
                "page_number": 7,
                "page_label": "7",
            },
            highlights=[],
        )
        results = _enrich_page_results_with_parent_info(db, [already_enriched])
        assert results[0].metadata["pdf_parent_id"] == "pdf-already-set"

    def test_score_and_preview_preserved(self, db):
        """Enrichment must not alter score or content_preview."""
        pdf = _make_pdf(db)
        page = _make_page(db, "page-9", pdf.id, 9, "some text")

        result = _page_hit(page, score=0.93)
        result.content_preview = "some text preview"
        enriched = _enrich_page_results_with_parent_info(db, [result])

        assert enriched[0].score == pytest.approx(0.93)
        assert enriched[0].content_preview == "some text preview"
