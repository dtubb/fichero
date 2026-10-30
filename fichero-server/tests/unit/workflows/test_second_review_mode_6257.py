"""A second Review the reading model takes the first's work in turn, alone, or both and settles (#6257, owner 2026-10-29,
`source.recipe.second-reviewer`). In turn (the default) is shown the reading as the first review left it; compare is shown the
reading the first review started from, so it reviews it on its own; both is shown that reading and the first review's version of
each line it changed, to settle, with what it cannot settle marked for a person. On the real Vienna Syriac folio (CC-BY-SA)."""
from __future__ import annotations

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.llm.working_lines import write_readings
from fichero_server.models import Artifact, ContentRepresentation
from fichero_server.tool_context import BOTH, COMPARE, IN_TURN, as_prompt_context, tool_context
from tests.unit.api.test_reader_directions import SYRIAC, _import

FIRST_REVIEW = "first reviewer's version"


def _reviewed_page(db):
    """The imported page with one line its first review corrected; (page id, line id, the reading it started from)."""
    doc_id = _import(db, SYRIAC)
    line = next(r for r in tool_context(db, doc_id).segment_ids)
    started = tool_context(db, doc_id).text.splitlines()
    before = next(row.split(" | ", 3)[3] for row in started if row.startswith(line))
    reading = next(r for r in db.query(ContentRepresentation, document_id=doc_id) if r.segment_id == line)
    artifact = Artifact(document_id=doc_id, artifact_type="transcription_review", content=f"{line} | {FIRST_REVIEW}")
    db.save(artifact)
    write_readings(db, document_id=doc_id, readings=[(line, FIRST_REVIEW)], artifact_id=artifact.id, run_id=None,
                   derived_from={line: reading.id})
    return doc_id, line, before


def _text_of(context, line):
    return next(row.split(" | ", 3)[3] for row in context.text.splitlines() if row.startswith(line))


def test_in_turn_is_shown_the_reading_as_the_first_review_left_it(db):
    doc_id, line, _before = _reviewed_page(db)
    assert _text_of(tool_context(db, doc_id), line) == FIRST_REVIEW
    assert _text_of(tool_context(db, doc_id, review_mode=IN_TURN), line) == FIRST_REVIEW


def test_compare_is_shown_the_reading_the_first_review_started_from(db):
    doc_id, line, before = _reviewed_page(db)
    got = tool_context(db, doc_id, review_mode=COMPARE)
    assert _text_of(got, line) == before != FIRST_REVIEW
    assert got.first_review == {}  # it does not see the other's version: that is the point of comparing


def test_both_is_given_the_starting_reading_and_the_first_reviews_version_to_settle(db):
    doc_id, line, before = _reviewed_page(db)
    got = tool_context(db, doc_id, review_mode=BOTH)
    assert _text_of(got, line) == before and got.first_review == {line: FIRST_REVIEW}
    words = as_prompt_context(got)
    assert f"their version of {line}: {FIRST_REVIEW}" in words and "uncertain" in words and "settle" in words
    assert "settle" not in as_prompt_context(tool_context(db, doc_id, review_mode=COMPARE))


def test_a_page_no_review_touched_reads_the_same_in_every_mode(db):
    doc_id = _import(db, SYRIAC)
    assert tool_context(db, doc_id, review_mode=COMPARE).text == tool_context(db, doc_id).text
    assert tool_context(db, doc_id, review_mode=BOTH).first_review == {}


def test_a_mode_nobody_defined_is_refused_naming_the_valid_ones(db):
    doc_id = _import(db, SYRIAC)
    with pytest.raises(ValueError, match="in-turn, compare, both; not 'together'"):
        tool_context(db, doc_id, review_mode="together")


def _settled(db, doc_id, line, answer_text, *, settling=True):
    """The second review's answer for the first-changed line, put onto the lines; the line's counting reading after."""
    from fichero_server.api.routes.document.segment_readings import document_text
    from fichero_server.llm.working_lines import correct_lines

    artifact = Artifact(document_id=doc_id, artifact_type="transcription_review", content=f"{line} | uncertain | {answer_text}")
    db.save(artifact)
    correct_lines(db, document_id=doc_id, text=artifact.content, artifact_id=artifact.id, run_id=None, settling=settling)
    span = next(s for s in document_text(db, doc_id, include_furniture=True).spans if s.segment_id == line)
    return db.get(ContentRepresentation, span.representation_id)


@pytest.mark.parametrize("answer", [FIRST_REVIEW, "the second reviewer's version"])
def test_a_line_both_cannot_settle_keeps_a_lower_certainty_whichever_version_it_gives(db, answer):
    doc_id, line, _before = _reviewed_page(db)
    reading = _settled(db, doc_id, line, answer)
    assert reading.content == answer and reading.machine_confidence is not None and reading.machine_confidence <= 0.5


def test_a_line_flagged_uncertain_outside_both_is_as_before(db):
    doc_id, line, _before = _reviewed_page(db)
    reading = _settled(db, doc_id, line, "the second reviewer's version", settling=False)
    assert reading.machine_confidence is None


def test_the_settle_rows_are_not_listed_lines_so_nothing_counts_or_trims_them(db):
    from fichero_server.workflows.tools.transcribe_review import _SHOWN_LINE, _only_unsure, shows_segment_lines

    doc_id, line, _before = _reviewed_page(db)
    words = as_prompt_context(tool_context(db, doc_id, review_mode=BOTH), confidence=True)
    listed = [row for row in words.splitlines() if _SHOWN_LINE.match(row)]
    assert len(listed) == len(tool_context(db, doc_id, review_mode=BOTH).segment_ids)
    assert FIRST_REVIEW in words and shows_segment_lines(words)
    _kept, _said, (_sent, total) = _only_unsure(words, 0.5, "m")
    assert total == len(listed)


def test_an_answer_that_names_a_line_twice_still_ties_and_the_later_answer_wins(db):
    from fichero_server.llm.working_lines import correct_lines

    doc_id, line, _before = _reviewed_page(db)
    artifact = Artifact(document_id=doc_id, artifact_type="transcription_review",
                        content=f"{line} | certain | settled text\n{line} | uncertain | settled text again")
    db.save(artifact)
    made, said = correct_lines(db, document_id=doc_id, text=artifact.content, artifact_id=artifact.id, run_id=None,
                               settling=True)
    assert len(made) == 1 and "NOT_TIED" not in said
    assert db.get(ContentRepresentation, made[0]).content == "settled text again"
