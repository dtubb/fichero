"""Hands: who wrote the ink, as project records, and rival judgements of it (slice 14, #4935).

`source.hand.record`, `source.hand.attributed`, `source.hand.not-provenance`. The segments are real:
two DDbDP papyri (CC BY 3.0, `fixtures/corpus/CORPUS.md`) imported through the library, each with
more than one hand in the file. What breaks without these: a second scholar's judgement silently
replacing the first; "everything in hand B" unanswerable across sources; the hand confused with who
made the record.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import Segment
from fichero_server.models.hands import HandAttribution
from tests.unit.api.test_page_text_follows_the_file import _import

CORPUS = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus"
ZENON = CORPUS / "ddbdp_greek-papyrus_p.cair.zen.4.59742.tei.xml"
FLOR = CORPUS / "ddbdp_greek-papyrus_p.flor.2.133.tei.xml"
ANNA = ActionContext(actor="anna", library_path=None, is_bootstrap=True)
BEN = ActionContext(actor="ben", library_path=None, is_bootstrap=True)


def _lines(db, doc_id: str) -> list[Segment]:
    return sorted((s for s in db.all(Segment) if s.document_id == doc_id and s.kind == "line"),
                  key=lambda s: s.metadata["file_position"])


def _hand(client, label: str, **extra) -> str:
    response = client.post("/api/hands", json={"label": label, **extra})
    assert response.status_code == 200, response.text
    return response.json()["result"]["hand_id"]


def test_a_hand_is_a_project_record_shared_across_sources(db, client):
    """"Everything in hand B" is one question, whichever papyrus the lines are on."""
    zenon, flor = _lines(db, _import(db, ZENON)), _lines(db, _import(db, FLOR))
    hand_b = _hand(client, "hand B", date="s. III a.C.", style="documentary cursive")
    for line in (zenon[0], flor[2]):
        r = client.post("/api/hands/attributions", json={"hand_id": hand_b, "segment_id": line.id})
        assert r.status_code == 200, r.text
    everything = client.get(f"/api/hands/{hand_b}/attributions").json()["items"]
    assert {a["segment_id"] for a in everything} == {zenon[0].id, flor[2].id}
    assert [h["label"] for h in client.get("/api/hands").json()["items"]] == ["hand B"]


def test_rival_attributions_stand_side_by_side(db, client):
    """Two scholars, two hands, one line: neither replaces the other, and each keeps its author."""
    line = _lines(db, _import(db, ZENON))[0]
    m1 = registry.invoke(db, "hand.create", {"label": "m1"}, ANNA).result["hand_id"]
    m2 = registry.invoke(db, "hand.create", {"label": "m2"}, ANNA).result["hand_id"]
    registry.invoke(db, "hand.attribute", {"hand_id": m2, "segment_id": line.id, "certainty": 0.8}, ANNA)
    registry.invoke(db, "hand.attribute", {"hand_id": m1, "segment_id": line.id, "certainty": 0.4}, BEN)
    items = [(a["hand_id"], a["created_by"], a["certainty"])
             for a in client.get(f"/api/hands/segment/{line.id}").json()["items"]]
    assert items == [(m2, "anna", 0.8), (m1, "ben", 0.4)]


def test_withdrawing_one_judgement_leaves_the_rival(db, client):
    line = _lines(db, _import(db, ZENON))[0]
    m1 = _hand(client, "m1")
    m2 = _hand(client, "m2")
    first = registry.invoke(db, "hand.attribute", {"hand_id": m1, "segment_id": line.id}, ANNA).result["attribution_id"]
    registry.invoke(db, "hand.attribute", {"hand_id": m2, "segment_id": line.id}, BEN)
    assert client.post(f"/api/hands/attributions/{first}/withdraw").status_code == 200
    assert [a["hand_id"] for a in client.get(f"/api/hands/segment/{line.id}").json()["items"]] == [m2]


def test_an_attribution_undoes_through_the_audit_trail(db, client):
    line = _lines(db, _import(db, ZENON))[0]
    m1 = _hand(client, "m1")
    made = client.post("/api/hands/attributions", json={"hand_id": m1, "segment_id": line.id}).json()
    assert client.post(f"/api/actions/audit/{made['audit_id']}/undo").status_code == 200
    assert client.get(f"/api/hands/segment/{line.id}").json()["items"] == []


def test_the_hand_is_not_who_made_the_record(db):
    """`source.hand.not-provenance`: hand m2 wrote the ink; anna made the judgement. Two facts."""
    line = _lines(db, _import(db, ZENON))[0]
    m2 = registry.invoke(db, "hand.create", {"label": "m2", "scribe": "Zenon's secretary"}, ANNA).result["hand_id"]
    attribution_id = registry.invoke(db, "hand.attribute", {"hand_id": m2, "segment_id": line.id}, ANNA).result["attribution_id"]
    attribution = db.get(HandAttribution, attribution_id)
    assert attribution.hand_id == m2 and attribution.created_by == "anna"
    assert attribution.provenance_kind.value != "unknown"


def test_a_withdrawn_hand_keeps_its_attributions(db, client):
    """Tidying the list must not lose a scholar's judgement: the attribution still names the hand."""
    line = _lines(db, _import(db, ZENON))[0]
    m3 = _hand(client, "m3")
    client.post("/api/hands/attributions", json={"hand_id": m3, "segment_id": line.id})
    assert client.post(f"/api/hands/{m3}/withdraw").status_code == 200
    assert client.get("/api/hands").json()["items"] == []
    assert [a["hand_id"] for a in client.get(f"/api/hands/segment/{line.id}").json()["items"]] == [m3]


def test_a_new_attribution_needs_a_live_hand_and_a_live_segment(db, client):
    line = _lines(db, _import(db, ZENON))[0]
    gone = _hand(client, "gone")
    client.post(f"/api/hands/{gone}/withdraw")
    assert client.post("/api/hands/attributions", json={"hand_id": gone, "segment_id": line.id}).status_code == 404
    live = _hand(client, "live")
    assert client.post("/api/hands/attributions", json={"hand_id": live, "segment_id": "0" * 32}).status_code == 404


def test_certainty_is_a_fraction_and_notes_are_capped(db):
    """Notes go into the audit chain, which nothing can purge: capped, like a sign's."""
    line = _lines(db, _import(db, ZENON))[0]
    m1 = registry.invoke(db, "hand.create", {"label": "m1"}, ANNA).result["hand_id"]
    with pytest.raises(ValidationError):
        registry.invoke(db, "hand.attribute", {"hand_id": m1, "segment_id": line.id, "certainty": 1.5}, ANNA)
    with pytest.raises(ValidationError):
        registry.invoke(db, "hand.create", {"label": "m9", "notes": "x" * 501}, ANNA)
