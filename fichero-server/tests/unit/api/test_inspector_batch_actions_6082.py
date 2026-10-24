"""The Inspector's multi-selection acts on every selected line in ONE request, one audit id, one undo, all or nothing (#6082):
`hand.attribute_many`, `rights.set_many`, `editorial.record_many`, and one read, `POST /api/source-settings/resolve-many`, so a
selection is read in one request instead of one per line. Real lines from the DDbDP papyrus fixtures."""
from __future__ import annotations

from pathlib import Path

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models import Segment
from fichero_server.models.editorial import EditorialFact
from fichero_server.models.hands import HandAttribution
from fichero_server.models.rights import RightsRecord
from tests.unit.api.test_page_text_follows_the_file import _import

ZENON = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus" / "ddbdp_greek-papyrus_p.cair.zen.4.59742.tei.xml"


def _lines(db) -> list[Segment]:
    doc = _import(db, ZENON)
    return sorted((s for s in db.all(Segment) if s.document_id == doc and s.kind == "line"),
                  key=lambda s: s.metadata["file_position"])[:4]


def _live(db, model):
    return [r for r in db.all(model) if r.withdrawn_at is None]


def _hand(client) -> str:
    return client.post("/api/hands", json={"label": "m1"}).json()["result"]["hand_id"]


def test_one_hand_on_many_lines_is_one_audit_row_and_one_undo(db, client):
    lines, hand = _lines(db), None
    hand = _hand(client)
    r = client.post("/api/hands/attributions/many", json={"hand_id": hand, "segment_ids": [s.id for s in lines]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["result"]["attribution_ids"]) == len(lines) and body["result"]["skipped"] == []
    assert len([a for a in _live(db, HandAttribution) if a.hand_id == hand]) == len(lines)
    assert client.post(f"/api/actions/audit/{body['audit_id']}/undo").status_code == 200
    assert [a for a in _live(db, HandAttribution) if a.hand_id == hand] == []


def test_a_line_already_in_that_hand_is_skipped_not_doubled(db, client):
    lines, hand = _lines(db), _hand(client)
    client.post("/api/hands/attributions", json={"hand_id": hand, "segment_id": lines[0].id})
    body = client.post("/api/hands/attributions/many", json={"hand_id": hand, "segment_ids": [s.id for s in lines]}).json()
    assert body["result"]["skipped"] == [lines[0].id]
    assert len([a for a in _live(db, HandAttribution) if a.hand_id == hand]) == len(lines)


def test_one_missing_line_writes_nothing(db, client):
    lines, hand = _lines(db), _hand(client)
    r = client.post("/api/hands/attributions/many", json={"hand_id": hand, "segment_ids": [lines[0].id, "nope"]})
    assert r.status_code == 404
    assert [a for a in _live(db, HandAttribution) if a.hand_id == hand] == []


def test_unattribute_many_withdraws_by_attribution_id_and_undoes(db, client):
    lines, hand = _lines(db), _hand(client)
    ids = client.post("/api/hands/attributions/many", json={"hand_id": hand, "segment_ids": [s.id for s in lines]}).json()["result"]["attribution_ids"]
    body = client.post("/api/hands/attributions/withdraw-many", json={"attribution_ids": ids}).json()
    assert [a for a in _live(db, HandAttribution) if a.hand_id == hand] == []
    client.post(f"/api/actions/audit/{body['audit_id']}/undo")
    assert len([a for a in _live(db, HandAttribution) if a.hand_id == hand]) == len(lines)


def test_rights_set_on_many_lines_is_one_audit_row_and_one_undo(db, client):
    lines = _lines(db)
    r = client.post("/api/rights/many", json={"targets": [{"kind": "segment", "id": s.id} for s in lines], "holders": ["the archive"]})
    assert r.status_code == 200, r.text
    assert len(_live(db, RightsRecord)) == len(lines)
    assert client.post(f"/api/actions/audit/{r.json()['audit_id']}/undo").status_code == 200
    assert _live(db, RightsRecord) == []


def test_rights_on_many_refuses_all_when_one_target_is_missing(db, client):
    lines = _lines(db)
    r = client.post("/api/rights/many", json={"targets": [{"kind": "segment", "id": lines[0].id}, {"kind": "segment", "id": "nope"}]})
    assert r.status_code >= 400
    assert _live(db, RightsRecord) == []


def test_the_same_target_twice_is_refused(db, client):
    line = _lines(db)[0]
    r = client.post("/api/rights/many", json={"targets": [{"kind": "segment", "id": line.id}] * 2})
    assert r.status_code == 422 and _live(db, RightsRecord) == []


def test_certainty_set_on_many_lines_is_one_step_and_undoes(db, client):
    lines = _lines(db)
    before = len(_live(db, EditorialFact))  # the file brought its own facts
    r = client.post("/api/editorial/many", json={"segment_ids": [s.id for s in lines], "kind": "unclear", "certainty": 0.5})
    assert r.status_code == 200, r.text
    assert len(_live(db, EditorialFact)) == before + len(lines)
    assert client.post(f"/api/actions/audit/{r.json()['audit_id']}/undo").status_code == 200
    assert len(_live(db, EditorialFact)) == before


def test_resolve_many_reads_a_selection_in_one_request_and_says_what_is_mixed(db, client):
    lines = _lines(db)
    hand = _hand(client)
    client.post("/api/hands/attributions", json={"hand_id": hand, "segment_id": lines[0].id})
    r = client.post("/api/source-settings/resolve-many", json={"segment_ids": [s.id for s in lines]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [i["segment_id"] for i in body["items"]] == [s.id for s in lines], body["items"]
    assert body["withheld"] == 0
    assert hand in body["items"][0]["hand_ids"] and hand not in body["items"][1]["hand_ids"]  # the file brings hands of its own
    assert body["mixed"]["hands"] is True and body["mixed"]["restricted"] is False
    assert {s["key"] for s in body["items"][0]["settings"]} == {"language", "script", "direction", "encoding"}


def test_resolve_many_404s_a_missing_line(db, client):
    assert client.post("/api/source-settings/resolve-many", json={"segment_ids": ["nope"]}).status_code == 404
