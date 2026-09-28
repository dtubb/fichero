"""A thumbnail is never served half-written (#5187, the empty thumbnail over UDS).

WHY: a derivative was written with `image.save(dest)`, which creates the file and THEN writes the
encoded bytes. The thumbnail route checks "does the file exist" and serves it: under load, a
request landing while the derivative stage was still writing got a 200 with an EMPTY body (the
transport matrix's "[uds] thumbnail body is empty", passing on rerun). If this regresses, a client
caches a blank thumbnail, and the gate flakes whenever the machine is busy.

The window is made deterministic: a stand-in for PIL's `save` creates the target file and then
blocks before writing a byte -- exactly the state a slow encode leaves -- while a reader asks.
"""

from __future__ import annotations

import threading

from PIL import Image

from fichero_server.db import storage
from fichero_server.models import Document, FileType


def _image_document(db) -> Document:
    source = db.path.parent / "files" / "page.png"
    source.parent.mkdir(exist_ok=True)
    Image.new("RGB", (400, 300), "navy").save(source)
    doc = Document(name="page.png", path=str(source), file_type=FileType.image)
    db.save(doc)
    return doc


def test_a_reader_during_the_write_sees_no_thumbnail_and_then_a_whole_one(db, monkeypatch):
    doc = _image_document(db)
    package = db.path.parent
    real_save = Image.Image.save
    created, release = threading.Event(), threading.Event()

    def slow_save(self, fp, format=None, **params):
        with open(fp, "wb"):
            pass                                    # the file exists, empty: the encode has begun
        created.set()
        release.wait(10)
        return real_save(self, fp, format, **params)

    monkeypatch.setattr(Image.Image, "save", slow_save)
    writer = threading.Thread(target=storage.ensure_thumbnail, args=(doc,), kwargs={"package_path": package, "db": db})
    writer.start()
    try:
        assert created.wait(10), "the thumbnail write never started"
        during = storage.get_thumbnail(doc, package_path=package, db=db)
        seen = (during, during.stat().st_size if during else None)
    finally:
        release.set()
        writer.join(10)
    assert seen == (None, None), f"a half-written thumbnail was visible: {seen}"   # old: (path, 0)
    after = storage.get_thumbnail(doc, package_path=package, db=db)
    assert after is not None and after.stat().st_size > 0
    with Image.open(after) as done:
        assert done.format == "JPEG" and max(done.size) <= max(storage.settings.thumb_size)
    assert not [p for p in after.parent.iterdir() if ".writing-" in p.name]      # no staging left behind


def test_a_failed_write_leaves_nothing_behind(monkeypatch, tmp_path):
    def broken_save(self, fp, format=None, **params):
        with open(fp, "wb") as out:
            out.write(b"half")
        raise OSError("disk full")

    monkeypatch.setattr(Image.Image, "save", broken_save)
    folder = tmp_path / "thumbnails"
    dest = folder / "thumb.jpg"
    try:
        storage.save_image_atomically(Image.new("RGB", (4, 4)), dest, "JPEG")
    except OSError:
        pass
    assert list(folder.iterdir()) == []                                           # neither half a file nor staging
