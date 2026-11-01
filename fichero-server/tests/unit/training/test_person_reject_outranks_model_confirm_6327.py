"""#6327: a person's verdict on a line outranks a model's, whichever came last.

Verdicts are recorded through the real `check.verdict` action. A model's later confirm used to be the newest verdict
`kraken_set.lines_of_pass` took, so a line a person rejected went back into the training set.
"""

from __future__ import annotations

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import readings_of_segment
from fichero_server.formats.harness import xml_id
from fichero_server.models.readings import legacy_reading_segment_id
from tests.unit.api.test_segment_readings import _artifact, _convert, _converted_segments, _make_doc

PERSON = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
MODEL = ActionContext(actor="checker", library_path=None, is_bootstrap=True)


@pytest.fixture
def line(db, client):
    artifact = _artifact(db, _make_doc(db))
    _convert(client, artifact.id)
    segment = _converted_segments(db, artifact.id)[2]
    return segment, readings_of_segment(db, segment.id)[0].id


def _say(db, segment, reading_id, verdict, *, by_model: bool):
    params = {"layer": "readings", "target_id": reading_id, "segment_id": segment.id, "verdict": verdict, "reasons": "x"}
    if by_model:
        params["checker_model"] = "anthropic/claude-fable"
    registry.invoke(db, "check.verdict", params, MODEL if by_model else PERSON)


def _rejected(db, segment):
    from fichero_server.training.kraken_set import lines_of_pass, newest_reading_verdicts

    return lines_of_pass(db, segment.pass_id, newest_reading_verdicts(db))[1]


def test_a_model_confirming_after_a_person_rejected_does_not_bring_the_line_back(db, line):
    segment, reading_id = line
    _say(db, segment, reading_id, "reject", by_model=False)
    _say(db, segment, reading_id, "confirm", by_model=True)
    assert xml_id(segment.id) in _rejected(db, segment)


def test_a_model_rejecting_after_a_person_confirmed_does_not_throw_the_line_out(db, line):
    segment, reading_id = line
    _say(db, segment, reading_id, "confirm", by_model=False)
    _say(db, segment, reading_id, "reject", by_model=True)
    assert xml_id(segment.id) not in _rejected(db, segment)


def test_a_model_reject_alone_still_flags_the_line(db, line):
    segment, reading_id = line
    _say(db, segment, reading_id, "reject", by_model=True)
    assert xml_id(segment.id) in _rejected(db, segment)


def test_a_later_person_verdict_replaces_an_earlier_person_verdict(db, line):
    segment, reading_id = line
    _say(db, segment, reading_id, "reject", by_model=False)
    _say(db, segment, reading_id, "confirm", by_model=False)
    assert xml_id(segment.id) not in _rejected(db, segment)


def test_a_model_confirming_another_reading_of_the_line_does_not_bring_it_back(db, client):
    """Two readings on one line (the stored one and its provisional twin): the person rejected the first, a model later
    confirmed the second. The line's standing verdict is the person's."""
    artifact = _artifact(db, _make_doc(db))
    _convert(client, artifact.id)
    segment = _converted_segments(db, artifact.id)[2]
    stored = readings_of_segment(db, segment.id)[0].id
    twin = legacy_reading_segment_id(artifact.id, 2)
    assert twin != stored and twin in [r.id for r in readings_of_segment(db, segment.id, with_provisional_twins=True)]
    _say(db, segment, stored, "reject", by_model=False)
    _say(db, segment, twin, "confirm", by_model=True)
    assert xml_id(segment.id) in _rejected(db, segment)


def _claim(db):
    from fichero_server.models.knowledge import KnowledgeClaim

    doc = _make_doc(db)
    claim = KnowledgeClaim(text="El rey murio en 1492", source_document_id=doc.id)
    db.save(claim)
    return doc, claim


def _say_claim(db, claim, verdict, *, by_model: bool):
    params = {"layer": "claims", "target_id": claim.id, "verdict": verdict, "reasons": "x"}
    if by_model:
        params["checker_model"] = "anthropic/claude-fable"
    registry.invoke(db, "check.verdict", params, MODEL if by_model else PERSON)


def test_the_catalogue_keeps_a_claim_a_person_rejected_when_a_model_confirms_it_later(db):
    from fichero_server.catalogue_sheet import facts

    doc, claim = _claim(db)
    _say_claim(db, claim, "reject", by_model=False)
    _say_claim(db, claim, "confirm", by_model=True)
    assert facts(db).rejected == {doc.id: [claim.text]}


def test_the_catalogue_does_not_list_a_claim_a_person_confirmed_when_a_model_rejects_it_later(db):
    from fichero_server.catalogue_sheet import facts

    _, claim = _claim(db)
    _say_claim(db, claim, "confirm", by_model=False)
    _say_claim(db, claim, "reject", by_model=True)
    assert facts(db).rejected == {}


def _checked(db, reading_id: str, *, reviewed: bool) -> bool:
    from fichero_server.api.routes.document.segment_readings import ReadingMeasures
    from fichero_server.models import Artifact

    item = next(r for r in _all_readings(db) if r.id == reading_id)
    artifact = db.get(Artifact, item.derived_from_artifact_id)
    artifact.reviewed = reviewed
    db.save(artifact)
    return ReadingMeasures(db).of(item)["checked"]


def _all_readings(db):
    from fichero_server.models import Segment

    return [r for s in db.query(Segment) for r in readings_of_segment(db, s.id)]


def test_a_reviewed_machine_reading_a_person_rejected_stays_unchecked_when_a_model_confirms_it(db, line):
    segment, reading_id = line
    _say(db, segment, reading_id, "reject", by_model=False)
    _say(db, segment, reading_id, "confirm", by_model=True)
    assert _checked(db, reading_id, reviewed=True) is False


def test_a_machine_reading_a_person_confirmed_stays_checked_when_a_model_rejects_it(db, line):
    segment, reading_id = line
    _say(db, segment, reading_id, "confirm", by_model=False)
    _say(db, segment, reading_id, "reject", by_model=True)
    assert _checked(db, reading_id, reviewed=False) is True
