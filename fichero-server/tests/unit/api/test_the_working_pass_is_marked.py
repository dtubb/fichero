"""The segment list says which pass is the page's working pass, and why (#5156).

The working pass is the one a page's text and edits come from; a person can choose it
(`pass.choose_working`). The app could not see which one it was, so its canvas ranked passes by its
own rule and nothing showed the choice. Through the calls the app makes: the list route, and
`POST /api/actions/invoke` / the audit undo.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from tests.unit.api.test_page_text_follows_the_file import SYRIAC, _import


def _passes(client, doc_id: str) -> list[dict]:
    return [p for p in client.get(f"/api/segments/document/{doc_id}").json()["passes"] if not p["provisional"]]


def test_exactly_one_pass_is_working_and_a_persons_choice_moves_it_and_undo_moves_it_back(db, client):
    doc_id = _import(db, SYRIAC)
    [imported] = _passes(client, doc_id)
    assert imported["working"] is True and imported["working_basis"]      # the only pass, and why

    second = client.post("/api/actions/invoke", json={"name": "segment.pass_create", "params": {
        "document_id": doc_id, "name": "a second reading of the page"}})
    assert second.status_code == 200, second.text
    second_id = next(p["id"] for p in _passes(client, doc_id) if p["id"] != imported["id"])
    by_rule = {p["id"]: (p["working"], p["working_basis"]) for p in _passes(client, doc_id)}
    assert sum(working for working, _ in by_rule.values()) == 1

    chosen = client.post("/api/actions/invoke", json={"name": "pass.choose_working", "params": {
        "document_id": doc_id, "pass_id": second_id}})
    assert chosen.status_code == 200, chosen.text
    after = {p["id"]: p for p in _passes(client, doc_id)}
    assert after[second_id]["working"] is True and after[second_id]["working_basis"] == "chosen"
    assert after[imported["id"]]["working"] is False and after[imported["id"]]["working_basis"] is None

    # ⌘Z of a page's FIRST choice: there was no earlier choice, so the choice is retired and the
    # project's rule decides again -- exactly as it did before anyone chose (#5156; this undo used to
    # fail with "Action did not yield an inverse to apply").
    undone = client.post(f"/api/actions/audit/{chosen.json()['audit_id']}/undo")
    assert undone.status_code == 200, undone.text
    back = {p["id"]: (p["working"], p["working_basis"]) for p in _passes(client, doc_id)}
    assert back == by_rule
    assert all(basis != "chosen" for _, basis in back.values())

    # ⇧⌘Z (the undo of the undo) chooses it again.
    redone = client.post(f"/api/actions/audit/{undone.json()['audit_id']}/undo")
    assert redone.status_code == 200, redone.text
    again = {p["id"]: p for p in _passes(client, doc_id)}
    assert again[second_id]["working"] is True and again[second_id]["working_basis"] == "chosen"
