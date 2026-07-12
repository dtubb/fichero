"""Tests for image-editing routes (#462, #463, #466, #467, #468)."""

from __future__ import annotations

import asyncio
import io
import time
from pathlib import Path

import httpx
import pytest
from PIL import Image

from fichero.api.auth import initialize_token
from fichero.api.main import app
from fichero.api.routes import image_editing
from fichero.models import DocType, Document, FileType


def _make_image_doc(db, tmp_path, name: str = "sample.jpg", size: tuple[int, int] = (80, 50)):
    image_path = db.path.parent / "files" / name
    image_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, "white")
    img.putpixel((0, 0), (255, 0, 0))
    img.save(image_path, format="JPEG")

    doc = Document(name=name, path=str(image_path), file_type=FileType.image)
    db.save(doc)
    return doc


def _make_gray_image_doc(
    db, tmp_path, name: str = "gray.jpg", size: tuple[int, int] = (80, 50)
):
    image_path = db.path.parent / "files" / name
    image_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, (128, 128, 128))
    img.putpixel((0, 0), (255, 0, 0))
    img.save(image_path, format="JPEG")

    doc = Document(name=name, path=str(image_path), file_type=FileType.image)
    db.save(doc)
    return doc


def _make_foreground_image_doc(db, tmp_path, name: str = "foreground.png"):
    image_path = db.path.parent / "files" / name
    image_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (60, 40), "white")
    for x in range(20, 40):
        for y in range(10, 30):
            img.putpixel((x, y), (10, 20, 30))
    img.save(image_path, format="PNG")

    doc = Document(name=name, path=str(image_path), file_type=FileType.image)
    db.save(doc)
    return doc


def _make_segmentable_image_doc(db, tmp_path, name: str = "segments.png"):
    image_path = db.path.parent / "files" / name
    image_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (100, 60), "white")
    for x in range(10, 30):
        for y in range(10, 30):
            img.putpixel((x, y), (0, 0, 0))
    for x in range(65, 90):
        for y in range(20, 45):
            img.putpixel((x, y), (0, 0, 0))
    img.save(image_path, format="PNG")

    doc = Document(name=name, path=str(image_path), file_type=FileType.image)
    db.save(doc)
    return doc


class TestImageEditChainRoutes:
    @pytest.mark.parametrize(
        "operation",
        [
            {"op": "invent", "params": {}},
            {"op": "rotate", "params": {"angle": 999}},
            {"op": "crop", "params": {"left": 0, "top": 0, "width": -1, "height": 2}},
        ],
    )
    def test_put_rejects_invalid_operations(self, client, db, tmp_path, operation):
        doc = _make_image_doc(db, tmp_path)
        response = client.put(f"/api/images/{doc.id}/edits", json={"operations": [operation]})
        assert response.status_code == 422

    def test_valid_chain_round_trips_without_transient_path(self, client, db, tmp_path):
        doc = _make_image_doc(db, tmp_path)
        response = client.put(
            f"/api/images/{doc.id}/edits",
            json={"operations": [{"op": "rotate", "params": {"angle": 90}}]},
        )
        assert response.status_code == 200
        assert "derived_path" not in response.json()["operations"][0]
        assert client.get(f"/api/images/{doc.id}/preview").status_code == 200

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
        assert ops[0]["params"] == {
            "left": 10,
            "top": 15,
            "width": 40,
            "height": 30,
            "auto_orient": True,
        }
        assert "derived_path" not in ops[0]

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
        assert "derived_path" not in ops[0]

    def test_enhance_operation_appends_chain(self, client, db, tmp_path):
        doc = _make_gray_image_doc(db, tmp_path)
        enhance = client.post(
            f"/api/images/{doc.id}/operations/enhance",
            json={
                "brightness": 0.5,
                "contrast": 1.25,
                "sharpen": 1.5,
                "auto_levels": True,
                "page": 1,
            },
        )
        assert enhance.status_code == 200
        ops = enhance.json()["operations"]
        assert len(ops) == 1
        assert ops[0]["op"] == "enhance"
        assert ops[0]["params"] == {
            "brightness": 0.5,
            "contrast": 1.25,
            "sharpen": 1.5,
            "auto_levels": True,
        }
        assert "derived_path" not in ops[0]

    def test_remove_background_operation_appends_chain(self, client, db, tmp_path):
        doc = _make_foreground_image_doc(db, tmp_path)
        rmbg = client.post(
            f"/api/images/{doc.id}/operations/remove-background",
            json={"method": "threshold", "threshold": 5, "page": 1},
        )
        assert rmbg.status_code == 200
        ops = rmbg.json()["operations"]
        assert len(ops) == 1
        assert ops[0]["op"] == "remove_background"
        assert ops[0]["params"] == {"method": "threshold", "threshold": 5}
        assert "derived_path" not in ops[0]

    def test_segment_operation_appends_chain_and_creates_chunk_docs(
        self, client, db, tmp_path
    ):
        doc = _make_segmentable_image_doc(db, tmp_path)
        rmbg = client.post(
            f"/api/images/{doc.id}/operations/remove-background",
            json={"method": "threshold", "threshold": 5, "page": 1},
        )
        assert rmbg.status_code == 200

        segment = client.post(
            f"/api/images/{doc.id}/operations/segment",
            json={
                "method": "foreground",
                "threshold": 5,
                "min_area": 50,
                "max_segments": 10,
                "page": 1,
            },
        )
        assert segment.status_code == 200
        ops = segment.json()["operations"]
        assert [op["op"] for op in ops] == ["remove_background", "segment"]
        assert len(ops[1]["segments"]) == 2
        assert len(ops[1]["child_document_ids"]) == 2
        assert "derived_path" not in ops[1]

        children = sorted(
            db.query(Document, parent_id=doc.id, doc_type=DocType.chunk),
            key=lambda child: child.sequence or 0,
        )
        assert [child.sequence for child in children] == [1, 2]
        assert [child.path for child in children] == [doc.path, doc.path]
        assert children[0].bbox == (10, 10, 20, 20)
        assert children[1].bbox == (65, 20, 25, 25)
        assert children[0].metadata["view_kind"] == "image_segment"
        assert children[0].metadata["source_document_id"] == doc.id

    @pytest.mark.anyio
    async def test_crop_operation_does_not_block_concurrent_request(
        self, db, test_package, tmp_path, monkeypatch
    ):
        doc = _make_image_doc(db, tmp_path, size=(120, 90))

        from fichero.api.routes import image_editing as routes

        original_apply_operation = routes._apply_operation

        def slow_apply_operation(image, op):
            time.sleep(0.25)
            return original_apply_operation(image, op)

        monkeypatch.setattr(routes, "_apply_operation", slow_apply_operation)

        transport = httpx.ASGITransport(app=app)
        # The unit conftest re-attaches the auth middleware; a raw httpx
        # AsyncClient (unlike TestClient) isn't covered by the conftest token
        # injection, so carry the bootstrap bearer token explicitly.
        headers = {
            "X-Fichero-Library-Path": str(test_package),
            "Authorization": f"Bearer {initialize_token()}",
        }
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", headers=headers
        ) as async_client:
            crop_task = asyncio.create_task(
                async_client.post(
                    f"/api/images/{doc.id}/operations/crop",
                    json={"left": 10, "top": 10, "width": 30, "height": 20, "page": 1},
                )
            )
            await asyncio.sleep(0.02)
            edits_response = await async_client.get(f"/api/images/{doc.id}/edits")
            crop_response = await crop_task

        assert edits_response.status_code == 200
        assert crop_response.status_code == 200


class TestReversibleImageSplit:
    def test_archive_black_border_remover_masks_and_crops(self):
        pytest.importorskip("cv2")
        from fichero.api.routes.image_editing import _remove_black_background_opencv

        image = Image.new("RGB", (100, 80), "black")
        for x in range(15, 85):
            for y in range(10, 70):
                image.putpixel((x, y), (245, 245, 245))

        cleaned = _remove_black_background_opencv(image)
        assert cleaned.mode == "RGBA"
        assert cleaned.size[0] < image.size[0]
        assert cleaned.size[1] < image.size[1]

    def test_split_children_keep_bbox_and_lineage_then_unsplit(self, client, db, tmp_path):
        source = _make_image_doc(db, tmp_path, size=(80, 50))
        source_before = db.get(Document, source.id).model_dump(mode="json")

        split = client.post(
            f"/api/images/{source.id}/split",
            json={"bboxes": [[0, 0, 40, 50], [40, 0, 40, 50]]},
        )
        assert split.status_code == 200
        children = split.json()["children"]
        assert [child["bbox"] for child in children] == [[0, 0, 40, 50], [40, 0, 40, 50]]
        assert all(child["metadata"]["derived_from"] == source.id for child in children)
        assert all(child["metadata"]["source_bbox"] == child["bbox"] for child in children)
        assert db.get(Document, source.id).model_dump(mode="json") == source_before

        unsplit = client.post(f"/api/images/{source.id}/unsplit")
        assert unsplit.status_code == 200
        assert set(unsplit.json()["deleted_child_ids"]) == {child["id"] for child in children}
        assert all(db.get(Document, child["id"]).deleted_at is not None for child in children)
        assert db.get(Document, source.id).model_dump(mode="json") == source_before

    def test_archive_auto_detector_creates_two_page_regions(self, client, db, tmp_path):
        pytest.importorskip("cv2")
        source = _make_image_doc(db, tmp_path, name="spread.png", size=(1200, 600))
        image_path = Path(source.path)
        image = Image.open(image_path)
        for y in range(image.height):
            image.putpixel((600, y), (0, 0, 0))
        image.save(image_path, format="PNG")

        split = client.post(f"/api/images/{source.id}/split", json={})
        assert split.status_code == 200
        assert [child["bbox"][2] for child in split.json()["children"]] == [600, 600]

    def test_split_rejects_empty_and_overlapping_regions(self, client, db, tmp_path):
        source = _make_image_doc(db, tmp_path)

        empty = client.post(f"/api/images/{source.id}/split", json={"bboxes": []})
        assert empty.status_code == 422

        overlapping = client.post(
            f"/api/images/{source.id}/split",
            json={"bboxes": [[0, 0, 50, 50], [40, 0, 40, 50]]},
        )
        assert overlapping.status_code == 422


class TestReversibleImageCrop:
    def test_crop_child_preserves_source_then_uncrop(self, client, db, tmp_path):
        source = _make_image_doc(db, tmp_path, size=(100, 80))
        source_before = db.get(Document, source.id).model_dump(mode="json")

        cropped = client.post(
            f"/api/images/{source.id}/crop",
            json={"left": 10, "top": 15, "width": 50, "height": 40},
        )
        assert cropped.status_code == 200
        child = cropped.json()["child"]
        assert child["bbox"] == [10, 15, 50, 40]
        assert child["metadata"]["derived_from"] == source.id
        assert db.get(Document, source.id).model_dump(mode="json") == source_before

        uncropped = client.post(f"/api/images/{child['id']}/uncrop")
        assert uncropped.status_code == 200
        assert db.get(Document, child["id"]).deleted_at is not None
        assert db.get(Document, source.id).model_dump(mode="json") == source_before

    def test_batch_crop_applies_one_spec_to_each_source(self, client, db, tmp_path):
        first = _make_image_doc(db, tmp_path, name="first.jpg", size=(100, 80))
        second = _make_image_doc(db, tmp_path, name="second.jpg", size=(100, 80))

        response = client.post(
            "/api/images/crops/batch",
            json={
                "document_ids": [first.id, second.id],
                "left": 5,
                "top": 10,
                "width": 40,
                "height": 30,
            },
        )
        assert response.status_code == 200
        assert [item["source_document_id"] for item in response.json()["children"]] == [
            first.id,
            second.id,
        ]

    def test_crop_rejects_out_of_bounds_bbox(self, client, db, tmp_path):
        source = _make_image_doc(db, tmp_path, size=(100, 80))

        response = client.post(
            f"/api/images/{source.id}/crop",
            json={"left": 80, "top": 20, "width": 30, "height": 40},
        )
        assert response.status_code == 422


class TestImagePreviewRoute:
    def test_preview_resolves_library_relative_source_path(
        self, client, db, test_package
    ):
        image_path = test_package / "files" / "im" / "preview.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (77, 55), "white").save(image_path, format="JPEG")

        doc = Document(
            name="preview.jpg",
            path=str(image_path.relative_to(test_package)),
            file_type=FileType.image,
        )
        db.save(doc)

        r = client.get(f"/api/images/{doc.id}/preview?apply_edits=false")
        assert r.status_code == 200
        rendered = Image.open(io.BytesIO(r.content))
        assert rendered.size == (77, 55)

    def test_preview_returns_original_without_edits(self, client, db, tmp_path):
        doc = _make_image_doc(db, tmp_path, size=(90, 60))
        r = client.get(f"/api/images/{doc.id}/preview?apply_edits=false")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/jpeg")
        img = Image.open(io.BytesIO(r.content))
        assert img.size == (90, 60)

    def test_preview_uses_worker_thread(self, db, tmp_path, monkeypatch):
        doc = _make_image_doc(db, tmp_path)
        async def rendered(*_args):
            return b"image", "image/jpeg"
        monkeypatch.setattr(image_editing.asyncio, "to_thread", rendered)
        response = asyncio.run(image_editing.preview_image(doc.id, db=db))
        assert response.body == b"image"

    def test_preview_cache_invalidates_on_chain_change(self, db, tmp_path, monkeypatch):
        doc = _make_image_doc(db, tmp_path)
        calls = 0
        original = image_editing._load_source_image
        def counted(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)
        monkeypatch.setattr(image_editing, "_load_source_image", counted)
        image_editing._render_preview(db, doc.id, True, 1)
        image_editing._render_preview(db, doc.id, True, 1)
        assert calls == 1
        image_editing.set_operations_impl(
            db, doc.id, [{"op": "rotate", "params": {"angle": 90}}]
        )
        image_editing._render_preview(db, doc.id, True, 1)
        assert calls == 2

    def test_preview_honours_exif_orientation(self, client, db, tmp_path):
        # A JPEG whose pixels are stored landscape (90x60) but tagged
        # orientation=6 (rotate 90° for display) should come back oriented
        # portrait (60x90) — matching what the SwiftUI viewer / Finder show, so
        # the editor opens at the same orientation as the viewer (#1529).
        image_path = db.path.parent / "files" / "rotated.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (90, 60), "white")
        exif = Image.Exif()
        exif[0x0112] = 6  # Orientation: rotate 90° CW for display
        img.save(image_path, format="JPEG", exif=exif)

        doc = Document(name="rotated.jpg", path=str(image_path), file_type=FileType.image)
        db.save(doc)

        r = client.get(f"/api/images/{doc.id}/preview?apply_edits=false")
        assert r.status_code == 200
        rendered = Image.open(io.BytesIO(r.content))
        assert rendered.size == (60, 90)

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

    def test_preview_applies_saved_fuzzy_clean_operation(self, client, db, tmp_path):
        image_path = db.path.parent / "files" / "speckle.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (9, 9), (128, 128, 128))
        image.putpixel((4, 4), (0, 0, 0))
        image.save(image_path, format="PNG")
        doc = Document(name="speckle.png", path=str(image_path), file_type=FileType.image)
        db.save(doc)

        put = client.put(
            f"/api/images/{doc.id}/edits",
            json={
                "operations": [
                    {
                        "op": "fuzzy_clean",
                        "page": 1,
                        "params": {"despeckle_radius": 3, "background_clean": False},
                    }
                ]
            },
        )
        assert put.status_code == 200

        edited = client.get(f"/api/images/{doc.id}/preview")
        assert edited.status_code == 200
        edited_img = Image.open(io.BytesIO(edited.content))
        assert edited_img.getpixel((4, 4))[0] > 0

    def test_preview_enhance_operation_supports_saved_denoise_param(
        self, client, db, tmp_path
    ):
        image_path = db.path.parent / "files" / "speckle.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (9, 9), (128, 128, 128))
        image.putpixel((4, 4), (0, 0, 0))
        image.save(image_path, format="PNG")
        doc = Document(name="speckle.png", path=str(image_path), file_type=FileType.image)
        db.save(doc)

        put = client.put(
            f"/api/images/{doc.id}/edits",
            json={
                "operations": [
                    {
                        "op": "enhance",
                        "page": 1,
                        "params": {
                            "brightness": 1.0,
                            "contrast": 1.0,
                            "sharpen": 1.0,
                            "denoise": True,
                        },
                    }
                ]
            },
        )
        assert put.status_code == 200

        edited = client.get(f"/api/images/{doc.id}/preview")
        assert edited.status_code == 200
        edited_img = Image.open(io.BytesIO(edited.content))
        assert edited_img.getpixel((4, 4))[0] > 0

    def test_preview_regenerates_from_enhance_operation_chain(self, client, db, tmp_path):
        doc = _make_gray_image_doc(db, tmp_path, size=(60, 40))
        enhance = client.post(
            f"/api/images/{doc.id}/operations/enhance",
            json={"brightness": 0.5, "contrast": 1.0, "sharpen": 1.0},
        )
        assert enhance.status_code == 200

        original = client.get(f"/api/images/{doc.id}/preview?apply_edits=false")
        edited = client.get(f"/api/images/{doc.id}/preview")
        assert original.status_code == 200
        assert edited.status_code == 200

        original_img = Image.open(io.BytesIO(original.content))
        edited_img = Image.open(io.BytesIO(edited.content))
        assert original_img.size == (60, 40)
        assert edited_img.size == (60, 40)
        assert original_img.getpixel((30, 20))[0] > edited_img.getpixel((30, 20))[0]

    def test_preview_regenerates_remove_background_as_png(
        self, client, db, tmp_path
    ):
        doc = _make_foreground_image_doc(db, tmp_path)
        rmbg = client.post(
            f"/api/images/{doc.id}/operations/remove-background",
            json={"method": "threshold", "threshold": 5, "page": 1},
        )
        assert rmbg.status_code == 200

        original = client.get(f"/api/images/{doc.id}/preview?apply_edits=false")
        edited = client.get(f"/api/images/{doc.id}/preview")
        assert original.status_code == 200
        assert edited.status_code == 200
        assert original.headers["content-type"].startswith("image/jpeg")
        assert edited.headers["content-type"].startswith("image/png")

        edited_img = Image.open(io.BytesIO(edited.content))
        assert edited_img.mode == "RGBA"
        assert edited_img.getpixel((0, 0))[3] == 0
        assert edited_img.getpixel((30, 20))[3] == 255

    def test_preview_regenerates_after_segment_without_copying_source(
        self, client, db, tmp_path
    ):
        doc = _make_segmentable_image_doc(db, tmp_path)
        segment = client.post(
            f"/api/images/{doc.id}/operations/segment",
            json={"method": "foreground", "threshold": 5, "min_area": 50},
        )
        assert segment.status_code == 200

        edited = client.get(f"/api/images/{doc.id}/preview")
        assert edited.status_code == 200
        assert edited.headers["content-type"].startswith("image/jpeg")
        img = Image.open(io.BytesIO(edited.content))
        assert img.size == (100, 60)

        children = db.query(Document, parent_id=doc.id, doc_type=DocType.chunk)
        assert len(children) == 2
        assert all(child.path == doc.path for child in children)

    def test_preview_missing_source_returns_404(self, client, db):
        doc = Document(name="missing.jpg", path="/tmp/does-not-exist.jpg", file_type=FileType.image)
        db.save(doc)
        r = client.get(f"/api/images/{doc.id}/preview")
        assert r.status_code == 404
