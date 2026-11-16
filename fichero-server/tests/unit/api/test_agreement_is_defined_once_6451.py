"""`source.disagree.agreement-is-character-similarity-defined-once-and-never-accuracy` (#6451/#6453)."""
from __future__ import annotations

import re

from fichero_server.models import ContentRepresentation
from fichero_server.models.knowledge import ProvenanceKind
from tests.unit.api.test_where_the_readers_disagree_5665 import _disagreement, _lines, _page, _read


def test_a_line_is_one_minus_distance_over_the_longer_length(db, client):
    page, pass_row = _page(db)
    [line] = _lines(db, page, pass_row, 1)
    _read(db, page, line, "abcdefghij", model="A")
    _read(db, page, line, "abcdefghij", model="B")
    _read(db, page, line, "abcdefgxyz", model="C")  # three characters of ten differ

    body = _disagreement(client, page.id)

    [only] = body["lines"]
    [far] = [x for x in only["similarity"] if x["distance"]]
    assert (far["distance"], far["length"]) == (3, 10) and abs(far["agreement"] - 0.7) < 1e-9
    assert abs(only["agreement"] - (1.0 + 0.7) / 2) < 1e-9, "the mean over the readers other than the reference"


def test_the_page_is_the_length_weighted_mean_of_its_lines(db, client):
    page, pass_row = _page(db)
    [short, long_] = _lines(db, page, pass_row, 2)
    _read(db, page, short, "abcdefghij", model="A")
    _read(db, page, short, "abcdefghij", model="B")
    _read(db, page, long_, "a" * 30, model="A")
    _read(db, page, long_, "a" * 15 + "b" * 15, model="B")  # half of it differs: 50 %

    body = _disagreement(client, page.id)

    assert [round(x["agreement"], 3) for x in body["lines"]] == [1.0, 0.5]
    assert abs(body["page_agreement"] - 0.625) < 1e-9, "not the plain mean, 0.75"


def test_the_definition_is_the_engines_and_never_says_accuracy(db, client):
    page, pass_row = _page(db)
    [line] = _lines(db, page, pass_row, 1)
    _read(db, page, line, "dixo", model="A")
    _read(db, page, line, "dixo", model="B")

    words = _disagreement(client, page.id)["definition"]

    assert "1 - d / L" in words and not re.search(r"accura|\bCER\b|\bCAR\b", words.replace("not accuracy", ""))


def test_a_corrected_line_gets_its_own_figure_and_a_page_without_one_shows_none(db, client):
    page, pass_row = _page(db)
    [corrected, plain] = _lines(db, page, pass_row, 2)
    for line in (corrected, plain):
        _read(db, page, line, "abcdefghij", model="A")
        _read(db, page, line, "abcdefghij", model="B")
    assert _disagreement(client, page.id)["against_corrected"] is None
    db.save(ContentRepresentation(document_id=page.id, segment_id=corrected.id, kind="transcription", content="abcdefghix", source_anchor=corrected.anchor,
                                  provenance_kind=ProvenanceKind.human))

    body = _disagreement(client, page.id)

    first, second = body["lines"]
    assert [round(x["error_rate"], 3) for x in first["against_corrected"]] == [0.1, 0.1] and second["against_corrected"] == []
    assert body["against_corrected"]["lines"] == 1 and body["against_corrected"]["of_lines"] == 2
    assert abs(body["against_corrected"]["error_rate"] - 0.1) < 1e-9
    assert abs(first["agreement"] - 1.0) < 1e-9, "the readers still agree with each other: a separate figure"
