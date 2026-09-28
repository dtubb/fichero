"""Letterforms: character > allograph > a scribe's form > this mark, with components and features
(slice 14, #4935; `source.letterform.*`). On the real imported Syriac page, through the calls the app
and the command line make (`POST /api/actions/invoke`, the letterforms reads).
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models.letterforms import LetterformDescription
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

ALAPH = "ܐ"


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _invoke(client, name, params):
    return client.post("/api/actions/invoke", json={"name": name, "params": params})


def _a_mark(db, client) -> dict:
    """A character segment -- one letter's box -- inside the imported page's first line."""
    doc_id = _import(db, SYRIAC)
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    line = min((s for s in body["segments"] if s["pass_id"] == real["id"] and s["kind"] == "line"),
               key=lambda s: s["anchor"]["rect"])
    x, y, w, h = line["anchor"]["rect"]
    created = _ok(_invoke(client, "segment.create", {
        "document_id": doc_id, "pass_id": real["id"], "kind": "character",
        "anchor": {"document_id": doc_id, "rect": [x, y, w / 20, h]},
    }))
    return {"doc_id": doc_id, "segment_id": created["result"]["segment_ids"][0]}


def test_a_mark_names_its_chain_and_features_and_is_gathered_across_hands(db, client):
    mark = _a_mark(db, client)
    allograph = _ok(_invoke(client, "allograph.create", {"character": ALAPH, "name": "Estrangela alaph"}))
    hand = _ok(_invoke(client, "hand.create", {"label": "hand B"}))
    described = _ok(_invoke(client, "letterform.describe", {
        "segment_id": mark["segment_id"], "character": ALAPH,
        "allograph_id": allograph["result"]["allograph_id"], "hand_id": hand["result"]["hand_id"],
        "features": [{"component": "stem", "feature": "wedged"}, {"component": "foot", "feature": "curved"}],
    }))
    [description] = _ok(client.get(f"/api/letterforms/segment/{mark['segment_id']}"))["items"]
    assert description["character"] == ALAPH
    assert description["allograph_id"] == allograph["result"]["allograph_id"]
    assert description["hand_id"] == hand["result"]["hand_id"]
    assert {(f["component"], f["feature"]) for f in description["features"]} == {("stem", "wedged"), ("foot", "curved")}

    # Gathered to compare, by character, by allograph, by hand (`source.letterform.compare`).
    for query in ({"character": ALAPH}, {"allograph_id": allograph["result"]["allograph_id"]},
                  {"hand_id": hand["result"]["hand_id"]}):
        assert [d["id"] for d in _ok(client.get("/api/letterforms", params=query))["items"]] == [description["id"]]
    # The open lists are what the project has used.
    assert {(f["component"], f["feature"], f["count"]) for f in _ok(client.get("/api/letterforms/features"))["items"]} \
        == {("stem", "wedged", 1), ("foot", "curved", 1)}
    assert described["audit_id"]


def test_describing_a_mark_again_supersedes_and_undo_and_redo_swap_them_back(db, client):
    mark = _a_mark(db, client)
    first = _ok(_invoke(client, "letterform.describe", {"segment_id": mark["segment_id"], "character": ALAPH,
                                                        "features": [{"component": "stem", "feature": "wedged"}]}))
    second = _ok(_invoke(client, "letterform.describe", {"segment_id": mark["segment_id"], "character": ALAPH,
                                                         "features": [{"component": "stem", "feature": "straight"}]}))

    def live():
        return [d["features"][0]["feature"] for d in _ok(client.get(f"/api/letterforms/segment/{mark['segment_id']}"))["items"]]

    assert live() == ["straight"]                                   # one live description per mark
    undone = _ok(client.post(f"/api/actions/audit/{second['audit_id']}/undo"))
    assert live() == ["wedged"]                                     # ⌘Z brings the earlier one back
    _ok(client.post(f"/api/actions/audit/{undone['audit_id']}/undo"))
    assert live() == ["straight"]                                   # ⇧⌘Z
    assert first["audit_id"]


def test_an_allograph_of_another_character_and_an_unnamed_gather_are_refused(db, client):
    mark = _a_mark(db, client)
    beth = _ok(_invoke(client, "allograph.create", {"character": "ܒ", "name": "Estrangela beth"}))
    wrong = _invoke(client, "letterform.describe", {"segment_id": mark["segment_id"], "character": ALAPH,
                                                    "allograph_id": beth["result"]["allograph_id"]})
    assert wrong.status_code == 422, wrong.text
    assert client.get("/api/letterforms").status_code == 422


def test_a_person_denied_the_page_cannot_withdraw_its_letterform(multiuser_client, app_db, users, db):
    client, login, library_path = multiuser_client
    _grant_role(app_db, users.editor, library_path, "editor")
    denied = _make_doc(db, "denied.jpg")
    allowed = _make_doc(db, "allowed.jpg")
    _override(app_db, users.editor, library_path, denied.id, "deny")
    ids = {}
    for doc in (denied, allowed):
        seg = _make_segment(db, document_id=doc.id, pass_id=_make_pass(db, doc.id).id, rect=[0.1, 0.1, 0.02, 0.05])
        description = LetterformDescription(segment_id=seg.id, character=ALAPH)
        db.save(description)
        ids[doc.id] = description.id
    for doc, expected in ((denied, 403), (allowed, 200)):
        response = client.post("/api/actions/invoke", headers=login("editor"), json={
            "name": "letterform.withdraw", "params": {"description_id": ids[doc.id]}})
        assert response.status_code == expected, (doc.name, response.text)
