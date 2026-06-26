"""Tests for IIIF image API routes.

IIIF routes serve local images via the IIIF Image API v2.1. The router has
prefix="/iiif" and is mounted at "/api/iiif", creating the double-prefix
pattern: actual paths are at /api/iiif/iiif/...
"""

from PIL import Image

from fichero.models import Document, DocType, FileType


BASE = "/api/iiif/iiif"


# ---------------------------------------------------------------------------
# GET /api/iiif/iiif/{identifier}/info.json
# ---------------------------------------------------------------------------


class TestIIIFImageInfo:
    def test_missing_document_returns_404(self, client):
        r = client.get(f"{BASE}/no-such-doc/info.json")
        assert r.status_code == 404

    def test_document_without_image_path_returns_404(self, client, db):
        # A document with no file_type (text doc) has no image path → 404
        doc = Document(id="doc-no-img", name="Text doc", doc_type=DocType.file)
        db.save(doc)

        r = client.get(f"{BASE}/doc-no-img/info.json")
        assert r.status_code == 404

    def test_relative_image_path_resolves_against_current_library(
        self, client, db, test_package
    ):
        image_path = test_package / "files" / "ii" / "scan.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (40, 20), "white").save(image_path, format="JPEG")

        doc = Document(
            id="doc-rel-img",
            name="scan.jpg",
            doc_type=DocType.file,
            file_type=FileType.image,
            path=str(image_path.relative_to(test_package)),
        )
        db.save(doc)

        r = client.get(f"{BASE}/{doc.id}/info.json")
        assert r.status_code == 200
        assert r.json()["width"] == 40
        assert r.json()["height"] == 20

    def test_out_of_root_image_path_returns_404(self, client, db):
        doc = Document(
            id="doc-outside-img",
            name="passwd",
            doc_type=DocType.file,
            file_type=FileType.image,
            path="/etc/passwd",
        )
        db.save(doc)

        r = client.get(f"{BASE}/{doc.id}/info.json")

        assert r.status_code == 404
