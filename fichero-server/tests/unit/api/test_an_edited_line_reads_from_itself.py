"""A line a person typed in the Reader reads from their reading, even when the file gave its words (#5224).

WHY: an imported line whose words carry their own text (PAGE `Word/TextEquiv`, ALTO `String`) is
read THROUGH its words. Typing in the Reader saves a person's reading of the LINE; read through the
words, the page, its line map and every export kept showing the old words, so the correction
vanished on refresh -- on every imported page with word-level text. If this regresses, a person's
line correction is saved and never seen.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.models import ContentRepresentation, Segment
from tests.unit.api.test_page_text_follows_the_file import CLM, _import

PERSON = ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _a_line_read_through_its_words(db, doc_id: str) -> Segment:
    rows = [s for s in db.all(Segment) if s.document_id == doc_id and s.deleted_at is None]
    worded = {r.parent_segment_id for r in rows if r.kind == "word"
              and db.query(ContentRepresentation, segment_id=r.id)}
    return next(r for r in rows if r.kind == "line" and r.id in worded)


def test_a_persons_line_reading_is_what_the_page_reads_and_its_words_are_not_read_twice(db):
    doc_id = _import(db, CLM)
    line = _a_line_read_through_its_words(db, doc_id)
    typed = "TYPED BY A PERSON"
    made = registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": line.id, "kind": "transcription", "content": typed,
    }, PERSON).result
    rep_id = made["id"] if isinstance(made, dict) else made.id

    text = document_text(db, doc_id)
    assert typed in text.text
    [span] = [s for s in text.spans if s.segment_id == line.id]
    assert span.representation_id == rep_id and text.text[span.start:span.end] == typed
    words = {r.id for r in db.all(Segment) if r.parent_segment_id == line.id}
    assert not [s for s in text.spans if s.segment_id in words], "the line's words must not be read as well"


def test_an_imported_line_with_word_text_is_still_read_through_its_words(db):
    doc_id = _import(db, CLM)
    line = _a_line_read_through_its_words(db, doc_id)
    spans = document_text(db, doc_id).spans
    assert not [s for s in spans if s.segment_id == line.id]
    assert [s for s in spans if s.segment_id in {r.id for r in db.all(Segment) if r.parent_segment_id == line.id}]
