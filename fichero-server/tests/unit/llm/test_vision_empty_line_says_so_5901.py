"""`source.read.vision-empty-line-says-so` (#5901): a line Apple Vision came back empty on is UNREAD with the reason "Apple
Vision returned nothing for this line", never "looked, no writing" and never a read line. Vision does not read the same crop the
same way twice (the bake-off probe: 25 of 72 empties read on a plain re-run), so an empty answer is not evidence of a blank line."""
from __future__ import annotations

import asyncio

from PIL import Image

from fichero_server import llm
from fichero_server.llm import line_reader
from fichero_server.llm.working_lines import NO_WRITING_KEY
from tests.unit.llm.test_line_reader_refusal import _geometry


def _apple(monkeypatch, tmp_path, ids, answers):
    calls = iter(answers)

    async def fake_vision(**kw):
        assert kw.get("language") == "es-ES" and kw.get("recognition_only_ok") is True, "the Apple path"
        return next(calls)

    monkeypatch.setattr(llm, "vision", fake_vision)
    path, geometry = _geometry(tmp_path, ids)
    return asyncio.run(line_reader.read_lines(path, geometry, None, language="es-ES", apple=True))


def test_an_empty_vision_line_is_unread_and_says_vision_returned_nothing(monkeypatch, tmp_path):
    out = _apple(monkeypatch, tmp_path, ["a", "b", "c"], ["", "hola", "   "])
    assert [b.metadata["segment_id"] for b in out.boxes if b.text] == ["b"], "only the line Vision read has text"
    why = out.metadata["lines_unanswered"]
    assert set(why) == {"a", "c"} and all(w == line_reader.VISION_RETURNED_NOTHING for w in why.values()), why
    assert "Vision returned nothing" in line_reader.VISION_RETURNED_NOTHING
    assert out.metadata[NO_WRITING_KEY] == [], "an empty Vision answer is not 'looked, found no writing'"


def test_a_page_vision_returned_nothing_for_is_unread_with_the_reason_not_a_blank_page(monkeypatch, tmp_path):
    out = _apple(monkeypatch, tmp_path, ["a", "b"], ["", ""])
    assert not [b for b in out.boxes if b.text]
    assert set(out.metadata["lines_unanswered"]) == {"a", "b"} and out.metadata[NO_WRITING_KEY] == []


def test_a_generative_models_null_is_still_no_writing(monkeypatch, tmp_path):
    """The change is Apple Vision's: a vision MODEL that answers null looked at the line and found nothing written."""
    from fichero_server.llm import LLMConfig

    answers = iter(['["hola", null]'])

    async def fake_vision(**kw):
        return next(answers)

    monkeypatch.setattr(llm, "vision", fake_vision)
    path, geometry = _geometry(tmp_path, ["a", "b"])
    out = asyncio.run(line_reader.read_lines(path, geometry, LLMConfig(provider="openrouter", model="x")))
    assert out.metadata[NO_WRITING_KEY] == ["b"] and out.metadata["lines_unanswered"] == {}


def test_the_reason_reaches_the_line_and_the_page_counts_it_unread(db):
    from fichero_server.llm.working_lines import mark_unread_reasons
    from fichero_server.models.segments import Segment
    from fichero_server.recipes.done import unread_reasons
    from tests.unit.recipes.test_unread_lines_not_read_5758 import _page

    page = _page(db, 2, 0)
    empty = next(s for s in db.query(Segment, document_id=page) if s.kind == "line")
    mark_unread_reasons(db, {empty.id: line_reader.VISION_RETURNED_NOTHING})
    assert unread_reasons(db, page)[empty.id] == line_reader.VISION_RETURNED_NOTHING
