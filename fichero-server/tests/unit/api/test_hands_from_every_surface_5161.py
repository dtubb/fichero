"""The calls every surface makes to assign a hand (#5161; `source.hand.record`, `source.hand.attributed`,
`source.hand.not-provenance`): the row menu, the menu bar, the shortcut and the Inspector all send the same four calls
on a selection of an imported page's lines -- read each line's attributions, attribute the selection (one line:
`hand.attribute`, several: `hand.attribute_many`), withdraw the selection's attributions (`hand.unattribute_many`) --
and each is one undo. A real DDbDP papyrus whose file already names hands, so the selection is mixed."""
from __future__ import annotations

from pathlib import Path

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models import Segment
from tests.unit.api.test_page_text_follows_the_file import _import

ZENON = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus" / "ddbdp_greek-papyrus_p.cair.zen.4.59742.tei.xml"


def _live(client, segment_id: str) -> list[dict]:
    items = client.get(f"/api/hands/segment/{segment_id}").json()["items"]
    return [a for a in items if a.get("withdrawn_at") is None]


def _hand_ids(client, segment_id: str) -> set[str]:
    return {a["hand_id"] for a in _live(client, segment_id)}


def test_a_mixed_selection_takes_a_hand_and_gives_every_judgement_back_in_one_undo_each(db, client):
    doc = _import(db, ZENON)
    lines = sorted((s for s in db.all(Segment) if s.document_id == doc and s.kind == "line"),
                   key=lambda s: s.metadata["file_position"])
    selection = [lines[0], lines[2]]  # the file puts the first on m2 and the third on m1: a Mixed selection
    before = [_hand_ids(client, s.id) for s in selection]
    assert before[0] != before[1] and all(len(h) == 1 for h in before)

    # New Hand…, then attribute the selection to it (one create, one attribute_many)
    new_hand = client.post("/api/hands", json={"label": "hand B"}).json()["result"]["hand_id"]
    attributed = client.post("/api/hands/attributions/many",
                             json={"hand_id": new_hand, "segment_ids": [s.id for s in selection]}).json()
    assert [_hand_ids(client, s.id) for s in selection] == [h | {new_hand} for h in before]

    # Remove Hand: every live judgement on the selection, the file's too, withdrawn in one step
    live_ids = [a["id"] for s in selection for a in _live(client, s.id)]
    removed = client.post("/api/hands/attributions/withdraw-many", json={"attribution_ids": live_ids}).json()
    assert [_hand_ids(client, s.id) for s in selection] == [set(), set()]

    assert client.post(f"/api/actions/audit/{removed['audit_id']}/undo").status_code == 200
    assert [_hand_ids(client, s.id) for s in selection] == [h | {new_hand} for h in before]
    assert client.post(f"/api/actions/audit/{attributed['audit_id']}/undo").status_code == 200
    assert [_hand_ids(client, s.id) for s in selection] == before


def test_one_line_takes_a_hand_through_the_single_route(db, client):
    doc = _import(db, ZENON)
    line = next(s for s in db.all(Segment) if s.document_id == doc and s.kind == "line")
    hand = client.post("/api/hands", json={"label": "hand B"}).json()["result"]["hand_id"]
    made = client.post("/api/hands/attributions", json={"hand_id": hand, "segment_id": line.id}).json()
    assert hand in _hand_ids(client, line.id)
    attribution = next(a for a in _live(client, line.id) if a["hand_id"] == hand)
    assert attribution["source"] is None  # a person's judgement, not the file's
    assert client.post(f"/api/actions/audit/{made['audit_id']}/undo").status_code == 200
    assert hand not in _hand_ids(client, line.id)
