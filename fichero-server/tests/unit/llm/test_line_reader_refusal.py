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


def _read(monkeypatch, tmp_path, ids, answers, **kw):
    calls = iter(answers)

    async def fake_vision(**kw):
        return next(calls)

    monkeypatch.setattr(llm, "vision", fake_vision)
    path, geometry = _geometry(tmp_path, ids)
    config = LLMConfig(provider=kw.pop("provider", "openrouter"), model="x")
    return asyncio.run(line_reader.read_lines(path, geometry, config, **kw))


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


def _calls(monkeypatch, tmp_path, ids, **kw):
    seen = []

    async def fake_vision(**kw2):
        seen.append(kw2)
        n = len(ids)
        return str([f"t{i}" for i in range(n)]).replace("'", '"')

    monkeypatch.setattr(llm, "vision", fake_vision)
    path, geometry = _geometry(tmp_path, ids)
    provider = kw.pop("provider", "openrouter")
    asyncio.run(line_reader.read_lines(path, geometry, LLMConfig(provider=provider, model="x"), **kw))
    return seen


def test_the_page_rides_once_per_request_reduced_beside_the_batch_of_lines(monkeypatch, tmp_path):
    """Variant B (owner's brief: line image + page context + language), cheaply: not once a line."""
    import base64
    import io

    [call] = _calls(monkeypatch, tmp_path, ["a", "b", "c"])
    assert len(call["images"]) == 4, "the page, then the three lines"
    with Image.open(io.BytesIO(base64.b64decode(call["images"][0].split(",", 1)[1]))) as page:
        assert max(page.size) <= line_reader.PAGE_CONTEXT_SIDE
    assert call["prompt"].startswith("Before the 3 line images comes one more, first: the whole page")


def test_no_page_beside_a_reader_trained_on_one_picture_or_when_asked_not_to(monkeypatch, tmp_path):
    [local] = _calls(monkeypatch, tmp_path, ["a", "b"], provider="omlx")
    assert len(local["images"]) == 2 and not local["prompt"].startswith("Before")
    [off] = _calls(monkeypatch, tmp_path, ["a", "b"], page_context=False)
    assert len(off["images"]) == 2


def test_the_line_says_why_it_is_unread_after_the_page_is_written(db):
    """The refusal reason is on the line itself (`unread_reason`), versioned and audited, not only in the result."""
    from fichero_server.llm.working_lines import mark_unread_reasons
    from fichero_server.models.segments import Segment
    from fichero_server.recipes.done import unread_reasons
    from tests.unit.recipes.test_unread_lines_not_read_5758 import _page

    page = _page(db, 2, 0)
    first = next(s for s in db.query(Segment, document_id=page) if s.kind == "line")
    before = first.version
    reason = "the model answered with text that is not a reading (\"I'm sorry\")"
    mark_unread_reasons(db, {first.id: reason})
    assert db.get(Segment, first.id).version == before + 1
    assert unread_reasons(db, page)[first.id] == reason
    mark_unread_reasons(db, {first.id: reason})
    assert db.get(Segment, first.id).version == before + 1, "the same reason twice is one change"
