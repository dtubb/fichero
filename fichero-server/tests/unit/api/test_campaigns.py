"""Campaigns of writing (slice 14, #4935; `source.campaign.*`), on the real imported Syriac page,
through `POST /api/actions/invoke` and the campaigns reads -- the calls the app and the command line
make. And access control: a campaign, a membership and a reading's campaigns belong to their document.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models import ContentRepresentation
from fichero_server.models.campaigns import Campaign
from tests.unit.api.test_page_text_follows_the_file import SYRIAC, _import
from tests.unit.api.test_segments_multiuser_access import (  # noqa: F401  (fixtures)
    _grant_role,
    _make_doc,
    _make_pass,
    _make_segment,
    _override,
    multiuser_client,
    users,
)


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _invoke(client, name, params):
    return client.post("/api/actions/invoke", json={"name": name, "params": params})


def _page(db, client):
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    lines = sorted((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
                   key=lambda s: s["anchor"]["rect"])
    return doc_id, real["id"], lines


def _campaign_of(client, segment_id):
    campaign = _ok(client.get(f"/api/campaigns/segment/{segment_id}"))["campaign"]
    return campaign["name"] if campaign else None


def test_campaigns_are_ordered_and_a_segment_belongs_to_one_moves_and_undoes(db, client):
    doc_id, _pass, lines = _page(db, client)
    main = _ok(_invoke(client, "campaign.create", {"document_id": doc_id, "name": "main ink", "sequence": 1}))
    vowels = _ok(_invoke(client, "campaign.create", {"document_id": doc_id, "name": "later vowels", "sequence": 2,
                                                     "date": "s. XII"}))
    assert [c["name"] for c in _ok(client.get(f"/api/campaigns/document/{doc_id}"))["items"]] == ["main ink", "later vowels"]

    first = lines[0]["id"]
    _ok(_invoke(client, "campaign.assign", {"campaign_id": main["result"]["campaign_id"], "segment_ids": [first]}))
    assert _campaign_of(client, first) == "main ink"
    moved = _ok(_invoke(client, "campaign.assign", {"campaign_id": vowels["result"]["campaign_id"], "segment_ids": [first]}))
    assert _campaign_of(client, first) == "later vowels"          # ONE campaign per segment
    undone = _ok(client.post(f"/api/actions/audit/{moved['audit_id']}/undo"))
    assert _campaign_of(client, first) == "main ink"              # ⌘Z puts it back where it was
    _ok(client.post(f"/api/actions/audit/{undone['audit_id']}/undo"))
    assert _campaign_of(client, first) == "later vowels"          # ⇧⌘Z


def test_a_reading_says_which_campaigns_it_takes_in_and_undo_restores_the_earlier_answer(db, client):
    doc_id, _pass, lines = _page(db, client)
    main = _ok(_invoke(client, "campaign.create", {"document_id": doc_id, "name": "consonants"}))["result"]["campaign_id"]
    vowels = _ok(_invoke(client, "campaign.create", {"document_id": doc_id, "name": "vowels", "sequence": 2}))["result"]["campaign_id"]
    [reading] = _ok(client.get(f"/api/segments/{lines[0]['id']}/readings"))["items"]
    both = _ok(_invoke(client, "reading.take_in", {"representation_id": reading["id"], "campaign_ids": [main, vowels]}))
    assert _ok(client.get(f"/api/campaigns/reading/{reading['id']}"))["campaign_ids"] == [main, vowels]
    _ok(client.post(f"/api/actions/audit/{both['audit_id']}/undo"))
    assert _ok(client.get(f"/api/campaigns/reading/{reading['id']}"))["campaign_ids"] == []


def test_a_segment_of_another_source_and_a_withdrawn_campaign_are_refused(db, client):
    doc_id, _pass, lines = _page(db, client)
    other_id, _p, _l = _page(db, client)
    campaign = _ok(_invoke(client, "campaign.create", {"document_id": other_id, "name": "elsewhere"}))["result"]["campaign_id"]
    assert _invoke(client, "campaign.assign", {"campaign_id": campaign, "segment_ids": [lines[0]["id"]]}).status_code == 422
    _ok(_invoke(client, "campaign.withdraw", {"campaign_id": campaign}))
    assert _invoke(client, "campaign.assign", {"campaign_id": campaign, "segment_ids": [lines[0]["id"]]}).status_code == 404


def test_a_person_denied_the_page_cannot_touch_its_campaigns_or_its_readings_campaigns(multiuser_client, app_db, users, db):
    client, login, library_path = multiuser_client
    _grant_role(app_db, users.editor, library_path, "editor")
    denied = _make_doc(db, "denied.jpg")
    allowed = _make_doc(db, "allowed.jpg")
    _override(app_db, users.editor, library_path, denied.id, "deny")
    ids = {}
    for doc in (denied, allowed):
        seg = _make_segment(db, document_id=doc.id, pass_id=_make_pass(db, doc.id).id, rect=[0.1, 0.1, 0.2, 0.05])
        campaign = Campaign(document_id=doc.id, name="main")
        reading = ContentRepresentation(document_id=doc.id, segment_id=seg.id, kind="transcription", content="x",
                                        provenance_kind="human", source_anchor={"document_id": doc.id, "segment_id": seg.id})
        db.save(campaign)
        db.save(reading)
        ids[doc.id] = (campaign.id, reading.id)
    for doc, expected in ((denied, 403), (allowed, 200)):
        campaign_id, reading_id = ids[doc.id]
        took = client.post("/api/actions/invoke", headers=login("editor"), json={
            "name": "reading.take_in", "params": {"representation_id": reading_id, "campaign_ids": [campaign_id]}})
        assert took.status_code == expected, (doc.name, took.text)
        withdrew = client.post("/api/actions/invoke", headers=login("editor"), json={
            "name": "campaign.withdraw", "params": {"campaign_id": campaign_id}})
        assert withdrew.status_code == expected, (doc.name, withdrew.text)
