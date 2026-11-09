"""`source.disagree.popover-lists-every-reader-and-the-lines-other-readings` (#6451/#6453): every compared reader appears on every line,
as a counted reading or as an absent reader with its why; absent readers are not counted in the agreement."""
from __future__ import annotations

from fichero_server.models import Artifact, ContentRepresentation
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from tests.unit.api.test_where_the_readers_disagree_5665 import _disagreement, _lines, _page, _read


def _page_reading(db, page, text, model):
    artifact = Artifact(document_id=page.id, artifact_type="transcription", provider="x", model=model, content=text)
    db.save(artifact)
    db.save(ContentRepresentation(document_id=page.id, kind="transcription", content=text, derived_from_artifact_id=artifact.id,
                                  source_anchor=SourceAnchor(document_id=page.id, rect=[0, 0, 1, 1]),
                                  producer_run_id="r", provenance_kind=ProvenanceKind.workflow))


def test_three_readers_make_three_appearances_on_a_line_one_of_them_never_tied(db, client):
    page, pass_row = _page(db)
    [one, two] = _lines(db, page, pass_row, 2)
    _read(db, page, one, "Cucharas", model="Gemini 3.1 Pro")
    _read(db, page, one, "cucharas", model="Gemini 3 Flash")
    _read(db, page, two, "dos cosas", model="Gemini 3.1 Pro")
    _read(db, page, two, "dos cosas", model="Gemini 3 Flash")
    _page_reading(db, page, "Cucharas. dos cosas", "Claude Haiku")  # read the page, tied to no line

    body = _disagreement(client, page.id)

    labels = {r["id"]: r["label"] for r in body["readers"]}
    assert len(labels) == 3
    for line in body["lines"]:
        counted = {x["reader"] for x in line["similarity"]} | {line["reference_reader"]}
        absent = {x["reader"] for x in line["absent"]}
        assert len(counted) + len(absent) == 3 and not counted & absent
        [haiku] = [x for x in line["absent"]]
        assert labels[haiku["reader"]] == "Claude Haiku" and haiku["why"] == "read the page, not tied to this line"


def test_a_reader_without_a_reading_of_one_line_is_absent_there_and_does_not_change_the_agreement(db, client):
    page, pass_row = _page(db)
    [one, two] = _lines(db, page, pass_row, 2)
    for model in ("A", "B", "C"):
        _read(db, page, one, "Yten dixo", model=model)
    for model in ("A", "B"):
        _read(db, page, two, "el testigo", model=model)

    body = _disagreement(client, page.id)

    first, second = body["lines"]
    assert first["absent"] == [] and first["agreement"] == 1.0
    assert [x["why"] for x in second["absent"]] == ["no reading of this line"] and second["agreement"] == 1.0
