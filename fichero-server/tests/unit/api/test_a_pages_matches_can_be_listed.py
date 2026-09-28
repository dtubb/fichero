"""A page's segment matches can be LISTED, so a person can review them (#5165).

WHY: a match could be proposed (`POST /api/segments/matches`), accepted and rejected -- and
nothing could list them. A proposal made by a tool, or by a person yesterday, was only reachable
by its id, which the review surface does not have: it could never be reviewed, so the carry
across it could never be made. If this regresses, the review list is empty however many
proposals wait.

Through the routes the app calls, on a real imported page.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from tests.unit.api.test_reader_directions import ARABIC, _import
from tests.unit.api.test_reader_line_map import _view


def test_proposed_matches_are_listed_and_filtered_by_state(db, client):
    doc_id = _import(db, ARABIC)
    ids = [line["segment_id"] for line in _view(client, doc_id)[0]["pages"][0]["lines"]]
    first = client.post("/api/segments/matches", json={"from_segment_id": ids[0], "to_segment_id": ids[1]})
    second = client.post("/api/segments/matches", json={"from_segment_id": ids[2], "to_segment_id": ids[3]})
    assert first.status_code == second.status_code == 200, (first.text, second.text)
    assert client.post(f"/api/segments/matches/{second.json()['id']}/reject").status_code == 200

    everything = client.get(f"/api/segments/document/{doc_id}/matches").json()
    assert everything["count"] == 2
    assert [(m["from_segment_id"], m["to_segment_id"]) for m in everything["items"]] == [(ids[0], ids[1]), (ids[2], ids[3])]

    waiting = client.get(f"/api/segments/document/{doc_id}/matches", params={"state": "proposed"}).json()
    assert [m["id"] for m in waiting["items"]] == [first.json()["id"]]


def test_another_pages_matches_are_not_listed(db, client):
    doc_id = _import(db, ARABIC)
    other = _import(db, ARABIC.with_name(ARABIC.name))   # the same file on a second page
    ids = [line["segment_id"] for line in _view(client, doc_id)[0]["pages"][0]["lines"]]
    client.post("/api/segments/matches", json={"from_segment_id": ids[0], "to_segment_id": ids[1]})
    assert client.get(f"/api/segments/document/{other}/matches").json() == {"items": [], "count": 0}
