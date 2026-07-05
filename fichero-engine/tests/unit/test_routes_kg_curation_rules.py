"""Tests for persistent KG curation-rule routes."""

from fichero.actions.registry import ActionContext, registry
from fichero.knowledge_models import ClaimSuppressionRule, EntityResolutionRule
from fichero.models import ActionAudit

LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


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

    def test_entity_rule_routes_write_action_audit_and_emit(
        self, client, db, monkeypatch
    ):
        calls: list[tuple] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )

        create = client.post(
            "/api/kg/curation-rules/entity-rules",
            json={
                "rule_type": "merge_into",
                "match_canonical_name": "J. Davidson",
                "target_canonical_name": "John Davidson",
                "reason": "same person",
            },
        )

        assert create.status_code == 200
        created_id = create.json()["id"]
        create_audits = [
            row for row in db.all(ActionAudit) if row.action_name == "kg.entity_rule.create"
        ]
        assert len(create_audits) == 1
        assert create_audits[0].target_ids == [created_id]
        assert calls[-1][1]["type"] == "entity.updated"

        delete = client.request(
            "DELETE",
            "/api/kg/curation-rules/entity-rules",
            json={"rule_id": created_id},
        )

        assert delete.status_code == 200
        delete_audits = [
            row for row in db.all(ActionAudit) if row.action_name == "kg.entity_rule.delete"
        ]
        assert len(delete_audits) == 1
        assert delete_audits[0].target_ids == [created_id]
        assert calls[-1][1]["type"] == "entity.updated"

    def test_entity_rule_create_undo_then_redo(self, db):
        reg = registry
        params = {
            "rule_type": "merge_into",
            "match_canonical_name": "J. Davidson",
            "target_canonical_name": "John Davidson",
            "reason": "same person",
        }

        created = reg.invoke(db, "kg.entity_rule.create", params, _ctx())
        created_id = created.result["id"]

        create_action = reg.get("kg.entity_rule.create")
        assert create_action.undoable is True
        assert db.get(EntityResolutionRule, created_id) is not None

        inv = create_action.invert(created.result, created.result, _ctx())
        assert inv is not None
        inv_name, inv_params = inv
        assert inv_name == "kg.entity_rule.delete"
        reg.invoke(db, inv_name, inv_params, _ctx())
        assert db.get(EntityResolutionRule, created_id) is None

        delete_action = reg.get(inv_name)
        assert delete_action.undoable is False


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

    def test_claim_rule_routes_write_action_audit_and_emit(
        self, client, db, monkeypatch
    ):
        calls: list[tuple] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )

        create = client.post(
            "/api/kg/curation-rules/claim-rules",
            json={
                "action": "prune",
                "match_predicate_verb": "is",
                "reason": "trivial copula",
            },
        )

        assert create.status_code == 200
        created_id = create.json()["id"]
        create_audits = [
            row for row in db.all(ActionAudit) if row.action_name == "kg.claim_rule.create"
        ]
        assert len(create_audits) == 1
        assert create_audits[0].target_ids == [created_id]
        assert calls[-1][1]["type"] == "claim.updated"

        delete = client.request(
            "DELETE",
            "/api/kg/curation-rules/claim-rules",
            json={"rule_id": created_id},
        )

        assert delete.status_code == 200
        delete_audits = [
            row for row in db.all(ActionAudit) if row.action_name == "kg.claim_rule.delete"
        ]
        assert len(delete_audits) == 1
        assert delete_audits[0].target_ids == [created_id]
        assert calls[-1][1]["type"] == "claim.updated"
