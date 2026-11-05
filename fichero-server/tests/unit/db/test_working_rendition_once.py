"""The working rendition (the display image) is made once, keyed by content hash and size, and read without the source
(`image.enhance.working-rendition-once`, `image.enhance.reads-without-the-source`, #6200).

WHY: a view or a run called `ensure_display` and, when the file's modified time had moved (a copy, a remount, a sync), the
whole picture was decoded and resized again; with the source unmounted the call answered nothing even though the picture
was on disk. The picture is now identified by what it is (the file's checksum at import) and the side it was cut to.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from PIL import Image

from fichero_server.db import storage
from fichero_server.models import Document, FileType


def _doc(db, name="big.png", colour=(200, 180, 150), size=(3000, 2000)) -> tuple[Document, Path]:
    path = db.path.parent / "files" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(path)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    doc = Document(name=name, path=str(path), file_type=FileType.image, metadata={"checksum": checksum})
    db.save(doc)
    return doc, path


@pytest.fixture
def renders(monkeypatch):
    calls: list[Path] = []
    real = storage._generate_image

    def counting(source, dest, size):
        calls.append(source)
        return real(source, dest, size)

    monkeypatch.setattr(storage, "_generate_image", counting)
    return calls


def test_a_second_call_with_the_same_content_and_side_does_no_render_even_when_the_file_was_touched(db, renders):
    doc, path = _doc(db)
    first = storage.ensure_display(doc, package_path=db.path.parent, db=db)
    assert first is not None and first.is_file() and len(renders) == 1
    newer = path.stat().st_mtime + 3600
    os.utime(path, (newer, newer))  # a copy or a remount: same bytes, a later modified time
    again = storage.ensure_display(doc, package_path=db.path.parent, db=db)
    assert again == first and len(renders) == 1


def test_a_different_side_is_a_different_key_and_renders_again(db, renders, monkeypatch):
    doc, _ = _doc(db)
    storage.ensure_display(doc, package_path=db.path.parent, db=db)
    monkeypatch.setattr(storage.settings, "display_width", 800)
    monkeypatch.setattr(storage.settings, "display_height", 800)
    out = storage.ensure_display(doc, package_path=db.path.parent, db=db)
    assert len(renders) == 2
    with Image.open(out) as made:
        assert max(made.size) <= 800


def test_different_content_is_a_different_key_and_renders_again(db, renders):
    doc, path = _doc(db)
    storage.ensure_display(doc, package_path=db.path.parent, db=db)
    Image.new("RGB", (3000, 2000), (10, 10, 10)).save(path)
    doc.metadata = {**doc.metadata, "checksum": hashlib.sha256(path.read_bytes()).hexdigest()}
    out = storage.ensure_display(doc, package_path=db.path.parent, db=db)
    assert len(renders) == 2
    with Image.open(out) as made:
        assert made.getpixel((5, 5)) == (10, 10, 10)


def test_with_the_source_unmounted_the_made_picture_is_still_served(db, renders):
    doc, path = _doc(db)
    first = storage.ensure_display(doc, package_path=db.path.parent, db=db)
    path.rename(path.with_suffix(".away"))  # the drive is gone
    assert storage.ensure_display(doc, package_path=db.path.parent, db=db) == first
    assert len(renders) == 1


def test_a_page_never_made_and_unmounted_answers_nothing_and_does_not_invent_a_picture(db, renders):
    doc, path = _doc(db)
    path.rename(path.with_suffix(".away"))
    assert storage.ensure_display(doc, package_path=db.path.parent, db=db) is None and renders == []


def test_force_renders_again(db, renders):
    doc, _ = _doc(db)
    storage.ensure_display(doc, package_path=db.path.parent, db=db)
    storage.ensure_display(doc, force=True, package_path=db.path.parent, db=db)
    assert len(renders) == 2


def test_the_line_readers_page_context_is_cut_from_the_working_rendition_not_the_full_page(monkeypatch, tmp_path):
    import asyncio

    from fichero_server import llm
    from fichero_server.llm import LLMConfig, line_reader
    from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

    page = tmp_path / "page.png"
    Image.new("RGB", (400, 300), (255, 255, 255)).save(page)
    working = tmp_path / "working.png"
    Image.new("RGB", (40, 30), (10, 20, 30)).save(working)
    box = OCRGeometryBox(text="", bbox=[0.0, 0.0, 0.5, 0.1], level=OCRGeometryLevel.LINE, provider="kraken", model="m",
                         source="working-pass",
                         metadata={"segment_id": "s0", "polygon_px": [[0, 0], [100, 0], [100, 20], [0, 20]],
                                   "baseline_px": [[0, 15], [100, 15]], "pixel_frame": {"width": 400, "height": 300}})
    geometry = OCRGeometryResult(text="", provider="kraken", model="m", boxes=[box], source="working-pass", metadata={})
    seen: list[str] = []

    async def model(images, prompt, config, **_):
        seen.append(images[0])  # the page picture rides first
        return '["x"]'

    monkeypatch.setattr(llm, "vision", model)
    asyncio.run(line_reader.read_lines(str(page), geometry, LLMConfig(provider="openrouter", model="x"), granularity="page",
                                       page_context=True, working_image=str(working)))
    import base64
    import io

    sent = Image.open(io.BytesIO(base64.b64decode(seen[0].split(",", 1)[1])))
    assert sent.size == (40, 30)  # the working rendition's size, not the 400x300 page


def test_the_thumbnail_is_cut_from_the_working_rendition_not_the_original(db, renders):
    doc, path = _doc(db)
    display = storage.ensure_display(doc, package_path=db.path.parent, db=db)
    assert display is not None and renders == [path]

    thumb = storage.ensure_thumbnail(doc, package_path=db.path.parent, db=db)

    assert thumb is not None and thumb.is_file()
    assert renders == [path, display], "the thumbnail read the display image, not the 3000 px original"


def test_a_page_with_no_working_rendition_yet_still_gets_its_thumbnail_from_the_original(db, renders):
    doc, path = _doc(db)
    thumb = storage.ensure_thumbnail(doc, package_path=db.path.parent, db=db)
    assert thumb is not None and renders == [path]
