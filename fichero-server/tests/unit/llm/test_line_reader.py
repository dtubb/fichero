"""A vision model reads the lines Kraken found (distilling a large reader into a Kraken one).

WHY: Kraken trains on line images paired with their text. The teacher (Gemini) reads each line
Kraken found, so the pair keeps Kraken's own geometry. If a batch's answer were placed by position
when its length is wrong, every following line would carry its neighbour's text and the trained
reader would learn misreadings; a line with no writing (the ruler, graph paper) must not become a
training line with invented text.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from PIL import Image

from fichero_server.llm import line_reader
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult


def test_the_answer_must_be_exactly_n_readings():
    assert line_reader.parse_answer('```json\n["a", null, " b "]\n```', 3) == ["a", None, "b"]
    assert line_reader.parse_answer('["a", "b"]', 3) is None
    assert line_reader.parse_answer("not json", 1) is None
    assert line_reader.parse_answer('[1, "b"]', 2) is None


def _lines(n):
    boxes = [OCRGeometryBox(text="", bbox=[0, i / n, 1, 1 / n], level=OCRGeometryLevel.LINE,
                            metadata={"polygon_px": [[10, 10 + 20 * i], [190, 10 + 20 * i], [190, 25 + 20 * i], [10, 25 + 20 * i]]})
             for i in range(n)]
    return OCRGeometryResult(text="", provider="kraken", model="blla", boxes=boxes)


def test_lines_keep_kraken_geometry_carry_the_models_text_and_blank_lines_drop(tmp_path, monkeypatch):
    image = tmp_path / "page.png"
    Image.new("RGB", (200, 220), "white").save(image)
    calls = []

    async def fake_vision(images, prompt, config, **_):
        calls.append(len(images))
        if len(images) > 1:
            return "[]"  # a malformed batch answer: must be re-asked one by one, not placed
        return '["linea"]' if len(calls) % 2 else "[null]"

    monkeypatch.setattr("fichero_server.llm.vision", fake_vision)
    config = SimpleNamespace(provider="openrouter", model="google/gemini-3-flash-preview")
    result = asyncio.run(line_reader.read_lines(str(image), _lines(3), config))

    assert calls[0] == 3 and calls[1:] == [1, 1, 1]
    assert result.provider == "openrouter" and result.metadata["lines_found"] == 3
    assert len(result.boxes) + result.metadata["lines_without_writing"] == 3
    assert all(b.text == "linea" and b.metadata["polygon_px"] for b in result.boxes)
    assert result.text == "\n".join(b.text for b in result.boxes)
    assert [result.text[b.char_start:b.char_end] for b in result.boxes] == [b.text for b in result.boxes]
