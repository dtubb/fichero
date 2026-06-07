"""Tests for persistent KG curation-rule routes."""

from fichero.knowledge_models import ClaimSuppressionRule, EntityResolutionRule


class TestEntityCurationRules:
    def test_create_list_delete_entity_rule(self, client, db):
        create = client.post(
            "/api/kg/curation-rules/entity-rules",
            json={
                "rule_type": "merge_into",
                "match_canonical_name": "J. Davidson",
                "match_entity_type": "person",
                "target_canonical_name": "John Davidson",
                "target_entity_type": "person",
                "reason": "same person",
                "created_by": "tester",
            },
        )
        assert create.status_code == 200
        created = create.json()
        assert created["rule_type"] == "merge_into"

        listed = client.get("/api/kg/curation-rules/entity-rules")
        assert listed.status_code == 200
        assert listed.json()["count"] == 1
        assert listed.json()["items"][0]["id"] == created["id"]

        delete = client.request(
            "DELETE",
            "/api/kg/curation-rules/entity-rules",
            json={"rule_id": created["id"]},
        )
        assert delete.status_code == 200
        assert delete.json()["deleted_rule_id"] == created["id"]
        assert db.get(EntityResolutionRule, created["id"]) is None

    def test_batch_create_entity_rules(self, client):
        batch = client.post(
            "/api/kg/curation-rules/entity-rules/batch",
            json={
                "items": [
                    {
                        "rule_type": "alias",
                        "match_canonical_name": "Quito",
                        "reason": "keep alias",
                    },
                    {
                        "rule_type": "suppress",
                        "match_canonical_name": "Unknown Person",
                        "reason": "noise",
                    },
                ]
            },
        )
        assert batch.status_code == 200
        payload = batch.json()
        assert payload["count"] == 2
        assert {item["rule_type"] for item in payload["items"]} == {"alias", "suppress"}


class TestClaimCurationRules:
    def test_create_list_delete_claim_rule(self, client, db):
        create = client.post(
            "/api/kg/curation-rules/claim-rules",
            json={
                "action": "demote",
                "match_predicate_verb": "is",
                "match_subject_name": "Andagoya",
                "match_object_phrase": "a place",
                "suppress_is_a_copulas": True,
                "reason": "trivial copula",
                "created_by": "tester",
            },
        )
        assert create.status_code == 200
        created = create.json()
        assert created["action"] == "demote"

        listed = client.get("/api/kg/curation-rules/claim-rules")
        assert listed.status_code == 200
        assert listed.json()["count"] == 1
        assert listed.json()["items"][0]["id"] == created["id"]

        delete = client.request(
            "DELETE",
            "/api/kg/curation-rules/claim-rules",
            json={"rule_id": created["id"]},
        )
        assert delete.status_code == 200
        assert delete.json()["deleted_rule_id"] == created["id"]
        assert db.get(ClaimSuppressionRule, created["id"]) is None

    def test_batch_create_claim_rules(self, client):
        batch = client.post(
            "/api/kg/curation-rules/claim-rules/batch",
            json={
                "items": [
                    {
                        "action": "disable",
                        "match_predicate_verb": "said",
                        "reason": "known bad extraction",
                    },
                    {
                        "action": "prune",
                        "match_subject_name": "Noise",
                        "reason": "discard",
                    },
                ]
            },
        )
        assert batch.status_code == 200
        payload = batch.json()
        assert payload["count"] == 2
        assert {item["action"] for item in payload["items"]} == {"disable", "prune"}
