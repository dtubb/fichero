# ruff: noqa: F811  (the imported `page` fixture is the test parameter)
"""Review 8 migration cases: what an existing library pays after Prepare (`wide.prepare.operations-run-on-every-page`).

WHY: a read page's reading counts only for the image it was read from (`unread_by`, the skip-if-done lookup). Prepare writing a
new image over a page already read made the next read pay again. Stubbed model, counted sends; no paid call, no real database.
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from fichero_server.media import find_page as fp
from fichero_server.media import turn_by_text as tt
from fichero_server.media.current_image import current_page_image
from fichero_server.models import Document, Rendition
from fichero_server.recipes import page_crop
from fichero_server.recipes.prepare_run import run_prepare
from tests.unit.media.test_find_page import scan
from tests.unit.workflows.test_every_step_sends_the_edited_image_6296 import _poly, _tool, _whole_page_saved
from tests.unit.workflows.test_every_step_sends_the_edited_image_6296 import page  # noqa: F401,F811  (fixture)


@pytest.fixture(autouse=True)
def stubs(monkeypatch):
    monkeypatch.setattr(fp, "find_page_vision", lambda image: None)
    monkeypatch.setattr(tt, "read_lines", lambda image, db_path=None: [])
    monkeypatch.setattr(page_crop, "_has_text", lambda *a: True)


def ruled(angle):
    img = Image.new("RGB", (900, 700), (235, 230, 215))
    draw = ImageDraw.Draw(img)
    for y in range(80, 640, 40):
        draw.line([(40, y), (860, y)], fill=(40, 40, 70), width=3)
    return img.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=(235, 230, 215))


def _signature(p):
    return current_page_image(p["db"], p["db"].get(Document, p["doc"].id)).signature


def _set_meta(p, **kw):
    doc = p["db"].get(Document, p["doc"].id)
    doc.metadata = {**(doc.metadata or {}), **kw}
    p["db"].save(doc)


def _v2_stamp(p):
    info = Path(p["path"]).stat()
    return {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "version": 2}


def _as_v2_build(p):
    """What the integration build left: uuid-prefixed rendition files and a version 2 stamp."""
    for r in p["db"].query(Rendition, document_id=p["doc"].id):
        old = Path(r.path)
        new = old.with_name(f"{uuid.uuid4().hex[:8]}_{p['doc'].id}_{r.role}.png")
        old.rename(new)
        r.path = str(new)
        p["db"].save(r)
    _set_meta(p, page_prep_stamp=_v2_stamp(p))


def _prepare(p, run):
    step: dict = {}
    run_prepare(p["db"], [p["doc"].id], run, step, paper=[], operations=None)
    return step["page_prep"]


def _read(p, monkeypatch):
    """One whole-page read through the real skip-if-done lookup: the sends the stub model received."""
    return asyncio.new_event_loop().run_until_complete(_whole_page_saved(p, monkeypatch))


def test_a_cut_page_from_the_old_build_is_not_prepared_again_and_not_read_again(page, monkeypatch):
    scan().save(page["path"])
    assert page_crop.crop_pages(page["db"], [page["doc"].id], "old", prepare=True)["cropped"] == 1
    _as_v2_build(page)
    before = _signature(page)
    assert len(_read(page, monkeypatch)) == 1
    assert _prepare(page, "new")["unchanged"] == 1 and _signature(page) == before
    assert _read(page, monkeypatch) == []


@pytest.mark.parametrize("stamp", ["none", "v1"])
def test_a_cut_page_with_no_current_stamp_is_read_again_at_most_once(page, monkeypatch, stamp):
    """Integration prepares these again too (a new uuid each time); here the byte-named file ends it after one."""
    scan().save(page["path"])
    page_crop.crop_pages(page["db"], [page["doc"].id], "old", prepare=True)
    _as_v2_build(page)
    _set_meta(page, page_prep_stamp=None if stamp == "none" else {**_v2_stamp(page), "version": 1})
    _read(page, monkeypatch)
    assert _prepare(page, "new")["unchanged"] == 0
    after = _signature(page)
    assert len(_read(page, monkeypatch)) == 1
    assert _prepare(page, "newer")["unchanged"] == 1 and _signature(page) == after
    assert _read(page, monkeypatch) == []


@pytest.mark.parametrize("angle", [3.0, 0.0])
def test_a_whole_page_already_read_keeps_its_image_and_is_not_sent_again(page, monkeypatch, angle):
    ruled(angle).save(page["path"])
    monkeypatch.setattr(fp, "find_page", lambda image: None)
    _set_meta(page, page_prep_stamp=_v2_stamp(page))
    assert len(_read(page, monkeypatch)) == 1
    assert _signature(page) == "original"
    _prepare(page, "new")
    assert _signature(page) == "original" and _read(page, monkeypatch) == []


@pytest.mark.asyncio
async def test_a_half_read_whole_page_asks_only_for_the_line_it_has_not_read(page, monkeypatch):
    import fichero_server.llm.kraken_runtime as kr
    from fichero_server.llm.working_lines import working_lines
    from fichero_server.workflows.tools.transcribe import transcribe

    ruled(3.0).save(page["path"])
    monkeypatch.setattr(fp, "find_page", lambda image: None)
    monkeypatch.setattr(kr, "segment_lines", lambda image_path, **_: {"width": 900, "height": 700, "regions": [], "lines": [
        {"baseline": [[120, 155], [280, 155]], "polygon": _poly((120, 140, 280, 160)), "region": None},
        {"baseline": [[120, 205], [280, 205]], "polygon": _poly((120, 190, 280, 210)), "region": None}]})
    await _tool(page, transcribe, vision_mode="kraken")
    monkeypatch.setattr(kr, "resolve_recognition_model", lambda ref: ("/models/m.mlmodel", ref))
    asked: list[int] = []

    def read(image_path, model_path, lines, **kw):
        asked.append(len(lines))
        return ["texto"] * len(lines)

    monkeypatch.setattr(kr, "read_given_lines", read)
    await _tool(page, transcribe, vision_mode="kraken", kraken_model="kraken-m")
    found = working_lines(page["db"], page["doc"].id)
    page["db"].execute("DELETE FROM contentrepresentations WHERE segment_id = ?", [found.lines[1].id])  # a Stop before line 2
    _set_meta(page, page_prep_stamp=_v2_stamp(page))
    _prepare(page, "new")
    await _tool(page, transcribe, vision_mode="kraken", kraken_model="kraken-m")
    assert asked == [2, 1], "one line left: only that one is sent"
