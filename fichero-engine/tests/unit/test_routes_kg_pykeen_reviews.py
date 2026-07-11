from fichero.knowledge_models import KnowledgePredictionReview


def test_prediction_review_persists_and_transitions(client, db):
    created = client.post(
        "/api/kg/pykeen/reviews",
        json={
            "source_entity_id": "source",
            "relation": "related_to",
            "target_entity_id": "target",
            "score": 0.9,
        },
    )
    assert created.status_code == 200
    review_id = created.json()["id"]

    decided = client.patch(
        f"/api/kg/pykeen/reviews/{review_id}",
        json={"state": "accepted", "resulting_claim_id": "claim-1"},
    )
    assert decided.status_code == 200
    assert decided.json()["state"] == "accepted"
    assert db.get(KnowledgePredictionReview, review_id).resulting_claim_id == "claim-1"
