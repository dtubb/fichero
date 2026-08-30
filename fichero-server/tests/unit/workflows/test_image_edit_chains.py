"""Coverage for workflow image-edit chain persistence."""

from __future__ import annotations

from fichero_server.models import Document, ImageEditChain
from fichero_server.workflows.tools import image_edit_chains as chains


def test_candidate_document_ids_deduplicates_all_workflow_sources():
    ids = chains._candidate_document_ids(
        {"documents": [{"id": "a"}, {"id": "a"}, {"id": "ignored"}]},
        {"documents": [{"id": "b"}], "selected_doc_ids": ["a", "c"]},
    )

    assert ids == ["a", "ignored", "b", "c"]


def test_append_persists_new_and_existing_chains(monkeypatch):
    first = Document(id="doc-1", name="one.jpg")
    second = Document(id="doc-2", name="two.jpg")
    existing = ImageEditChain(document_id=first.id, operations=[{"op": "old"}])

    class DB:
        def __init__(self):
            self.saved = []

        def get(self, _model, doc_id):
            return {first.id: first, second.id: second}.get(doc_id)

        def query(self, _model, **filters):
            return [existing] if filters["document_id"] == first.id else []

        def save(self, value):
            self.saved.append(value)

    db = DB()
    monkeypatch.setattr(chains.db_manager, "get_database", lambda _path: db)

    records = chains.append_image_edit_operations(
        {"documents": [{"id": first.id}]},
        {"library_path": "/tmp/lib", "selected_doc_ids": [first.id, second.id]},
        lambda doc: {"op": "rotate", "document": doc.id},
    )

    assert [record["document_id"] for record in records] == [first.id, second.id]
    assert existing.operations[1]["op"] == "rotate"
    assert len(db.saved) == 2
    assert db.saved[1].document_id == second.id


def test_append_without_library_path_is_noop():
    assert chains.append_image_edit_operations({}, {}, lambda _doc: {}) == []


class TestQuarterTurnsAreLossless:
    """Daniel, 2026-08-30: "edits seemed to make the quality worse". Every
    rotate-left/right click was bicubic-resampling the page — a 90° turn must
    be a pixel-exact transpose, never an interpolation."""

    def _checker(self):
        from PIL import Image
        img = Image.new("RGB", (4, 2))
        px = img.load()
        for x in range(4):
            for y in range(2):
                px[x, y] = (255, 0, 0) if (x + y) % 2 == 0 else (0, 0, 255)
        return img

    def test_rotate_90_is_pixel_exact(self):
        from PIL import Image
        from fichero_server.media.image_ops import apply_operation

        img = self._checker()
        out = apply_operation(img, {"op": "rotate", "params": {"angle": 90}})
        assert out.size == (2, 4)
        # Pixel-exact against PIL's lossless transpose — no interpolation.
        assert list(out.getdata()) == list(img.transpose(Image.Transpose.ROTATE_90).getdata())

    def test_rotate_270_via_negative_90(self):
        from PIL import Image
        from fichero_server.media.image_ops import apply_operation

        img = self._checker()
        out = apply_operation(img, {"op": "rotate", "params": {"angle": -90}})
        assert list(out.getdata()) == list(img.transpose(Image.Transpose.ROTATE_270).getdata())

    def test_fractional_angle_still_interpolates(self):
        from fichero_server.media.image_ops import apply_operation

        img = self._checker()
        out = apply_operation(img, {"op": "rotate", "params": {"angle": 3.5}})
        # Expanded canvas: interpolation path taken, not the transpose.
        assert out.size != img.size
