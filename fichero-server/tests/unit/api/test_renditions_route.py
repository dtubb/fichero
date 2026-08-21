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


class TestRenditionContent:
    """Serving a rendition's bytes.

    The ownership check is a security boundary, not tidiness: without it a
    valid rendition id from ANY document would serve through any other
    document's URL, making the document segment of the path decorative.
    """

    def _served(self, db, tmp_path, name="e.jpg", body=b"\xff\xd8jpegbytes"):
        doc = _page(db)
        source = tmp_path / name
        source.write_bytes(body)
        rendition = Rendition(document_id=doc.id, role="enhanced", path=str(source))
        db.save(rendition)
        return doc, rendition, body

    def test_serves_the_bytes(self, client, db, tmp_path):
        doc, rendition, body = self._served(db, tmp_path)

        response = client.get(f"/api/documents/{doc.id}/renditions/{rendition.id}/content")

        assert response.status_code == 200
        assert response.content == body

    def test_rendition_of_another_document_is_not_served(self, client, db, tmp_path):
        """The load-bearing check. A real rendition id must not be reachable
        through a different document's URL."""
        _, rendition, _ = self._served(db, tmp_path)
        other = _page(db, "other")

        response = client.get(f"/api/documents/{other.id}/renditions/{rendition.id}/content")

        assert response.status_code == 404

    def test_missing_document_is_404(self, client, db, tmp_path):
        _, rendition, _ = self._served(db, tmp_path)

        response = client.get(f"/api/documents/nope/renditions/{rendition.id}/content")

        assert response.status_code == 404

    def test_missing_rendition_is_404(self, client, db):
        doc = _page(db)

        response = client.get(f"/api/documents/{doc.id}/renditions/nope/content")

        assert response.status_code == 404

    def test_unmaterialized_rendition_is_404_not_a_deeper_failure(self, client, db, tmp_path):
        """A knowable absent state recorded at import. Better an honest 404
        than a path failing deeper in the stack with a worse error."""
        doc = _page(db)
        source = tmp_path / "never-written.jpg"
        source.write_bytes(b"present-but-flagged-absent")
        rendition = Rendition(
            document_id=doc.id, role="original", path=str(source), materialized=False
        )
        db.save(rendition)

        response = client.get(f"/api/documents/{doc.id}/renditions/{rendition.id}/content")

        assert response.status_code == 404

    def test_path_escaping_the_permitted_roots_is_refused(self, client, db):
        """The stored path is confined by the same authority the IIIF image
        route uses. A row pointing outside the permitted roots must not become
        an arbitrary-file-read."""
        doc = _page(db)
        rendition = Rendition(
            document_id=doc.id, role="original", path="/etc/passwd"
        )
        db.save(rendition)

        response = client.get(f"/api/documents/{doc.id}/renditions/{rendition.id}/content")

        assert response.status_code == 404

    def test_media_type_is_explicit_never_the_mimetypes_module(self, client, db, tmp_path):
        """The content-type comes from the route's own suffix map.

        A bare FileResponse falls back to Python's mimetypes module, whose
        first-use initializer reads /etc/apache2/mime.types — denied in the
        SANDBOXED engine, so every flip 500ed with PermissionError while
        these tests, unsandboxed, stayed green (live repro 2026-08-21). The
        header is the observable proof the explicit map is in the path.
        """
        import fichero_server.api.routes.document.renditions as renditions_module

        doc = _page(db)
        path = tmp_path / "page.jpg"
        path.write_bytes(b"\xff\xd8\xffjpegish")
        rendition = Rendition(document_id=doc.id, role="enhanced", path=str(path))
        db.save(rendition)

        assert renditions_module.IMAGE_MEDIA_TYPES[".jpg"] == "image/jpeg"
        response = client.get(f"/api/documents/{doc.id}/renditions/{rendition.id}/content")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"

    def test_missing_file_on_disk_is_404(self, client, db, tmp_path):
        doc = _page(db)
        rendition = Rendition(
            document_id=doc.id, role="enhanced", path=str(tmp_path / "absent.jpg")
        )
        db.save(rendition)

        response = client.get(f"/api/documents/{doc.id}/renditions/{rendition.id}/content")

        assert response.status_code == 404
