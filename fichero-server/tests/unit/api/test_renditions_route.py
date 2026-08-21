"""GET /api/documents/{id}/renditions.

The route's job is small — fetch, order, envelope — so what these prove is the
part that is easy to get wrong: that "no renditions" and "no such document"
stay different answers, and that the ordering the clients depend on is applied
SERVER-side rather than left to whoever consumes it.
"""

from __future__ import annotations

from fichero_server.models import Document, Rendition
import fichero_server.api.routes.document.renditions  # noqa: F401


def _page(db, name: str = "page") -> Document:
    doc = Document(name=name)
    db.save(doc)
    return doc


def test_returns_renditions_in_display_order(client, db):
    doc = _page(db)
    for role in ("original", "enhanced", "rotated"):
        db.save(Rendition(document_id=doc.id, role=role, path=f"/{role}.jpg"))

    response = client.get(f"/api/documents/{doc.id}/renditions")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    # Ordered by the ENGINE, not by insertion: enhanced outranks original.
    assert [item["role"] for item in body["items"]] == [
        "enhanced",
        "rotated",
        "original",
    ]


def test_primary_is_first_even_against_role_preference(client, db):
    doc = _page(db)
    db.save(Rendition(document_id=doc.id, role="enhanced", path="/e.jpg"))
    db.save(Rendition(document_id=doc.id, role="original", path="/o.jpg", is_primary=True))

    body = client.get(f"/api/documents/{doc.id}/renditions").json()

    assert body["items"][0]["role"] == "original"


def test_existing_document_with_no_renditions_is_an_empty_list(client, db):
    """Legitimate: folders have none, and so does a node whose bytes were
    never materialised."""
    doc = _page(db, "a folder")

    response = client.get(f"/api/documents/{doc.id}/renditions")

    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}


def test_missing_document_is_404_not_an_empty_list(client, db):
    """The distinction that matters. A client that cannot tell these apart
    renders an empty flip strip for a typo'd id and calls it a page with one
    image."""
    response = client.get("/api/documents/no-such-document/renditions")

    assert response.status_code == 404
    assert "no-such-document" in response.json()["detail"]


def test_renditions_of_other_documents_are_not_returned(client, db):
    mine = _page(db, "mine")
    theirs = _page(db, "theirs")
    db.save(Rendition(document_id=mine.id, role="enhanced", path="/mine.jpg"))
    db.save(Rendition(document_id=theirs.id, role="enhanced", path="/theirs.jpg"))

    body = client.get(f"/api/documents/{mine.id}/renditions").json()

    assert body["count"] == 1
    assert body["items"][0]["path"] == "/mine.jpg"


def test_transform_round_trips_through_the_wire(client, db):
    """The honest-exception field: a cropped/deskewed rendition must arrive
    still saying so, or the client silently assumes the node's frame."""
    doc = _page(db)
    db.save(
        Rendition(
            document_id=doc.id,
            role="enhanced",
            path="/e.jpg",
            transform={
                "rect": [0.02, 0.01, 0.95, 0.98],
                "confidence": "measured",
                "method": "deskew-crop",
            },
        )
    )

    item = client.get(f"/api/documents/{doc.id}/renditions").json()["items"][0]

    assert item["transform"]["method"] == "deskew-crop"
    assert item["transform"]["confidence"] == "measured"


def test_pure_resample_reports_null_transform(client, db):
    """The common case must be distinguishable from 'unknown' on the wire."""
    doc = _page(db)
    db.save(Rendition(document_id=doc.id, role="enhanced", path="/e.jpg"))

    item = client.get(f"/api/documents/{doc.id}/renditions").json()["items"][0]

    assert item["transform"] is None
