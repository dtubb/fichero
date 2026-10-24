"""`source.recipe.cloud-reads-lines-per-page`: a batch answered with the page beside it is believed only if its answers are alike,
in order, to the same lines asked alone (or Kraken's own reading of them); a batch out of order is re-asked line by line, so a
reading never lands on a line it was not cut from."""
from __future__ import annotations

import asyncio

from PIL import Image, ImageDraw

from fichero_server import llm
from fichero_server.llm import LLMConfig, line_reader
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

TEXTS = ["Pedro Alvarado vive en el", "pueblo de Rio Claro desde", "hace muchos anos y cuida", "la huerta del convento"]


def _page(tmp_path):
    path = tmp_path / "p.png"
    image = Image.new("RGB", (400, 200), "white")
    draw = ImageDraw.Draw(image)
    boxes = []
    for i in range(len(TEXTS)):
        y = 10 + 45 * i
        draw.rectangle([10, y, 390, y + 30], fill=(40 * i + 10, 20, 200 - 40 * i))  # a picture of its own for every line
        poly = [[10, y], [390, y], [390, y + 30], [10, y + 30]]
        boxes.append(OCRGeometryBox(text="", bbox=[0.05, y / 200, 0.9, 0.15], level=OCRGeometryLevel.LINE, provider="kraken", model="m",
                                    source="working-pass",
                                    metadata={"segment_id": f"s{i}", "polygon_px": poly, "baseline_px": [[10, y + 25], [390, y + 25]],
                                              "pixel_frame": {"width": 400, "height": 200}}))
    image.save(path)
    return str(path), OCRGeometryResult(text="", provider="kraken", model="m", boxes=boxes, source="working-pass", metadata={})


def _run(monkeypatch, tmp_path, scramble):
    path, geometry = _page(tmp_path)
    page = Image.open(path)
    by_picture = {line_reader._crop_data_uri(page, b.metadata["polygon_px"]): TEXTS[i] for i, b in enumerate(geometry.boxes)}
    calls = []

    async def model(images, prompt, config, **_):
        calls.append(len(images))
        shown = [by_picture[i] for i in images if i in by_picture]  # the page picture rides first, unread
        if len(shown) > 1 and scramble:
            shown = shown[2:] + shown[:2]  # a batch answered out of page order
        return "[" + ", ".join(f'"{t}"' for t in shown) + "]"

    monkeypatch.setattr(llm, "vision", model)
    out = asyncio.run(line_reader.read_lines(path, geometry, LLMConfig(provider="openrouter", model="x"), granularity="page"))
    return {b.metadata["segment_id"]: b.text for b in out.boxes}, calls


def test_a_batch_answered_in_page_order_is_taken_whole(monkeypatch, tmp_path):
    read, calls = _run(monkeypatch, tmp_path, scramble=False)
    assert [read[f"s{i}"] for i in range(4)] == TEXTS
    assert len(calls) == 3, "the batch, then its first and last line asked alone as the check"


def test_a_batch_out_of_order_is_asked_line_by_line_and_every_reading_lands_on_its_own_line(monkeypatch, tmp_path):
    read, _calls = _run(monkeypatch, tmp_path, scramble=True)
    assert [read[f"s{i}"] for i in range(4)] == TEXTS


def test_answers_with_nothing_to_compare_are_believed():
    assert line_reader.answers_follow_order(["a", None], [None, "b"])
    assert not line_reader.answers_follow_order(["la huerta del convento"], ["Pedro Alvarado vive en el"])
