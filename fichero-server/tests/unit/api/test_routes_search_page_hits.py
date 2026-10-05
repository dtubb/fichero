"""A search reports EVERY hit on a page, so the Reader can light them all (#5473).

WHY: the Reader lights each anchored excerpt a search row carries on its page
(#5466). The engine capped that list at 3, so a word used seven times on a
page was lit only three times and the reader could not see the rest. These
tests go through ``POST /api/search`` -- the request the app sends -- so a cap
reintroduced anywhere on the route (the db search leg or the PDF page
projection) turns them red.
"""

from __future__ import annotations

from fichero_server.db import PAGE_HIT_CEILING, SearchResult
from fichero_server.models import DocType, Document, FileType


def _page_with(word: str, times: int) -> str:
    return " ".join(f"{word} worked the sluice." for _ in range(times))


def _project_onto_page(db, monkeypatch, page_content: str) -> None:
    """Seed a PDF whose one page holds ``page_content``; db.search returns the
    file hit, and the route projects it onto that page (the path a PDF hit
    takes in the app)."""
    parent = Document(
        id="pdf-hits",
        name="hits.pdf",
        doc_type=DocType.file,
        file_type=FileType.pdf,
        page_content="whole-file blob",
    )
    page = Document(
        id="pdf-hits-page-1",
        parent_id=parent.id,
        name="hits.pdf - Page 1",
        doc_type=DocType.page,
        sequence=1,
        page_content=page_content,
        metadata={"page_number": 1},
    )
    db.save(parent)
    db.save(page)
    file_hit = SearchResult(
        document_id=parent.id,
        score=0.9,
        content_preview="whole-file blob",
        metadata={"name": parent.name, "doc_type": "file", "file_type": "pdf"},
        highlights=[],
    )
    monkeypatch.setattr(
        type(db),
        "search",
        lambda self, **kwargs: (
            [file_hit],
            1,
            {"search_type": "hybrid", "execution_time_ms": 1.0, "has_more": False},
        ),
    )


def _search(client, query: str, search_type: str = "hybrid") -> dict:
    r = client.post("/api/search", json={"query": query, "search_type": search_type})
    assert r.status_code == 200, r.text
    return r.json()


def test_page_with_seven_occurrences_reports_seven_hits(client, db, monkeypatch):
    # WHY: the old cap of 3 left occurrences 4..7 dark in the Reader; each
    # of the seven must ride as its own page-anchored span.
    content = _page_with("Camilo", 7)
    _project_onto_page(db, monkeypatch, content)

    result = _search(client, "camilo")["results"][0]
    excerpts = result["transcript_excerpts"]

    assert result["document_id"] == "pdf-hits-page-1"
    assert len(excerpts) == 7
    spans = [(e["anchor"]["char_start"], e["anchor"]["char_end"]) for e in excerpts]
    assert all(e["anchor"]["document_id"] == "pdf-hits-page-1" for e in excerpts)
    assert all(content[s:t] == "Camilo" for s, t in spans), spans
    assert len(set(spans)) == 7, "each hit is a distinct span, in page order"
    assert spans == sorted(spans)


def test_fulltext_leg_also_reports_every_hit_on_the_page(client, db):
    # WHY: a plain (non-PDF) document's row is built by db.search's own
    # excerpt call, not the page projection; both must carry every hit.
    content = _page_with("Asprilla", 7)
    db.save(
        Document(
            id="doc-seven",
            name="seven.txt",
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content=content,
        )
    )

    body = _search(client, "Asprilla", search_type="fulltext")
    rows = [r for r in body["results"] if r["document_id"] == "doc-seven"]
    assert rows, body
    excerpts = rows[0]["transcript_excerpts"]
    assert len(excerpts) == 7
    assert all(
        content[e["anchor"]["char_start"] : e["anchor"]["char_end"]] == "Asprilla"
        for e in excerpts
    )


def test_ranking_and_snippet_unchanged_by_more_hits(client, db, monkeypatch):
    # WHY: the per-page hit list is a highlight set, not a ranking -- the row
    # count, score and its one-line snippet (the FIRST excerpt) must be what
    # they were with three excerpts.
    content = _page_with("Camilo", 7)
    _project_onto_page(db, monkeypatch, content)

    body = _search(client, "camilo")
    assert body["count"] == 1
    result = body["results"][0]
    assert result["score"] == 0.9
    first = result["transcript_excerpts"][0]
    assert result["content_preview"] == first["text"]
    assert first["anchor"]["char_start"] == 0
    # The snippet is the 80-char window around the first hit, not the page.
    assert len(result["content_preview"]) < len(content)


def test_ten_thousand_occurrence_page_is_bounded_at_the_ceiling(client, db, monkeypatch):
    # WHY: a pathological page (a word list, an OCR loop) must not ship
    # 10,000 excerpts per row; the list stops at the named ceiling.
    _project_onto_page(db, monkeypatch, _page_with("Camilo", 10_000))

    result = _search(client, "camilo")["results"][0]

    assert PAGE_HIT_CEILING == 500
    assert len(result["transcript_excerpts"]) == PAGE_HIT_CEILING
