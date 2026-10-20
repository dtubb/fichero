"""The Vision crop probe (#5894): the four crops, who counts as an empty and a real word, and the decision bar. Apple
Vision is replaced by a stub that reads only a picture at least 150 px high (as if upscaling rescued it)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "vision_crop_probe.py"
_SPEC = importlib.util.spec_from_file_location("vision_crop_probe", _SCRIPT)
assert _SPEC and _SPEC.loader
vp = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = vp
_SPEC.loader.exec_module(vp)  # type: ignore[attr-defined]


def _page(tmp_path) -> Path:
    folder = tmp_path / "pages"
    folder.mkdir()
    im = Image.new("RGB", (800, 300), (200, 190, 170))  # paper
    ImageDraw.Draw(im).rectangle((10, 10, 500, 70), fill=(20, 20, 20))
    im.save(folder / "p.png")
    return folder


def _poly(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def test_the_four_crops_are_todays_cut_white_filled_and_doubled():
    page = Image.new("RGB", (800, 300), (200, 190, 170))
    got = vp.variants(page, _poly(100, 100, 400, 160))
    assert set(got) == set(vp.VARIANTS)
    assert got["up2"].size == (got["today"].width * 2, got["today"].height * 2) and got["white"].size == got["today"].size
    assert got["white"].getpixel((0, 0)) == (255, 255, 255), "outside the polygon is white"
    assert got["today"].getpixel((0, 0)) == (200, 190, 170), "today's fill is the crop's median colour"
    from fichero_server.llm.line_cut import crop_line

    assert got["today"].size == crop_line(page, _poly(100, 100, 400, 160)).size, "the same cut the line reader makes"


def test_only_the_empty_lines_are_probed_and_the_real_word_ones_are_told_from_fragments(tmp_path):
    rows = [
        {"page": "p.png", "id": "0", "polygon": _poly(100, 100, 500, 140), "kraken": "Carlos", "vision": ""},  # real word
        {"page": "p.png", "id": "1", "polygon": _poly(100, 160, 160, 200), "kraken": "e", "vision": ""},  # fragment
        {"page": "p.png", "id": "2", "polygon": _poly(100, 210, 500, 250), "kraken": "", "vision": ""},  # wide, Kraken blank
        {"page": "p.png", "id": "3", "polygon": _poly(100, 20, 500, 60), "kraken": "hola", "vision": "hola"},  # read: skipped
    ]
    result = vp.probe(rows, _page(tmp_path), ocr=lambda img: "x" if img.height >= 150 else "")
    assert [r["id"] for r in result["lines"]] == ["0", "1", "2"]
    assert [r["real_word"] for r in result["lines"]] == [True, False, False]
    assert result["empties"] == 3 and result["real_word_empties"] == 1
    assert result["rescued"]["today"] == 0, "today was empty before: the probe's own check"


def test_a_variant_that_rescues_a_quarter_of_the_real_words_is_named_in_the_verdict(tmp_path):
    rows = [{"page": "p.png", "id": str(i), "polygon": _poly(100, 100, 500, 140), "kraken": "Carlos", "vision": ""}
            for i in range(4)]
    seen = {"n": 0}

    def ocr(img):  # only the upscaled white picture of the first line reads
        seen["n"] += 1
        return "ok" if img.height >= 150 and img.getpixel((0, 0)) == (255, 255, 255) and seen["n"] <= 4 else ""

    result = vp.probe(rows, _page(tmp_path), ocr=ocr)
    assert result["rescued_real_word"]["up2_white"] == 1 and result["decision"]["up2_white"] is True
    assert result["decision"]["white"] is False
    assert "up2_white" in vp.report_md(result) and "specify a crop change for Apple Vision only" in vp.report_md(result)


def test_when_nothing_rescues_enough_the_verdict_says_leave_crop_line_alone(tmp_path):
    rows = [{"page": "p.png", "id": "0", "polygon": _poly(100, 100, 500, 140), "kraken": "Carlos", "vision": ""}]
    result = vp.probe(rows, _page(tmp_path), ocr=lambda img: "")
    assert not any(result["decision"].values())
    assert "leave `crop_line` as it is" in vp.report_md(result)
    assert "not ground truth" in vp.report_md(result)
