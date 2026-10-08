"""Correcting a line takes the segment and its new text, nothing more (#5499, `source.reading.correct-a-line`).

WHY: the operator correcting a line through the CLI needed `representation.create` with three ids and six
flags. The route works out the document, the reading corrected and the compare-and-set itself, through the
one action every correction is -- so it counts, is audited, and undoes as the Reader's typing does.

Through `format.import` of a real page, as `test_a_correction_counts.py`.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.api.routes.document.segment_readings import counting_by_kind, document_text, readings_of_segment
from tests.unit.api.test_reader_directions import ARABIC, _import
from tests.unit.api.test_reader_line_map import _view
from tests.unit.api.test_page_text_follows_the_file import BOOT


def _third_line(db, client):
    doc_id = _import(db, ARABIC)
    line = _view(client, doc_id)[0]["pages"][0]["lines"][2]
    return doc_id, line["segment_id"], line["representation_id"]


def _counts(db, segment_id):
    return counting_by_kind(db, segment_id, readings_of_segment(db, segment_id))["transcription"]


def test_source_reading_correct_a_line__segment_and_text_only(db, client):
    """source.reading.correct-a-line: "takes the segment and its new text, nothing more ... the engine fills
    in the document, the reading it corrects ... a person's correction counts\""""
    doc_id, segment_id, file_reading = _third_line(db, client)
    response = client.post(f"/api/segments/{segment_id}/correct", json={"text": "the line, corrected"})
    assert response.status_code == 200, response.text
    made = response.json()
    assert (made["document_id"], made["segment_id"]) == (doc_id, segment_id)
    assert made["corrects_representation_id"] == file_reading
    assert made["kind"] == "transcription"
    answer = _counts(db, segment_id)
    assert (answer.representation_id, answer.basis.value) == (made["id"], "correction")
    assert "the line, corrected" in document_text(db, doc_id).text


def test_source_reading_correct_a_line__a_second_correction_corrects_the_first(db, client):
    _doc_id, segment_id, _file = _third_line(db, client)
    first = client.post(f"/api/segments/{segment_id}/correct", json={"text": "first fix"}).json()
    second = client.post(f"/api/segments/{segment_id}/correct", json={"text": "second fix"}).json()
    assert second["corrects_representation_id"] == first["id"]
    assert _counts(db, segment_id).representation_id == second["id"]


def test_source_reading_correct_a_line__undo_brings_the_reading_back(db, client):
    """source.reading.correct-a-line: "audited and undone as one\""""
    _doc_id, segment_id, file_reading = _third_line(db, client)
    response = client.post(f"/api/segments/{segment_id}/correct", json={"text": "a fix"})
    assert response.status_code == 200, response.text
    rows = client.get("/api/actions/audit", params={"limit": 1}).json()["items"]
    assert rows[0]["action_name"] == "representation.create"
    assert client.post(f"/api/actions/audit/{rows[0]['id']}/undo").status_code == 200
    assert _counts(db, segment_id).representation_id == file_reading


def test_source_reading_correct_a_line__stale_is_refused_and_nothing_written(db, client):
    """source.reading.correct-a-line: "when another reading counts than the one the caller read, it is refused
    with 409 and nothing is written\""""
    doc_id, segment_id, file_reading = _third_line(db, client)
    registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": segment_id, "kind": "transcription",
        "content": "someone else's fix", "corrects_representation_id": file_reading}, BOOT)
    before = len(readings_of_segment(db, segment_id))
    response = client.post(
        f"/api/segments/{segment_id}/correct", json={"text": "mine", "expected_counting_id": file_reading})
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["counting_text"] == "someone else's fix"
    assert len(readings_of_segment(db, segment_id)) == before


def test_source_reading_correct_a_line__unknown_and_provisional_segments_refused(db, client):
    _third_line(db, client)
    assert client.post("/api/segments/no-such-segment/correct", json={"text": "x"}).status_code == 404
    assert client.post("/api/segments/legacy:art:0/correct", json={"text": "x"}).status_code == 422


def test_source_reading_correct_a_line__empty_text_refused(db, client):
    _doc_id, segment_id, _file = _third_line(db, client)
    assert client.post(f"/api/segments/{segment_id}/correct", json={"text": ""}).status_code == 422
