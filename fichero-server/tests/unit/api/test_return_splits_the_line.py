"""Return in a line splits it at the character (#5154): `segment.split(at_offset=)`.

WHY: the Reader knows the character the caret is at; nothing knows where that character sits on
the image. The honest first version (ruled 2026-09-28) cuts the box in proportion to the
characters, ALONG THE LINE'S DIRECTION, and says so (`cut: estimated`). Proportional is wrong in
a known way a person can reshape; a cut on the wrong SIDE is wrong in a way nobody would expect:
cutting an Arabic line from the left gives its first words the box of its last. So the direction
is what these pin: rtl text starts at the right edge, a column at the top. If this regresses, the
first part of a right-to-left line is drawn over its end, or the texts of the parts do not add up
to the line's text as the file wrote it (lxml).
"""

from __future__ import annotations

from pytest import approx

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.api.routes.document.segments import estimated_cut
from fichero_server.models import ContentRepresentation, Segment
from tests.unit.api.test_page_text_follows_the_file import BOOT
from tests.unit.api.test_reader_directions import ARABIC, CHINESE, _import, _line_texts
from tests.unit.api.test_reader_line_map import _view


def _split_third_line(db, client, path, offset):
    doc_id = _import(db, path)
    page = _view(client, doc_id)[0]["pages"][0]
    line = page["lines"][2]
    text = page["content"][line["char_start"]:line["char_end"]]
    before = db.get(Segment, line["segment_id"])
    rect = list(before.anchor.rect)
    result = registry.invoke(db, "segment.split", {
        "segment_id": before.id, "at_offset": offset, "expected_version": before.version,
    }, BOOT).result
    kept, new = db.get(Segment, result["kept_id"]), db.get(Segment, result["new_segment_ids"][0])
    readings = {r.segment_id: r.content for r in db.all(ContentRepresentation)
                if r.id in set(result["representation_ids"])}
    return text, rect, kept, new, readings


def test_an_rtl_line_splits_from_the_right(db, client):
    text, rect, kept, new, readings = _split_third_line(db, client, ARABIC, 5)
    assert text == [t for t in _line_texts(ARABIC) if t][2]                   # the file's line
    assert (readings[kept.id], readings[new.id]) == (text[:5], text[5:])
    x, y, w, h = rect
    assert kept.anchor.rect == approx([x + w * (1 - 5 / len(text)), y, w * 5 / len(text), h])   # right end
    assert new.anchor.rect == approx([x, y, w * (1 - 5 / len(text)), h])
    assert kept.metadata["cut"] == new.metadata["cut"] == "estimated"


def test_a_column_splits_from_the_top(db, client):
    text, rect, kept, new, readings = _split_third_line(db, client, CHINESE, 2)
    assert (readings[kept.id], readings[new.id]) == (text[:2], text[2:])
    x, y, w, h = rect
    assert kept.anchor.rect == approx([x, y, w, h * 2 / len(text)])
    assert new.anchor.rect == approx([x, y + h * 2 / len(text), w, h * (1 - 2 / len(text))])


def test_ltr_and_the_edges():
    first, second = estimated_cut([0.1, 0.2, 0.4, 0.05], 0.25, "ltr")
    assert first == approx([0.1, 0.2, 0.1, 0.05]) and second == approx([0.2, 0.2, 0.3, 0.05])


def test_an_offset_outside_the_line_is_refused(db, client):
    import pytest
    from fastapi import HTTPException

    doc_id = _import(db, ARABIC)
    line = _view(client, doc_id)[0]["pages"][0]["lines"][2]
    row = db.get(Segment, line["segment_id"])
    for offset in (0, line["char_end"] - line["char_start"]):
        with pytest.raises(HTTPException) as refused:
            registry.invoke(db, "segment.split", {
                "segment_id": row.id, "at_offset": offset, "expected_version": row.version}, BOOT)
        assert refused.value.status_code == 422
