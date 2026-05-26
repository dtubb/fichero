"""Tests for image-editing routes (#462, #463)."""

from __future__ import annotations

import io

from PIL import Image

from fichero.models import Document, FileType


def _make_image_doc(db, tmp_path, name: str = "sample.jpg", size: tuple[int, int] = (80, 50)):
    image_path = tmp_path / name
    img = Image.new("RGB", size, "white")
    img.putpixel((0, 0), (255, 0, 0))
    img.save(image_path, format="JPEG")

    doc = Document(name=name, path=str(image_path), file_type=FileType.image)
    db.save(doc)
    return doc


class TestImageEditChainRoutes:
    def test_put_get_delete_chain(self, client, db, tmp_path):
        doc = _make_image_doc(db, tmp_path)

        put = client.put(
            f"/api/images/{doc.id}/edits",
            json={
                "operations": [
                    {"op": "rotate", "params": {"angle": 90}},
                    {"op": "grayscale"},
                ]
            },
        )
        assert put.status_code == 200
        assert len(put.json()["operations"]) == 2

        get = client.get(f"/api/images/{doc.id}/edits")
        assert get.status_code == 200
        assert get.json()["operations"][0]["op"] == "rotate"

        delete = client.delete(f"/api/images/{doc.id}/edits")
        assert delete.status_code == 204

        get_after = client.get(f"/api/images/{doc.id}/edits")
        assert get_after.status_code == 200
        assert get_after.json()["operations"] == []

    def test_missing_document_returns_404(self, client):
        r = client.get("/api/images/no-such-doc/edits")
        assert r.status_code == 404

    def test_crop_operation_appends_chain(self, client, db, tmp_path):
        doc = _make_image_doc(db, tmp_path, size=(120, 90))
        crop = client.post(
            f"/api/images/{doc.id}/operations/crop",
            json={"left": 10, "top": 15, "width": 40, "height": 30, "page": 1},
        )
        assert crop.status_code == 200
        ops = crop.json()["operations"]
        assert len(ops) == 1
        assert ops[0]["op"] == "crop"
        assert ops[0]["params"] == {"left": 10, "top": 15, "width": 40, "height": 30}
        assert "derived_path" in ops[0]

    def test_rotate_operation_appends_chain(self, client, db, tmp_path):
        doc = _make_image_doc(db, tmp_path, size=(80, 50))
        rotate = client.post(
            f"/api/images/{doc.id}/operations/rotate",
            json={"angle": 90, "expand": True, "page": 1},
        )
        assert rotate.status_code == 200
        ops = rotate.json()["operations"]
        assert len(ops) == 1
        assert ops[0]["op"] == "rotate"
        assert ops[0]["params"] == {"angle": 90.0, "expand": True}
        assert "derived_path" in ops[0]


class TestImagePreviewRoute:
    def test_preview_returns_original_without_edits(self, client, db, tmp_path):
        doc = _make_image_doc(db, tmp_path, size=(90, 60))
        r = client.get(f"/api/images/{doc.id}/preview?apply_edits=false")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/jpeg")
        img = Image.open(io.BytesIO(r.content))
        assert img.size == (90, 60)

    def test_preview_applies_edit_chain(self, client, db, tmp_path):
        doc = _make_image_doc(db, tmp_path, size=(100, 80))
        put = client.put(
            f"/api/images/{doc.id}/edits",
            json={"operations": [{"op": "crop", "params": {"left": 10, "top": 20, "width": 30, "height": 25}}]},
        )
        assert put.status_code == 200

        r = client.get(f"/api/images/{doc.id}/preview")
        assert r.status_code == 200
        img = Image.open(io.BytesIO(r.content))
        assert img.size == (30, 25)

    def test_preview_regenerates_from_crop_operation_chain(self, client, db, tmp_path):
        doc = _make_image_doc(db, tmp_path, size=(140, 100))
        crop = client.post(
            f"/api/images/{doc.id}/operations/crop",
            json={"left": 20, "top": 10, "width": 50, "height": 40, "page": 1},
        )
        assert crop.status_code == 200

        r = client.get(f"/api/images/{doc.id}/preview")
        assert r.status_code == 200
        img = Image.open(io.BytesIO(r.content))
        assert img.size == (50, 40)

    def test_preview_regenerates_from_rotate_operation_chain(self, client, db, tmp_path):
        doc = _make_image_doc(db, tmp_path, size=(80, 50))
        rotate = client.post(
            f"/api/images/{doc.id}/operations/rotate",
            json={"angle": 90, "expand": True, "page": 1},
        )
        assert rotate.status_code == 200

        r = client.get(f"/api/images/{doc.id}/preview")
        assert r.status_code == 200
        img = Image.open(io.BytesIO(r.content))
        assert img.size == (50, 80)

    def test_preview_missing_source_returns_404(self, client, db):
        doc = Document(name="missing.jpg", path="/tmp/does-not-exist.jpg", file_type=FileType.image)
        db.save(doc)
        r = client.get(f"/api/images/{doc.id}/preview")
        assert r.status_code == 404
