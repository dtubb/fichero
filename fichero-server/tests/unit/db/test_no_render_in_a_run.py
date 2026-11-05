"""NO RUN RENDERS THE WORKING IMAGE AGAIN (`image.enhance.working-rendition-once`, #6200, #6193)."""
from __future__ import annotations

import os

from fichero_server.models import DocType, Document, FileType
from tests.unit.media.test_find_page import scan


def test_a_prepare_images_run_and_a_read_over_made_pages_never_decode_the_original_again(db, tmp_path, monkeypatch):
    from fichero_server.db import storage
    from fichero_server.media import find_page as module
    from fichero_server.recipes.prepare_run import run_prepare

    monkeypatch.setattr(module, "find_page_vision", lambda _image: None)
    path = tmp_path / "scan.png"
    scan().save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path),
                   metadata={"checksum": "c1"})
    db.save(doc)
    assert storage.ensure_display(doc, db=db) is not None  # made once, at import

    calls = []
    real = storage._generate_image
    monkeypatch.setattr(storage, "_generate_image", lambda *a, **k: calls.append(a[0]) or real(*a, **k))
    step: dict = {}
    run_prepare(db, [doc.id], "run-1", step, operations=["crop", "straighten"])
    storage.ensure_display(doc, db=db)
    storage.ensure_thumbnail(doc, db=db)
    assert storage.made_display(doc, db=db) is not None
    # The thumbnail is keyed like the rendition: the original's modified time moving is no new thumbnail.
    first = storage.ensure_thumbnail(doc, db=db)
    calls.clear()
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 5_000_000_000))
    assert storage.ensure_thumbnail(doc, db=db) == first
    assert calls == [], calls
    assert [c for c in calls if c == path] == [], calls  # nothing decoded the original; the small thumbnail is cut from the made rendition
