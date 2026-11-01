"""#6085: the API lists one reading, not a stored reading and its provisional twin -- and what that must not break.

A verdict on an unconverted line is keyed by the PROVISIONAL reading's id, which conversion does not carry over. The
readers that look a reading up by an id (`kraken_set.lines_of_pass`, `line_check._person_checked`, `verdicts._proposal`,
the editorial span check) still see that id, though the listing shows the line once. (No editorial fact can be
recorded on an unconverted line: `editorial.record` refuses a `legacy:` segment.)
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from fichero_server.api.routes.document.segment_readings import (
    counting_by_kind,
    readings_of_segment,
    without_provisional_twins,
)
from fichero_server.models.checking import CheckVerdict, CheckVerdictParams
from fichero_server.models.readings import legacy_reading_segment_id
from tests.unit.api.test_segment_readings import _artifact, _convert, _converted_segments, _make_doc


@pytest.fixture
def converted(db, client):
    """A converted page, its third line, and the id its reading had before conversion (the provisional one)."""
    artifact = _artifact(db, _make_doc(db))
    _convert(client, artifact.id)
    segment = _converted_segments(db, artifact.id)[2]
    return artifact, segment, legacy_reading_segment_id(artifact.id, 2)


def _verdict(db, segment, target_id: str, verdict: str = "reject", trust: str = "person") -> CheckVerdict:
    row = CheckVerdict(layer="readings", target_id=target_id, document_id=segment.document_id, verdict=verdict,
                       reasons="x", checker="historian" if trust == "person" else "m", trust=trust)
    db.save(row)
    return row


def test_the_listing_hides_the_twin_but_the_id_lookup_can_still_see_it(db, converted):
    _, segment, provisional_id = converted
    assert provisional_id not in [r.id for r in readings_of_segment(db, segment.id)]
    assert provisional_id in [r.id for r in readings_of_segment(db, segment.id, with_provisional_twins=True)]


def test_a_rejected_provisional_reading_keeps_its_line_out_of_the_kraken_set(db, converted):
    from fichero_server.formats.harness import xml_id
    from fichero_server.training.kraken_set import lines_of_pass

    artifact, segment, provisional_id = converted
    reject = _verdict(db, segment, provisional_id, "reject")
    _, rejected, with_verdict = lines_of_pass(db, segment.pass_id, {provisional_id: reject})
    assert rejected == {xml_id(segment.id)} and with_verdict == 1


def test_a_line_a_person_checked_on_its_provisional_reading_is_still_checked(db, converted):
    from fichero_server.checking.line_check import _person_checked

    _, segment, provisional_id = converted
    confirm = _verdict(db, segment, provisional_id, "confirm")
    assert _person_checked(db, segment.id, {provisional_id: confirm}) is True


def test_a_verdict_names_the_provisional_reading_of_a_converted_line(db, converted):
    from fichero_server.checking.verdicts import _proposal

    _, segment, provisional_id = converted
    params = CheckVerdictParams(layer="readings", target_id=provisional_id, segment_id=segment.id,
                                verdict="confirm", reasons="x")
    assert _proposal(db, params) == segment.document_id


def test_a_span_naming_the_hidden_twin_is_accepted_and_kept_within_the_reading(db, converted):
    """`editorial._check_span` finds the reading by id among the line's readings with the twins kept, so a new span that
    names the hidden provisional twin is accepted and recorded with that id and its span (it is not drawn: the line's
    drawing takes facts on the counting reading only). A span past the twin's end is refused."""
    from fastapi import HTTPException

    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.api.routes.document.editorial import EditorialRecordParams, _check_span
    from fichero_server.models.editorial import EditorialFact

    _, segment, provisional_id = converted
    ctx = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
    result = registry.invoke(db, "editorial.record", {"segment_id": segment.id, "kind": "unclear",
                                                      "representation_id": provisional_id, "char_start": 0, "char_end": 3}, ctx)
    fact = db.get(EditorialFact, result.result["fact_id"])
    assert (fact.representation_id, fact.char_start, fact.char_end) == (provisional_id, 0, 3)
    with pytest.raises(HTTPException) as past:
        _check_span(db, EditorialRecordParams(segment_id=segment.id, kind="unclear", representation_id=provisional_id,
                                              char_start=0, char_end=7))
    assert past.value.status_code == 422


def test_a_retracted_stored_reading_does_not_hide_its_twin(db, converted):
    """The `not i.retracted` clause: a stored reading taken back says nothing now, so the provisional one stays listed."""
    _, segment, provisional_id = converted
    items = readings_of_segment(db, segment.id, with_provisional_twins=True)
    stored = [i for i in items if not i.provisional]
    retracted = [i.model_copy(update={"retracted": True}) for i in stored]
    twin = [i for i in items if i.provisional]
    assert twin and stored
    assert [i.id for i in without_provisional_twins(retracted + twin)] == [i.id for i in retracted + twin]
    assert [i.id for i in without_provisional_twins(stored + twin)] == [i.id for i in stored]


def test_where_the_twin_was_the_newest_machine_reading_the_next_reading_now_counts(db, converted):
    """The listing without the twin changes what counts in one case: a stored reading older than another reader's, with its
    artifact dated newer than both, counted the twin's words (the twin is dated by its artifact); without the twin the
    other reader's count. Readings are written after their artifact, so this order is made by hand here."""
    _, segment, provisional_id = converted
    items = readings_of_segment(db, segment.id, with_provisional_twins=True)
    stored = next(i for i in items if not i.provisional)
    twin = next(i for i in items if i.provisional)
    t0 = stored.created_at
    stored = stored.model_copy(update={"created_at": t0})
    other = stored.model_copy(update={"id": "other-reader", "content": "otro", "created_at": t0 + timedelta(minutes=1),
                                      "derived_from_artifact_id": None})
    twin = twin.model_copy(update={"created_at": t0 + timedelta(minutes=2)})
    before = counting_by_kind(db, segment.id, [stored, other, twin]).get("transcription")
    after = counting_by_kind(db, segment.id, without_provisional_twins([stored, other, twin])).get("transcription")
    assert before is not None and after is not None
    assert before.representation_id == twin.id
    assert after.representation_id == other.id
