"""The Reader's Content view of a page shows the page's text from its lines (#6579, owner 2026-11-13).

`reader.content.a-page-reads-its-own-lines`. WHY: an image page with lines that all had readings (the
segment list and the Order tab showed them) opened in the Reader as "Page 1 <name> crop -- No
transcription yet", "Page 2 ... crop", ...: the page has no page children, so the view fell back to
its REGION children, and the page's hand-drawn crops were listed as its pages, each empty, while the
page's own text was never shown.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.models import Document, DocType, FileType, Status
from fichero_server.models.anchors import NodeRegion
from tests.unit.api.test_page_text_follows_the_file import CLM, _import
from tests.unit.api.test_reader_line_map import _view


def _child(db, parent: Document, name: str, method: str, *, page_content: str | None = None,
           sequence: int = 0) -> Document:
    child = Document(
        parent_id=parent.id, doc_type=DocType.chunk, file_type=FileType.image, name=name,
        path=parent.path, page_content=page_content, sequence=sequence, status=Status.completed,
        region_in_parent=NodeRegion(rect=[0.1, 0.1 + sequence * 0.2, 0.8, 0.2], method=method),
    )
    db.save(child)
    return child


def test_a_page_with_crops_reads_as_itself_from_its_lines(db, client):
    doc_id = _import(db, CLM)
    page = db.get(Document, doc_id)
    for n in range(4):
        _child(db, page, f"{page.name} crop", "user-crop", sequence=n)

    payload, _ = _view(client, doc_id)

    assert [p["id"] for p in payload["pages"]] == [doc_id]     # no crop is a page
    shown = payload["pages"][0]
    assert shown["has_content"]
    assert shown["content"] == document_text(db, doc_id).text
    assert shown["lines"], "the text comes with its line map"


def test_empty_regions_are_not_pages(db, client):
    """A region that is not a crop (a detected zone) with no text of its own is not a section either."""
    doc_id = _import(db, CLM)
    page = db.get(Document, doc_id)
    _child(db, page, "zone 1", "detected", sequence=0)
    _child(db, page, "zone 2", "detected", sequence=1)

    payload, _ = _view(client, doc_id)

    assert [p["id"] for p in payload["pages"]] == [doc_id]
    assert payload["pages"][0]["content"] == document_text(db, doc_id).text


def test_a_page_whose_stored_text_missed_its_lines_shows_them(db, client):
    """The stored text is a cache of the lines' readings; one that is empty while the lines have
    readings (a write that missed the refresh) is derived when the page is shown, not "No transcription yet"."""
    doc_id = _import(db, CLM)
    page = db.get(Document, doc_id)
    page.page_content = ""          # the derivation stamp stays current: only the text is missing
    db.save(page)

    payload, _ = _view(client, doc_id)

    shown = payload["pages"][0]
    assert shown["has_content"]
    assert shown["content"] == document_text(db, doc_id).text
    assert shown["lines"]


def test_regions_with_text_are_still_the_sections(db, client):
    """Diary entries (regions with text) stay the sections; a crop beside them does not join them."""
    parent = Document(name="Diary page", doc_type=DocType.file, file_type=FileType.image,
                      path="/p/diary.jpg", status=Status.completed)
    db.save(parent)
    first = _child(db, parent, "Entry 1", "detected", page_content="The first entry.", sequence=0)
    second = _child(db, parent, "Entry 2", "detected", page_content="The second entry.", sequence=1)
    _child(db, parent, "Diary page crop", "user-crop", sequence=2)

    payload, _ = _view(client, parent.id)

    assert [p["id"] for p in payload["pages"]] == [first.id, second.id]
    assert [p["content"] for p in payload["pages"]] == ["The first entry.", "The second entry."]
