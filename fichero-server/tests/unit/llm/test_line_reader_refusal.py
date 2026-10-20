"""`source.recipe.kraken-lines-cloud-reads` (variant B): a line the model refuses, or answers with text that is not a
reading, keeps NO text, stays unread, and the page's result says why, with what the model said (#5894)."""
from __future__ import annotations

import asyncio

from PIL import Image

from fichero_server import llm
from fichero_server.llm import LLMConfig, line_reader
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult


def _geometry(tmp_path, ids):
    path = tmp_path / "p.png"
    Image.new("RGB", (400, 100), "white").save(path)

    def line(sid, y):
        poly = [[10, y], [390, y], [390, y + 20], [10, y + 20]]
        return OCRGeometryBox(text="", bbox=[0.0, y / 100, 1.0, 0.2], level=OCRGeometryLevel.LINE, provider="kraken",
                              model="m", source="working-pass",
                              metadata={"segment_id": sid, "polygon_px": poly, "baseline_px": [[10, y + 15], [390, y + 15]],
                                        "pixel_frame": {"width": 400, "height": 100}})

    return str(path), OCRGeometryResult(text="", provider="kraken", model="m", boxes=[line(s, 10 + 30 * i) for i, s in
                                                                                     enumerate(ids)],
                                        source="working-pass", metadata={})


def _read(monkeypatch, tmp_path, ids, answers):
    calls = iter(answers)

    async def fake_vision(**kw):
        return next(calls)

    monkeypatch.setattr(llm, "vision", fake_vision)
    path, geometry = _geometry(tmp_path, ids)
    return asyncio.run(line_reader.read_lines(path, geometry, LLMConfig(provider="openrouter", model="x")))


def test_a_refused_line_keeps_no_text_and_the_result_says_what_the_model_said(monkeypatch, tmp_path):
    out = _read(monkeypatch, tmp_path, ["a", "b"],
                ["Sorry", "I'm sorry, I can't read handwriting.", '["hola"]'])  # the pair fails, then each line alone
    assert [b.metadata["segment_id"] for b in out.boxes if b.text] == ["b"], "the refused line has no text"
    why = out.metadata["lines_unanswered"]
    assert set(why) == {"a"} and "not a reading" in why["a"] and "can't read handwriting" in why["a"], why


def test_an_empty_answer_is_said_too_and_a_line_with_no_writing_is_not_an_unanswered_one(monkeypatch, tmp_path):
    out = _read(monkeypatch, tmp_path, ["a", "b", "c"], ["", "", '[null]', '["hola"]'])
    why = out.metadata["lines_unanswered"]
    assert why.get("a") == "the model gave no answer"
    assert "b" not in why, "the model answered null for b: it looked and found no writing, which is not a refusal"
