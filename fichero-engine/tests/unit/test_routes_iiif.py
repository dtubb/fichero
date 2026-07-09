"""Tests for IIIF image API routes.

IIIF routes serve local images via the IIIF Image API v2.1. The router has
prefix="/iiif" and is mounted at "/api/iiif", creating the double-prefix
pattern: actual paths are at /api/iiif/iiif/...
"""

from PIL import Image

from fichero.knowledge_models import Annotation, AnnotationKind
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


class TestIIIFPresentationExport:
    def test_manifest_is_presentation3_and_points_at_annotation_page(
        self, client, db, test_package
    ):
        image_path = test_package / "files" / "ii" / "manifest.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (80, 50), "white").save(image_path, format="JPEG")

        doc = Document(
            id="doc-manifest-v3",
            name="Manifest Page",
            doc_type=DocType.file,
            file_type=FileType.image,
            path=str(image_path.relative_to(test_package)),
            page_content="A😀BC note text",
        )
        db.save(doc)
        db.save(
            Annotation(
                id="ann-text",
                document_id=doc.id,
                kind=AnnotationKind.note,
                text="note text",
                char_start=1,
                char_end=5,
            )
        )
        db.save(
            Annotation(
                id="ann-box",
                document_id=doc.id,
                kind=AnnotationKind.highlight,
                bbox=[0.1, 0.2, 0.3, 0.4],
            )
        )

        manifest = client.get(f"{BASE}/manifest/{doc.id}")
        assert manifest.status_code == 200
        body = manifest.json()
        assert body["@context"] == "http://iiif.io/api/presentation/3/context.json"
        assert body["type"] == "Manifest"
        assert "sequences" not in body
        canvas = body["items"][0]
        assert canvas["type"] == "Canvas"
        assert canvas["annotations"] == [
            {"id": f"/api/documents/{doc.id}/annotations.jsonld", "type": "AnnotationPage"}
        ]

        exported = client.get(f"/api/documents/{doc.id}/annotations.jsonld")
        assert exported.status_code == 200
        page = exported.json()
        assert page["@context"] == "http://www.w3.org/ns/anno.jsonld"
        assert page["type"] == "AnnotationPage"
        by_id = {item["id"]: item for item in page["items"]}
        text_target = by_id[f"/api/documents/{doc.id}/annotations/ann-text"]["target"]
        selectors = text_target["selector"]
        assert selectors[0] == {"type": "TextPositionSelector", "start": 1, "end": 5}
        assert selectors[1] == {"type": "TextQuoteSelector", "exact": "😀BC"}
        box_target = by_id[f"/api/documents/{doc.id}/annotations/ann-box"]["target"]
        assert box_target["selector"] == {
            "type": "FragmentSelector",
            "conformsTo": "http://www.w3.org/TR/media-frags/",
            "value": "xywh=pct:10,20,30,40",
        }
