"""#5077: a mark made on a SELECTION (`Annotation.targets`: a line and a stretch of its reading, in
UTF-16) follows its words when a correction changes that line, and is FLAGGED, never moved silently,
when the words are gone.

Why: the target's offsets index one line's reading. Once a correction rewrites the line, offsets left
alone point at other words, so a highlight or note on a selection would quietly cover the wrong text
(and export as the wrong PDF markup). Highlights on page text already follow (test_highlights_follow_
corrections.py); this pins the same rule for marks on a selection. Do not loosen these to pass.
"""
from __future__ import annotations

import pytest

from fichero_server.models.knowledge import Annotation, AnnotationKind, MarkTarget

from .test_page_content_is_a_cache import _converted, _correct

pytestmark = pytest.mark.source_model


def _mark(db, page_id: str, segment_id: str, line: str, words: str) -> Annotation:
    """As the Reader does: a mark is made on a page the Reader has read, which stores its line map."""
    from fichero_server.actions.page_text_cache import ensure_current

    ensure_current(db, [page_id])
    start = line.index(words)  # ASCII here, so code points equal UTF-16 units
    ann = Annotation(document_id=page_id, kind=AnnotationKind.highlight,
                     targets=[MarkTarget(segment_id=segment_id, char_start=start, char_end=start + len(words))])
    db.save(ann)
    return ann


def test_a_mark_on_a_lengthened_line_still_covers_its_words(db, client):
    page, _art, row = _converted(db, client)
    ann = _mark(db, page.id, row.id, "In the year of our Lord", "our Lord")
    _correct(db, page, row, content="Truly, in the year of our Lord")
    target = db.get(Annotation, ann.id).targets[0]
    assert "Truly, in the year of our Lord"[target.char_start:target.char_end] == "our Lord"
    assert "reanchor" not in (db.get(Annotation, ann.id).metadata or {})


def test_a_mark_on_words_the_correction_removed_is_flagged_not_moved(db, client):
    page, _art, row = _converted(db, client)
    ann = _mark(db, page.id, row.id, "In the year of our Lord", "our Lord")
    _correct(db, page, row, content="In the year of grace")
    got = db.get(Annotation, ann.id)
    assert (got.targets[0].char_start, got.targets[0].char_end) == (15, 23)
    assert got.metadata["reanchor"]["status"] == "lost"
    assert got.metadata["reanchor"]["segment_id"] == row.id
