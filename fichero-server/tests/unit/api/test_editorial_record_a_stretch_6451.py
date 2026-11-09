"""#6451 / #6454: a stretch of a reading is marked Unclear, Lost or Supplied from the Reader through `editorial.record` with a span.

The span is measured on the reading SHOWN where the selection was made (`representation_id`). Inside the reading it is accepted for
each of the three kinds; past the end it is refused in words; ⌘Z (the audit undo) withdraws the fact. On the recorded Syriac page.
"""
from __future__ import annotations

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from tests.unit.api.test_editorial_facts import _first_line, _invoke
from tests.unit.api.test_page_text_follows_the_file import SYRIAC, _import


@pytest.mark.parametrize("kind", ["unclear", "lost", "supplied"])
def test_a_span_inside_the_reading_is_recorded_for_each_kind_and_undo_withdraws_it(db, client, kind):
    doc_id = _import(db, SYRIAC)
    line, reading = _first_line(client, doc_id)
    recorded = _invoke(client, "editorial.record", {
        "segment_id": line["id"], "kind": kind, "representation_id": reading["id"], "char_start": 0, "char_end": 2,
    })
    assert recorded.status_code == 200, recorded.text
    [fact] = client.get(f"/api/editorial/segment/{line['id']}").json()["items"]
    assert (fact["kind"], fact["char_start"], fact["char_end"], fact["representation_id"]) == (kind, 0, 2, reading["id"])

    undone = client.post(f"/api/actions/audit/{recorded.json()['audit_id']}/undo")
    assert undone.status_code == 200, undone.text
    assert client.get(f"/api/editorial/segment/{line['id']}").json()["items"] == []


def test_a_span_past_the_end_of_the_reading_is_refused_in_words(db, client):
    doc_id = _import(db, SYRIAC)
    line, reading = _first_line(client, doc_id)
    refused = _invoke(client, "editorial.record", {
        "segment_id": line["id"], "kind": "unclear", "representation_id": reading["id"],
        "char_start": 0, "char_end": len(reading["content"]) + 5,
    })
    assert refused.status_code == 422
    assert "past the reading's" in refused.json()["detail"]
    assert client.get(f"/api/editorial/segment/{line['id']}").json()["items"] == []
