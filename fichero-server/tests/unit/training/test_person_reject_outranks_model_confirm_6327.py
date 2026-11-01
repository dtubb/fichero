"""#6327: a person's verdict on a line outranks a model's, whichever came last.

Verdicts are recorded through the real `check.verdict` action. A model's later confirm used to be the newest verdict
`kraken_set.lines_of_pass` took, so a line a person rejected went back into the training set.
"""

from __future__ import annotations

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import readings_of_segment
from fichero_server.formats.harness import xml_id
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
