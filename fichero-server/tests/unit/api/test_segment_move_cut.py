"""A cut mark moved by hand: the boundary between two words moves, and the cut becomes a person's.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.cut-marks-editable` (drag a cut mark to move
the cut: the two words' shapes, `cut_source: person`) and `segment-editor.cut-records-source-and-confidence` (a person's
cut has confidence 1). One action, one undo.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import registry
from fichero_server.models import Segment
from tests.unit.api.test_segment_cut_words import POSITIONS, TEXT, _cut, _line, _page, _person, _read, _words, _xs

pytestmark = pytest.mark.source_model


def _cut_page(db, client):
    doc, pass_id = _page(db, client)
    line = _line(client, doc, pass_id)
    _read(db, line, TEXT, POSITIONS)
    _cut(db, [line])
    return line, _words(db, line)


def _move(db, first, second, at):
    return registry.invoke(db, "segment.move_cut", {
        "first_id": first.id, "second_id": second.id, "at": at,
        "expected_versions": {first.id: db.get(Segment, first.id).version, second.id: db.get(Segment, second.id).version},
    }, _person())


def test_moving_the_cut_moves_where_one_word_ends_and_the_next_begins(db, client):
    line, (en, el, nombre) = _cut_page(db, client)
    before_el_start, _ = _xs(el)

    _move(db, el, nombre, 0.5)

    el_x0, el_x1 = _xs(db.get(Segment, el.id))
    nombre_x0, _ = _xs(db.get(Segment, nombre.id))
    assert el_x1 == pytest.approx(0.1 + 0.5 * 0.8, abs=0.01)
    assert nombre_x0 == pytest.approx(0.1 + 0.5 * 0.8, abs=0.01)
    assert el_x0 == pytest.approx(before_el_start, abs=0.01), "the word's other end stays"
    for word in (el, nombre):
        meta = db.get(Segment, word.id).metadata
        assert meta["cut_source"] == "person" and meta["cut_confidence"] == 1.0
    assert db.get(Segment, el.id).baseline[-1][0] == pytest.approx(0.5, abs=0.01)


def test_one_undo_puts_both_words_back(db, client):
    line, (_en, el, nombre) = _cut_page(db, client)
    shapes = {word.id: db.get(Segment, word.id).anchor.polygon for word in (el, nombre)}
    moved = _move(db, el, nombre, 0.5)
    response = client.post(f"/api/actions/audit/{moved.audit_id}/undo")
    assert response.status_code == 200, response.text
    assert {wid: db.get(Segment, wid).anchor.polygon for wid in shapes} == shapes


def test_a_cut_past_either_word_is_refused(db, client):
    line, (en, el, nombre) = _cut_page(db, client)
    with pytest.raises(HTTPException) as refused:
        _move(db, el, nombre, 0.2)  # inside "en", before "el" starts
    assert refused.value.status_code == 422


def test_words_of_two_lines_are_refused(db, client):
    line, (en, el, nombre) = _cut_page(db, client)
    other = db.get(Segment, nombre.id)
    other.parent_segment_id = None
    db.save(other)
    with pytest.raises(HTTPException):
        _move(db, el, other, 0.5)
