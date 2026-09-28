"""Editorial facts, recorded through the calls the app and the command line make (slice 14, #4935).

`source.sure.editorial-facts`: unclear, lost, restored, supplied, superfluous, deleted and added are
recorded as FACTS with extent, reason and author; `source.sure.brackets-are-drawn`: the read answers
the counting reading with the facts drawn in, never stored in it. On the real imported Syriac page.
Also access control: a fact or a hand attribution belongs to its segment's document, so a person
denied the page cannot withdraw it by naming its id.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models.editorial import EditorialFact
from fichero_server.models.hands import Hand, HandAttribution
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


def _first_line(client, doc_id: str) -> tuple[dict, dict]:
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    line = min((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
               key=lambda s: s["anchor"]["rect"])
    [reading] = client.get(f"/api/segments/{line['id']}/readings").json()["items"]
    return line, reading


def _invoke(client, name: str, params: dict):
    return client.post("/api/actions/invoke", json={"name": name, "params": params})


def test_a_fact_is_recorded_with_its_extent_reason_and_author_and_drawn_not_stored(db, client):
    doc_id = _import(db, SYRIAC)
    line, reading = _first_line(client, doc_id)
    recorded = _invoke(client, "editorial.record", {
        "segment_id": line["id"], "kind": "unclear", "representation_id": reading["id"],
        "char_start": 0, "char_end": 2, "reason": "faded",
    })
    assert recorded.status_code == 200, recorded.text
    answer = client.get(f"/api/editorial/segment/{line['id']}").json()
    [stored] = answer["items"]
    assert stored["kind"] == "unclear" and stored["reason"] == "faded" and stored["created_by"]
    assert answer["drawn_from"] == reading["id"]
    assert answer["drawn"] == reading["content"][0] + "̣" + reading["content"][1] + "̣" + reading["content"][2:]
    # The reading itself is untouched: the sign is drawn, never typed in.
    [again] = client.get(f"/api/segments/{line['id']}/readings").json()["items"]
    assert again["content"] == reading["content"]

    # ⌘Z withdraws it: kept, no longer drawn.
    undone = client.post(f"/api/actions/audit/{recorded.json()['audit_id']}/undo")
    assert undone.status_code == 200, undone.text
    after = client.get(f"/api/editorial/segment/{line['id']}").json()
    assert after["items"] == [] and after["drawn"] == reading["content"]
    assert db.get(EditorialFact, stored["id"]).withdrawn_at is not None


def test_a_lost_stretch_with_no_text_is_recorded_by_its_extent(db, client):
    doc_id = _import(db, SYRIAC)
    line, reading = _first_line(client, doc_id)
    assert _invoke(client, "editorial.record", {
        "segment_id": line["id"], "kind": "lost", "extent_quantity": 4, "extent_unit": "character",
        "reason": "a hole",
    }).status_code == 200
    assert client.get(f"/api/editorial/segment/{line['id']}").json()["drawn"] == reading["content"] + "[.4]"


def test_a_span_is_refused_unless_it_names_a_reading_of_this_segment_and_fits_in_it(db, client):
    doc_id = _import(db, SYRIAC)
    line, reading = _first_line(client, doc_id)
    base = {"segment_id": line["id"], "kind": "restored"}
    assert _invoke(client, "editorial.record", dict(base, char_start=0, char_end=1)).status_code == 422
    assert _invoke(client, "editorial.record", dict(
        base, representation_id=reading["id"], char_start=0, char_end=len(reading["content"]) + 5)).status_code == 422
    assert _invoke(client, "editorial.record", dict(
        base, representation_id="not-a-reading", char_start=0, char_end=1)).status_code == 422
    assert _invoke(client, "editorial.record", dict(base, kind="smudged")).status_code == 422


def test_a_person_denied_the_page_cannot_withdraw_its_fact_or_its_hand_attribution(multiuser_client, app_db, users, db):
    client, login, library_path = multiuser_client
    _grant_role(app_db, users.editor, library_path, "editor")
    denied = _make_doc(db, "denied.jpg")
    allowed = _make_doc(db, "allowed.jpg")
    _override(app_db, users.editor, library_path, denied.id, "deny")
    hand = Hand(label="hand B")
    db.save(hand)
    records = {}
    for doc in (denied, allowed):
        seg = _make_segment(db, document_id=doc.id, pass_id=_make_pass(db, doc.id).id, rect=[0.1, 0.1, 0.2, 0.05])
        fact = EditorialFact(segment_id=seg.id, kind="lost")
        attribution = HandAttribution(hand_id=hand.id, segment_id=seg.id)
        db.save(fact)
        db.save(attribution)
        records[doc.id] = (fact.id, attribution.id)

    for doc, expected in ((denied, 403), (allowed, 200)):
        fact_id, attribution_id = records[doc.id]
        withdrawn = client.post("/api/actions/invoke", headers=login("editor"),
                                json={"name": "editorial.withdraw", "params": {"fact_id": fact_id}})
        assert withdrawn.status_code == expected, (doc.name, withdrawn.text)
        unattributed = client.post("/api/actions/invoke", headers=login("editor"),
                                   json={"name": "hand.unattribute", "params": {"attribution_id": attribution_id}})
        assert unattributed.status_code == expected, (doc.name, unattributed.text)
