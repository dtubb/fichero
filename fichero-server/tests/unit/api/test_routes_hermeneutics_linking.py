"""Hermeneutics route link-integrity tests (#501)."""

from fichero_server.models.hermeneutics import FrameworkType
from fichero_server.models.knowledge import KnowledgeClaim


class TestHermeneuticsInterpretationClaimLinking:
    def test_create_interpretation_rejects_missing_claim(self, client):
        framework = client.post(
            "/api/hermeneutics/frameworks",
            json={
                "name": "Marxist reading",
                "framework_type": FrameworkType.theoretical.value,
                "description": "Material conditions shape ideas.",
            },
        )
        assert framework.status_code == 200
        framework_id = framework.json()["id"]

        response = client.post(
            "/api/hermeneutics/interpretations",
            json={
                "framework_id": framework_id,
                "claim_id": "claim-does-not-exist",
                "interpretation_text": "Class conflict lens",
                "act": "applying",
            },
        )
        assert response.status_code == 404
        assert "Claim not found" in response.json()["detail"]

    def test_create_interpretation_accepts_existing_claim(self, client, db):
        claim = KnowledgeClaim(
            id="claim-hermeneutics-1",
            text="Workers organized for better wages.",
            source_document_id="doc-1",
            source_page_label="12",
            entity_ids=[],
            subject_canonical="Workers",
            predicate_verb="organized",
            object_phrase="for better wages",
        )
        db.save(claim)

        framework = client.post(
            "/api/hermeneutics/frameworks",
            json={
                "name": "Marxist reading",
                "framework_type": FrameworkType.theoretical.value,
                "description": "Material conditions shape ideas.",
            },
        )
        assert framework.status_code == 200
        framework_id = framework.json()["id"]

        response = client.post(
            "/api/hermeneutics/interpretations",
            json={
                "framework_id": framework_id,
                "claim_id": claim.id,
                "interpretation_text": "The claim encodes labor-capital tension.",
                "act": "applying",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["claim_id"] == claim.id
        assert payload["framework_id"] == framework_id
