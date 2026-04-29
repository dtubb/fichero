"""Tests for IIIF image API routes.

IIIF routes serve local images via the IIIF Image API v2.1. The router has
prefix="/iiif" and is mounted at "/api/iiif", creating the double-prefix
pattern: actual paths are at /api/iiif/iiif/...
"""

import pytest

from fichero.models import Document, DocType


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
