"""The split_pages tool end to end on synthetic photographs (`prep.split-at-the-gutter`, #5382).

A synthetic notebook: a dark table, a bright open notebook whose spiral (a dark band) is NOT at the
image's middle, as on every real Sergio spread. The real-photo thresholds are pinned in
tests/unit/media/test_page_split.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")
pytest.importorskip("numpy")

from PIL import Image, ImageDraw

from fichero_server.llm import LLMConfig
from fichero_server.media.page_split import Outline
from fichero_server.models import Document, Rendition
from fichero_server.workflows.registry import get_tool_def
from fichero_server.workflows.tools.split_pages import split_pages, split_pages_file

SPREAD_OUTLINE = Outline((60, 50, 540, 350), 0.99, "apple-vision")  # 480 x 300: aspect 1.6
SPIRAL = (330, 344)  # the photo's middle is x = 300


def _spread(path: Path) -> Path:
    image = Image.new("RGB", (600, 400), (40, 40, 40))
    draw = ImageDraw.Draw(image)
    draw.rectangle(SPREAD_OUTLINE.box, fill=(225, 225, 220))
    draw.rectangle((SPIRAL[0], 50, SPIRAL[1], 350), fill=(70, 70, 70))
    for y in range(80, 330, 18):  # lines of writing on both pages
        draw.line((90, y, 300, y), fill=(120, 120, 140), width=2)
        draw.line((370, y, 510, y), fill=(120, 120, 140), width=2)
    image.save(path, quality=95)
    return path


def _cover(path: Path) -> Path:
    image = Image.new("RGB", (600, 400), (40, 40, 40))
    ImageDraw.Draw(image).rectangle((200, 40, 420, 360), fill=(30, 60, 110))
    image.save(path, quality=95)
    return path


COVER_OUTLINE = Outline((200, 40, 420, 360), 0.99, "apple-vision")  # 220 x 320: aspect 0.69


def test_a_spread_is_cut_at_its_spiral_not_the_middle(tmp_path):
    """WHY: today's split_images would cut at x = 300 here, 30 px into the right page's writing."""
    source = _spread(tmp_path / "spread.jpg")
    before = source.read_bytes()
    result = split_pages_file(source, tmp_path / "out", outline=SPREAD_OUTLINE)
    assert result["error"] is None
    assert source.read_bytes() == before, "the source photograph is never changed"
    assert result["details"]["decision"] == "split"
    gutter = result["details"]["gutter_x"]
    assert SPIRAL[0] - 4 <= gutter <= SPIRAL[1] + 4
    left, right = (p["bbox"] for p in result["parts"])
    assert left == [60, 50, gutter - 60, 300] and right == [gutter, 50, 540 - gutter, 300]
    assert all(p["source_size"] == [600, 400] for p in result["parts"]), "regions need the frame they were cut from"
    with Image.open(result["outputs"][0]) as first:
        assert first.size == (gutter - 60, 300)
    assert result["outputs"][0].endswith(".jpg"), "a JPEG photo's pages stay JPEG (#5386)"


def test_a_cover_is_kept_whole(tmp_path):
    """WHY: a closed notebook is one page; cutting it gives two half-covers and a broken page order."""
    result = split_pages_file(_cover(tmp_path / "cover.jpg"), tmp_path / "out", outline=COVER_OUTLINE)
    assert result["details"]["decision"] == "single_page"
    assert [p["bbox"] for p in result["parts"]] == [[200, 40, 220, 320]]


def test_without_vision_the_whole_frame_is_used_and_said(tmp_path):
    """WHY: off a Mac (or with Vision off) the job must still run, and say its outline is the frame."""
    result = split_pages_file(_spread(tmp_path / "spread.jpg"), tmp_path / "out", use_apple_vision=False)
    assert result["details"]["outline_method"] == "frame"


def test_tool_is_registered():
    tool_def = get_tool_def("split_pages")
    assert tool_def is not None and tool_def.uses_llm is False


@pytest.mark.asyncio
async def test_only_a_real_cut_becomes_child_pages(db, tmp_path, test_package, monkeypatch):
    """WHY: the pages of a cut spread are new items in the library, in reading order, with the region
    they were cut from; a cover is not a new page of itself, so it gets no child. Children carry the
    same `region_in_parent` the in-app split writes, so one unsplit serves both."""
    from fichero_server.workflows.tools import split_pages as tool

    spread, cover = _spread(tmp_path / "spread.jpg"), _cover(tmp_path / "cover.jpg")
    docs = []
    for source in (spread, cover):
        doc = Document(name=source.name, path=str(source), metadata={"source_path": str(source)})
        db.save(doc)
        docs.append(doc)
    outlines = {str(spread): SPREAD_OUTLINE, str(cover): COVER_OUTLINE}
    monkeypatch.setattr(tool.page_split, "detect_document_outline", lambda path: outlines[str(path)])

    result = await split_pages(
        {"files": [str(spread), str(cover)], "documents": [{"id": d.id} for d in docs],
         "library_path": str(test_package), "output_dir": str(tmp_path / "out")},
        {}, LLMConfig(provider="none", model="none"),
    )

    assert result["error"] is None and result["needs_review"] == []
    assert [d["decision"] for d in result["decisions"]] == ["split", "single_page"]
    children = sorted(db.query(Document, parent_id=docs[0].id), key=lambda c: c.sequence)
    assert [c.sequence for c in children] == [1, 2]
    assert children[0].region_in_parent.rect[0] == pytest.approx(60 / 600)
    assert children[1].region_in_parent.rect[0] == pytest.approx(result["decisions"][0]["gutter_x"] / 600)
    assert all(db.query(Rendition, document_id=c.id) for c in children)
    assert db.query(Document, parent_id=docs[1].id) == []
