"""Image editing on a PDF PAGE node (#4574).

A PDF page child owns no file of its own — it renders page ``sequence`` of its
parent PDF. Every image-editing route resolved the source through the page
document's OWN path, which is ``None``, so the entire editor answered 404
"Source file not available" on every page of every PDF.
"""

from __future__ import annotations

import pytest

from fichero_server.models import DocType, Document
from tests.fixture_paths import sample_file


@pytest.fixture
def pdf_pages(db):
    """Ingest the 3-page fixture PDF; return (parent, [page docs by sequence])."""
    from fichero_server.importers.ingest import ingest_file

    parent = ingest_file(str(sample_file("multipage.pdf")), db=db)
    pages = sorted(db.query(Document, parent_id=parent.id), key=lambda d: d.sequence or 0)
    assert len(pages) == 3, "fixture PDF must split into three page children"
    assert all(page.doc_type == DocType.page and not page.path for page in pages)
    return parent, pages


def test_preview_renders_a_pdf_page_node(client, pdf_pages):
    """The page node previews its own page, not a 404 and not page 1."""
    _parent, pages = pdf_pages
    page3 = pages[2]

    response = client.get(
        f"/api/images/{page3.id}/preview", params={"apply_edits": False, "page": 3}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("image/")
    assert len(response.content) > 0


def test_preview_page_number_comes_from_the_document_not_the_caller(client, pdf_pages):
    """A caller that omits ``page`` still gets THAT page, never page 1.

    The client points at a node; the server resolves what the node means.
    """
    from PIL import Image
    import io

    _parent, pages = pdf_pages
    page1, page3 = pages[0], pages[2]

    first = client.get(f"/api/images/{page1.id}/preview", params={"apply_edits": False})
    third = client.get(f"/api/images/{page3.id}/preview", params={"apply_edits": False})
    assert first.status_code == 200 and third.status_code == 200
    # Different pages of the fixture carry different text, so the bytes differ.
    assert first.content != third.content

    # And a caller passing a WRONG page cannot redirect the render.
    misdirected = client.get(
        f"/api/images/{page3.id}/preview", params={"apply_edits": False, "page": 1}
    )
    assert misdirected.status_code == 200
    assert misdirected.content == third.content

    assert Image.open(io.BytesIO(third.content)).size[0] > 0


@pytest.mark.parametrize(
    "route,body",
    [
        ("rotate", {"angle": 90, "expand": True}),
        ("crop", {"left": 10, "top": 10, "width": 50, "height": 40}),
        ("enhance", {"brightness": 1.1, "contrast": 1.2, "sharpen": 1.0, "auto_levels": True}),
        ("remove-background", {"method": "threshold", "threshold": 200}),
    ],
)
def test_edit_operations_apply_to_a_pdf_page(client, pdf_pages, route, body):
    _parent, pages = pdf_pages
    page2 = pages[1]

    response = client.post(
        f"/api/images/{page2.id}/operations/{route}", json={**body, "page": 2}
    )
    assert response.status_code == 200, response.text
    chain = response.json()
    assert chain["document_id"] == page2.id
    assert len(chain["operations"]) == 1
    # The op is stamped with the page the SERVER resolved, so the preview's
    # per-page filter can find it again.
    assert chain["operations"][0]["page"] == 2

    edited = client.get(f"/api/images/{page2.id}/preview", params={"page": 2})
    raw = client.get(
        f"/api/images/{page2.id}/preview", params={"apply_edits": False, "page": 2}
    )
    assert edited.status_code == 200 and raw.status_code == 200
    assert edited.content != raw.content, f"{route} did not change the rendered page"


def test_straighten_and_revert_round_trip_on_a_pdf_page(client, pdf_pages):
    _parent, pages = pdf_pages
    page1 = pages[0]

    raw = client.get(
        f"/api/images/{page1.id}/preview", params={"apply_edits": False, "page": 1}
    )
    assert raw.status_code == 200

    straighten = client.post(
        f"/api/images/{page1.id}/operations/straighten", json={"page": 1}
    )
    assert straighten.status_code == 200, straighten.text
    assert straighten.json()["operations"][0]["page"] == 1

    revert = client.delete(f"/api/images/{page1.id}/edits")
    assert revert.status_code == 204

    after = client.get(f"/api/images/{page1.id}/preview", params={"page": 1})
    assert after.status_code == 200
    assert after.content == raw.content


def test_page_with_an_unreadable_parent_pdf_says_so(client, db):
    """No silent fallback: a page whose parent is gone 404s and names itself."""
    from fichero_server.models import FileType

    parent = Document(name="ghost.pdf", path="/nowhere/ghost.pdf", file_type=FileType.pdf)
    db.save(parent)
    page = Document(
        parent_id=parent.id, doc_type=DocType.page, name="ghost.pdf - Page 1", sequence=1
    )
    db.save(page)

    response = client.get(f"/api/images/{page.id}/preview", params={"page": 1})
    assert response.status_code == 404
    assert page.id in response.json()["detail"]
