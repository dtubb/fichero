"""#6462 (`source.editor.compare-two-to-four-readings-with-the-line-picture-and-edit-in-line`): an edit of a
compared reading writes a NEW reading derived from THAT reading at ITS level and kind -- not from whichever
reading counts now. `POST /api/segments/{id}/correct` takes the reading to correct."""
from __future__ import annotations

from tests.unit.api.test_correct_a_line import _third_line




def test_a_correction_names_the_reading_it_corrects_and_keeps_its_level(db, client):
    doc_id, segment_id, file_reading = _third_line(db, client)
    counting = client.post(f"/api/segments/{segment_id}/correct", json={"text": "the one that counts"}).json()
    chosen = client.post(
        f"/api/segments/{segment_id}/correct",
        json={"text": "edited from the file reading", "corrects_representation_id": file_reading},
    )
    assert chosen.status_code == 200, chosen.text
    made = chosen.json()
    assert made["corrects_representation_id"] == file_reading != counting["id"]
    assert made["kind"] == "transcription" and made["provenance_kind"] == "human"


def test_a_reading_of_another_line_is_refused_and_nothing_is_written(db, client):
    _doc, segment_id, _file = _third_line(db, client)
    refused = client.post(f"/api/segments/{segment_id}/correct",
                          json={"text": "x", "corrects_representation_id": "no-such-reading"})
    assert 400 <= refused.status_code < 500, refused.text
