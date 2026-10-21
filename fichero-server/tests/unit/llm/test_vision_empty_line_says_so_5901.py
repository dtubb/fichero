"""`source.read.vision-empty-line-says-so` (#5901, review 524): a line Apple Vision comes back empty on is read once more in the
same run; empty twice it is FINAL ("Apple Vision returned nothing (twice)": a reason, not a reading) and does not keep the page
unfinished; a MOSTLY-empty page stays unread (the rate rule). Vision does not read one crop the same way twice, so one empty
answer is not evidence of a blank line."""
from __future__ import annotations

import asyncio
from collections import Counter

from fichero_server import llm
from fichero_server.llm import line_reader
from fichero_server.llm.working_lines import NO_WRITING_KEY, VISION_NOTHING_TWICE
from tests.unit.llm.test_line_reader_refusal import _geometry

TWICE = "Apple Vision returned nothing (twice)"


def _apple(monkeypatch, tmp_path, ids, answer):
    """`answer(line number, attempt) -> text`. Every crop of the drawn page is the same picture, so a call is told apart by
    its place in the order: the first len(ids) calls are the lines in order, the next ones the second attempts, in order."""
    attempts: Counter = Counter()
    calls: list[int] = []
    empties: list[int] = []

    async def fake_vision(images, **kw):
        assert kw.get("language") == "es-ES" and kw.get("recognition_only_ok") is True, "the Apple path"
        i = len(calls)
        n = i if i < len(ids) else empties[i - len(ids)]
        attempts[n] += 1
        calls.append(n)
        text = answer(n, attempts[n])
        if attempts[n] == 1 and not text:
            empties.append(n)
        return text

    monkeypatch.setattr(llm, "vision", fake_vision)
    path, geometry = _geometry(tmp_path, ids)
    out = asyncio.run(line_reader.read_lines(path, geometry, None, language="es-ES", apple=True))
    return out, Counter(calls)


def test_the_constant_is_the_ruled_wording():
    assert VISION_NOTHING_TWICE == TWICE


def test_empty_twice_is_final_with_the_reason_and_is_asked_exactly_twice(monkeypatch, tmp_path):
    out, calls = _apple(monkeypatch, tmp_path, ["a", "b", "c"], lambda n, attempt: "" if n == 0 else "hola")
    assert calls == {0: 2, 1: 1, 2: 1}, "the empty line is asked once more in the run, the read ones once"
    assert [b.metadata["segment_id"] for b in out.boxes if b.text] == ["b", "c"]
    assert out.metadata["lines_unanswered"] == {"a": TWICE}, "a reason, not a reading"
    assert out.metadata[NO_WRITING_KEY] == ["a"], "final: looked at, so the page is done and a Start does not ask again"


def test_a_second_answer_that_reads_is_the_lines_reading(monkeypatch, tmp_path):
    out, calls = _apple(monkeypatch, tmp_path, ["a", "b", "c"], lambda n, attempt: "" if (n == 0 and attempt == 1) else "hola")
    assert calls[0] == 2 and out.metadata["lines_unanswered"] == {} and out.metadata[NO_WRITING_KEY] == []
    assert [b.metadata["segment_id"] for b in out.boxes if b.text] == ["a", "b", "c"]


def test_a_mostly_empty_page_stays_unread_with_the_pages_reason_the_rate_rule(monkeypatch, tmp_path):
    from fichero_server.recipes.done import MOSTLY_NOTHING_FOR_PAGE

    ids = ["a", "b", "c", "d", "e"]
    out, _ = _apple(monkeypatch, tmp_path, ids, lambda n, attempt: "hola" if n >= 3 else "")  # 3 of 5 empty twice
    assert out.metadata["lines_unanswered"] == {"a": MOSTLY_NOTHING_FOR_PAGE, "b": MOSTLY_NOTHING_FOR_PAGE,
                                                "c": MOSTLY_NOTHING_FOR_PAGE}
    assert out.metadata[NO_WRITING_KEY] == [], "not final: a hand it cannot read is not a blank page"


def test_a_page_every_line_of_is_empty_twice_is_a_failed_read_not_blank(monkeypatch, tmp_path):
    from fichero_server.recipes.done import NOTHING_FOR_PAGE

    out, _ = _apple(monkeypatch, tmp_path, ["a", "b"], lambda n, attempt: "")
    assert set(out.metadata["lines_unanswered"].values()) == {NOTHING_FOR_PAGE} and out.metadata[NO_WRITING_KEY] == []
    assert not [b for b in out.boxes if b.text]


def test_a_few_empty_lines_on_a_page_that_reads_are_final_not_the_rate_rule(monkeypatch, tmp_path):
    ids = ["a", "b", "c", "d", "e"]
    out, _ = _apple(monkeypatch, tmp_path, ids, lambda n, attempt: "" if n == 0 else "hola")  # 1 of 5
    assert out.metadata["lines_unanswered"] == {"a": TWICE} and out.metadata[NO_WRITING_KEY] == ["a"]


def test_a_generative_models_null_is_still_no_writing_and_is_not_asked_again(monkeypatch, tmp_path):
    from fichero_server.llm import LLMConfig

    seen = []

    async def fake_vision(**kw):
        seen.append(1)
        return '["hola", null]'

    monkeypatch.setattr(llm, "vision", fake_vision)
    path, geometry = _geometry(tmp_path, ["a", "b"])
    out = asyncio.run(line_reader.read_lines(path, geometry, LLMConfig(provider="openrouter", model="x")))
    assert out.metadata[NO_WRITING_KEY] == ["b"] and out.metadata["lines_unanswered"] == {} and len(seen) == 1


def test_a_final_line_is_done_not_unread_carries_the_reason_and_is_counted_on_its_own(db):
    from fichero_server.llm.working_lines import mark_no_writing, mark_unread_reasons
    from fichero_server.models import ContentRepresentation
    from fichero_server.models.segments import Segment
    from fichero_server.recipes import run_view
    from fichero_server.recipes.done import lines_state, unread_on, unread_reasons, vision_gave_up
    from tests.unit.recipes.test_unread_lines_not_read_5758 import _page

    page = _page(db, 4, 3)  # three lines read, one without a reading
    read = {r.segment_id for r in db.query(ContentRepresentation, document_id=page)}
    [empty] = [s.id for s in db.query(Segment, document_id=page) if s.kind == "line" and s.id not in read]
    assert unread_on(db, page) == 1
    mark_no_writing(db, [empty], model="apple-vision")
    mark_unread_reasons(db, {empty: TWICE})
    assert unread_on(db, page) == 0, "the page is done: a Start does not ask Vision again"
    assert unread_reasons(db, page) == {}, "it is not listed as unread"
    assert db.get(Segment, empty).metadata["unread_reason"] == TWICE
    assert vision_gave_up(db, page) == 1 and lines_state(db, page)[2] == 1
    assert run_view.lines_seen_blank(db, [page]) == 0, "not also counted as 'found no writing on'"
    assert run_view.lines_vision_could_not_read(db, [page]) == 1
    summary = run_view.RecipeRunSummary(
        job_id="j", state="done", finished=True, pages=1, pages_read=1, names=[], dates=0, statements=0, failed=[],
        pages_failed=0, skipped=[], not_run=[], lines_vision_could_not_read=1)
    assert "1 line Vision could not read" in run_view._lines(summary, 0)
