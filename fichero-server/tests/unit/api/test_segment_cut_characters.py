"""Cut Characters: a word cut into its characters from the recogniser's character positions.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.cut-characters` (Cut Characters does what Cut
Words does inside a word, from its character positions, giving `character` children) and
`segment-editor.cut-records-source-and-confidence` (each carries its source, confidence, the reading and its stretch).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import registry
from fichero_server.models import Segment
from tests.unit.api.test_segment_cut_words import POSITIONS, TEXT, _cut, _line, _page, _person, _read, _words, _xs

pytestmark = pytest.mark.source_model


def _cut_characters(db, ids):
    return registry.invoke(db, "segment.cut_characters", {
        "segment_ids": ids, "expected_versions": {sid: db.get(Segment, sid).version for sid in ids}}, _person())


def _word_nombre(db, client, confidences=None):
    doc, pass_id = _page(db, client)
    line = _line(client, doc, pass_id)
    _read(db, line, TEXT, POSITIONS, confidences)
    _cut(db, [line])
    return line, _words(db, line)[-1]


def test_a_word_becomes_its_characters_each_where_the_recogniser_put_it(db, client):
    _line_id, nombre = _word_nombre(db, client, confidences=[0.9] * 12)

    made = _cut_characters(db, [nombre.id])

    chars = _words(db, nombre.id)
    assert len(chars) == 6 == len(made.result["segment_ids"])
    assert all(char.kind == "character" for char in chars)
    first_x0, first_x1 = _xs(chars[0])
    assert first_x0 == pytest.approx(0.1 + 0.455 * 0.8, abs=0.01), "the word's own start"
    assert first_x1 == pytest.approx(0.1 + POSITIONS[7] * 0.8, abs=0.01), "where the next character starts"
    assert [char.metadata["reading_span"] for char in chars] == [[i, i + 1] for i in range(6, 12)]
    assert {char.metadata["cut_source"] for char in chars} == {"ctc"}
    assert chars[0].metadata["cut_confidence"] == pytest.approx(0.9)


def test_one_undo_takes_the_characters_away(db, client):
    _line_id, nombre = _word_nombre(db, client)
    made = _cut_characters(db, [nombre.id])
    response = client.post(f"/api/actions/audit/{made.audit_id}/undo")
    assert response.status_code == 200, response.text
    assert _words(db, nombre.id) == []


def test_cutting_again_replaces_the_machines_characters(db, client):
    _line_id, nombre = _word_nombre(db, client)
    _cut_characters(db, [nombre.id])
    _cut_characters(db, [nombre.id])
    assert len(_words(db, nombre.id)) == 6


def test_a_word_with_no_positions_is_left_alone_and_said(db, client):
    doc, pass_id = _page(db, client, words_px=[(80, 200), (240, 320), (370, 700)])
    line = _line(client, doc, pass_id)
    _read(db, line, TEXT)  # no positions: the words were cut from the ink
    _cut(db, [line])
    word = _words(db, line)[-1]
    with pytest.raises(HTTPException) as refused:
        _cut_characters(db, [word.id])
    assert refused.value.status_code == 422
    assert "no-positions" in str(refused.value.detail)
