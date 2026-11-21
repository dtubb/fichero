"""A PDF page's segments come from its own text layer, with no model run.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.pdf.segments-from-the-text-layer` (where the
artifact is missing the engine reads the PDF again; a page with no text layer gets no segments and says so in one line;
re-running never duplicates). Engine half: `POST /api/segments/document/{doc_id}/text-layer`. Real PDFs built here.
"""

from __future__ import annotations

import fitz
import pytest

from fichero_server.models import Artifact, DocType, Document, FileType, Segment

pytestmark = pytest.mark.source_model

WORDS = "Marshall surveyed the Choco river in 1842"


def _pdf(tmp_path, text: str | None):
    path = tmp_path / ("letter.pdf" if text else "scan.pdf")
    pdf = fitz.open()
    page = pdf.new_page()
    if text:
        page.insert_text((72, 144), text, fontsize=12)
    pdf.save(str(path))
    pdf.close()
    return path


def _page_of(db, path):
    parent = Document(name=path.name, doc_type=DocType.file, file_type=FileType.pdf, path=str(path))
    db.save(parent)
    page = Document(name=f"{path.name} - Page 1", doc_type=DocType.page, file_type=FileType.pdf, parent_id=parent.id,
                    sequence=1, metadata={"pdf_parent_id": parent.id, "page_number": 1})
    db.save(page)
    return page


def _layer(client, page):
    response = client.post(f"/api/segments/document/{page.id}/text-layer")
    assert response.status_code == 200, response.text
    return response.json()


def _live(db, page):
    return [row for row in db.query(Segment, document_id=page.id) if row.deleted_at is None]


def test_a_page_with_no_saved_geometry_reads_the_pdf_again_and_gets_its_words_as_segments(db, client, tmp_path):
    page = _page_of(db, _pdf(tmp_path, WORDS))
    assert not db.query(Artifact, document_id=page.id)

    answer = _layer(client, page)

    assert answer["pass_id"] and answer["made"] is True
    [artifact] = db.query(Artifact, document_id=page.id, artifact_type="text_geometry")
    rows = _live(db, page)
    assert rows and {row.pass_id for row in rows} == {answer["pass_id"]}
    assert all(0.0 <= row.bbox_x <= 1.0 and 0.0 <= row.bbox_y <= 1.0 for row in rows)
    assert artifact.geometry_superseded_by_pass_id == answer["pass_id"]


def test_running_it_again_keeps_the_set_and_adds_nothing(db, client, tmp_path):
    page = _page_of(db, _pdf(tmp_path, WORDS))
    first = _layer(client, page)
    count = len(_live(db, page))

    again = _layer(client, page)

    assert again == {"pass_id": first["pass_id"], "made": False, "said": None}
    assert len(_live(db, page)) == count
    assert len(db.query(Artifact, document_id=page.id, artifact_type="text_geometry")) == 1


def test_a_scan_gets_no_segments_and_says_so_in_one_line(db, client, tmp_path):
    page = _page_of(db, _pdf(tmp_path, None))

    answer = _layer(client, page)

    assert answer == {"pass_id": None, "made": False,
                      "said": "No text layer on this page; find lines to make segments"}
    assert _live(db, page) == []


def test_a_page_that_is_not_from_a_pdf_is_refused(db, client):
    photo = Document(name="folio.jpg", doc_type=DocType.file, file_type=FileType.image, path="/path/folio.jpg")
    db.save(photo)

    response = client.post(f"/api/segments/document/{photo.id}/text-layer")

    assert response.status_code == 422
    assert "not a page of a PDF" in response.json()["detail"]
