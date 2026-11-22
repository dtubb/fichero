"""The readable route carries each sentence's clauses and segments (#6836).

spec: kg-paragraph-realisation (`kg.para.clause-carries-claim-ids`, `kg.para.every-character-has-an-origin`)
"""
from __future__ import annotations

from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity


def test_the_route_returns_clauses_and_segments_that_slice_the_paragraph(client, db):
    with db.defer_embeddings():
        page = KnowledgeEntity(canonical_name="Inés Valcárcel")
        db.save(page)
        for i, obj in enumerate(("una mula", "dos bueyes")):
            db.save(KnowledgeClaim(
                text=f"Inés Valcárcel vendió {obj}", svo_subject="Inés Valcárcel", svo_verb="vendió",
                svo_object=obj, subject_entity_id=page.id, entity_ids=[page.id], source_languages=["es"],
                time_start=f"173{i}-01-01"))
    body = client.get(f"/api/kg/entities/{page.id}/readable").json()
    paragraph = body["paragraph"]
    (sentence,) = body["sentences"]
    assert [paragraph[c["start"]:c["end"]] for c in sentence["clauses"]] == ["una mula", "dos bueyes"]
    assert {c["state"] for c in sentence["clauses"]} == {"proposed"}
    assert [paragraph[g["start"]:g["end"]] for g in sentence["segments"]] == [
        "Inés Valcárcel", "vendió", "una mula", "y", "dos bueyes", "."]
    assert [g["origin"] for g in sentence["segments"]][3:5] == ["table:es:and", sentence["segments"][4]["origin"]]
