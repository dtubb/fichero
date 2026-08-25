"""The Apple Vision geometry pass prefers a frame-true background_removed
rendition (2026-08-24 eval: near-total faint-pencil word recall vs ~2/3 on
the original). ``transform is None`` is the frame guarantee; anything else —
transformed, unmaterialized, missing bytes, wrong role — falls back to the
original pixels, silently.
"""

from __future__ import annotations

from fichero_server.db import db_manager
from fichero_server.models import NodeRegion, Rendition
from fichero_server.workflows.tools.vision_base import (
    _frame_true_background_removed_path,
)


def _library(tmp_path):
    package = tmp_path / "test.fichero"
    package.mkdir()
    return str(package), db_manager.get_database(str(package))


def _rendition(doc_id, path, **over):
    base = dict(document_id=doc_id, role="background_removed", path=path)
    base.update(over)
    return Rendition(**base)


def test_prefers_frame_true_background_removed(tmp_path):
    package, db = _library(tmp_path)
    pixels = tmp_path / "test.fichero" / "storage" / "bg.png"
    pixels.parent.mkdir(parents=True)
    pixels.write_bytes(b"png")
    db.save(_rendition("doc-1", "storage/bg.png"))

    assert _frame_true_background_removed_path(package, "doc-1") == str(pixels)


def test_transformed_rendition_is_refused(tmp_path):
    package, db = _library(tmp_path)
    pixels = tmp_path / "test.fichero" / "storage" / "bg.png"
    pixels.parent.mkdir(parents=True)
    pixels.write_bytes(b"png")
    db.save(_rendition(
        "doc-1", "storage/bg.png",
        transform=NodeRegion(rect=[0.1, 0.1, 0.5, 0.5]),
    ))

    assert _frame_true_background_removed_path(package, "doc-1") is None


def test_missing_bytes_and_wrong_role_fall_back(tmp_path):
    package, db = _library(tmp_path)
    db.save(_rendition("doc-1", "storage/nope.png"))  # referenced, not written
    pixels = tmp_path / "test.fichero" / "storage" / "enh.png"
    pixels.parent.mkdir(parents=True)
    pixels.write_bytes(b"png")
    db.save(_rendition("doc-1", "storage/enh.png", role="enhanced"))

    assert _frame_true_background_removed_path(package, "doc-1") is None
    assert _frame_true_background_removed_path(package, None) is None
    assert _frame_true_background_removed_path("", "doc-1") is None
