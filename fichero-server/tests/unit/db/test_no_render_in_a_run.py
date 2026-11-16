"""NO RUN RENDERS THE WORKING IMAGE AGAIN (`image.enhance.working-rendition-once`, #6200, #6193)."""
from __future__ import annotations

import os

import pytest

from fichero_server.models import DocType, Document, FileType
from tests.unit.media.test_find_page import scan


@pytest.fixture
def made(db, tmp_path, monkeypatch):
    """A page whose working rendition is made, then a counter around `_generate_image` listing each source it decodes."""
    from fichero_server.db import storage
    from fichero_server.media import find_page as module

    monkeypatch.setattr(module, "find_page_vision", lambda _image: None)
    path = tmp_path / "scan.png"
    scan().save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path),
                   metadata={"checksum": "c1"})
    db.save(doc)
    assert storage.ensure_display(doc, db=db) is not None
    decoded: list = []
    real = storage._generate_image
    monkeypatch.setattr(storage, "_generate_image", lambda *a, **k: decoded.append(a[0]) or real(*a, **k))
    return doc, path, decoded


def test_a_prepare_images_run_decodes_the_original_zero_times_when_the_rendition_is_made(db, made):
    from fichero_server.db import storage
    from fichero_server.recipes.prepare_run import run_prepare

    doc, path, decoded = made
    run_prepare(db, [doc.id], "run-1", {}, operations=["crop", "straighten"])
    storage.ensure_display(doc, db=db)
    storage.ensure_thumbnail(doc, db=db)
    assert path not in decoded, decoded
    assert storage.made_display(doc, db=db) is not None


def test_the_thumbnail_is_not_made_again_when_the_originals_modified_time_moves(db, made):
    from fichero_server.db import storage

    doc, path, decoded = made
    first = storage.ensure_thumbnail(doc, db=db)
    decoded.clear()
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 5_000_000_000))
    assert storage.ensure_thumbnail(doc, db=db) == first
    assert decoded == []


def test_a_document_with_no_checksum_keeps_the_modified_time_identity(db, made):
    from fichero_server.db import storage

    doc, path, decoded = made
    doc.metadata = {}
    db.save(doc)
    first = storage.ensure_thumbnail(doc, db=db)
    assert path in decoded  # nothing identifies the content, so the original is what the thumbnail comes from
    decoded.clear()
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 5_000_000_000))
    assert storage.ensure_thumbnail(doc, db=db) != first
    assert path in decoded


def test_a_stale_key_makes_the_thumbnail_again(db, made):
    from fichero_server.db import storage

    doc, path, decoded = made
    first = storage.ensure_thumbnail(doc, db=db)
    doc.metadata = {"checksum": "c2"}  # the content changed: the rendition's key no longer matches
    db.save(doc)
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 60_000_000_000))  # newer than the thumbnail
    decoded.clear()
    second = storage.ensure_thumbnail(doc, db=db)
    assert second != first
    assert path in decoded


def test_a_thumbnail_made_for_earlier_content_is_not_adopted_when_the_rendition_is_made_again(db, made):
    from fichero_server.db import storage

    doc, path, decoded = made
    first = storage.ensure_thumbnail(doc, db=db)
    doc.metadata = {"checksum": "c2"}  # the content changed and its rendition is made again under the new key
    db.save(doc)
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 60_000_000_000))
    storage.ensure_display(doc, db=db)
    decoded.clear()
    second = storage.ensure_thumbnail(doc, db=db)
    assert second != first
    assert decoded, "the old thumbnail was served instead of being cut from the new rendition"
