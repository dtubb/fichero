"""HTTP route tests for entity merge / split / undo / audit (#1135).

Covers POST /api/kg/entity-curation/merge, /split, /undo/{audit_id}, and
GET /api/kg/entity-curation/audit.  Uses the shared ``client`` + ``db``
fixtures from tests/conftest.py (real in-memory DuckDB database).
"""

from __future__ import annotations

from datetime import datetime

from fichero.models.knowledge import (
    ClaimCurationState,
    EntityCurationState,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    MutationLog,
)
from fichero.models import ActionAudit, DocType, Document


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(db, name: str, entity_type: EntityType = EntityType.person) -> KnowledgeEntity:
    entity = KnowledgeEntity(
        canonical_name=name,
        entity_type=entity_type,
        aliases=[name.lower()],
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.save(entity)
    return entity


def _make_doc(db, name: str = "Source Doc") -> Document:
    doc = Document(name=name, doc_type=DocType.file)
    db.save(doc)
    return doc


def _make_claim(db, doc: Document, entity: KnowledgeEntity, text: str = "A claim.") -> KnowledgeClaim:
    claim = KnowledgeClaim(
        text=text,
        source_document_id=doc.id,
        entity_ids=[entity.id],
        curation_state=ClaimCurationState.unreviewed,
        confidence=0.9,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.save(claim)
    return claim


# ---------------------------------------------------------------------------
# Regression: a merged-away (tombstoned) entity must NOT reappear in the
# entity list the UI shows — otherwise merge "looks like it did nothing"
# even though the DB merge succeeded.  (#1849)
# ---------------------------------------------------------------------------


class TestMergedEntitiesHiddenFromList:
    def test_absorbed_entity_excluded_from_full_list(self, client, db):
        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")
        r = client.post(
            "/api/kg/entity-curation/merge",
            json={
                "absorbing_entity_id": absorber.id,
                "absorbed_entity_ids": [absorbed.id],
            },
        )
        assert r.status_code == 200
        ids = {item["id"] for item in client.get("/api/entities").json()["items"]}
        assert absorber.id in ids
        assert absorbed.id not in ids  # tombstoned entity must be hidden

    def test_absorbed_entity_excluded_from_doc_scoped_list(self, client, db):
        """The document_id union loop must also drop tombstoned entities even
        when their source_document_ids still intersect the requested doc."""
        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")
        doc = _make_doc(db)
        _make_claim(db, doc, absorbed, "Alicia was here.")
        absorbed.source_document_ids = [doc.id]
        db.save(absorbed)
        r = client.post(
            "/api/kg/entity-curation/merge",
            json={
                "absorbing_entity_id": absorber.id,
                "absorbed_entity_ids": [absorbed.id],
            },
        )
        assert r.status_code == 200
        listed = client.get(f"/api/entities?document_id={doc.id}").json()
        ids = {item["id"] for item in listed["items"]}
        assert absorbed.id not in ids

    def test_absorbed_entity_excluded_from_alias_map(self, client, db):
        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")
        r = client.post(
            "/api/kg/entity-curation/merge",
            json={
                "absorbing_entity_id": absorber.id,
                "absorbed_entity_ids": [absorbed.id],
            },
        )
        assert r.status_code == 200
        alias_map = client.get("/api/entities/alias-map").json()
        mapped_ids = {entry["entity_id"] for entry in alias_map["entries"]}
        assert absorbed.id not in mapped_ids  # tombstone must not seed the map


# ---------------------------------------------------------------------------
# POST /api/kg/entity-curation/merge
# ---------------------------------------------------------------------------


class TestMergeEntities:
    def test_merge_basic(self, client, db):
        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")
        r = client.post(
            "/api/kg/entity-curation/merge",
            json={
                "absorbing_entity_id": absorber.id,
                "absorbed_entity_ids": [absorbed.id],
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["operation_type"] == "merge"
        assert body["target_entity_id"] == absorber.id
        assert absorbed.id in body["source_entity_ids"]

    def test_merge_moves_aliases(self, client, db):
        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")
        absorbed.aliases = ["ali", "alicia"]
        db.save(absorbed)
        r = client.post(
            "/api/kg/entity-curation/merge",
            json={
                "absorbing_entity_id": absorber.id,
                "absorbed_entity_ids": [absorbed.id],
            },
        )
        assert r.status_code == 200
        absorber_after = db.get(KnowledgeEntity, absorber.id)
        assert "ali" in absorber_after.aliases
        assert "alicia" in absorber_after.aliases

    def test_merge_repoints_claims(self, client, db):
        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")
        doc = _make_doc(db)
        claim = _make_claim(db, doc, absorbed, "Alicia was here.")
        r = client.post(
            "/api/kg/entity-curation/merge",
            json={
                "absorbing_entity_id": absorber.id,
                "absorbed_entity_ids": [absorbed.id],
            },
        )
        assert r.status_code == 200
        claim_after = db.get(KnowledgeClaim, claim.id)
        assert absorber.id in claim_after.entity_ids
        assert absorbed.id not in claim_after.entity_ids

    def test_merge_repoints_multi_entity_claim(self, client, db):
        """A claim referencing both absorbed A and absorbed B gets a single absorber entry."""
        absorber = _make_entity(db, "Alice")
        absorbed_a = _make_entity(db, "Alicia")
        absorbed_b = _make_entity(db, "Al")
        doc = _make_doc(db)
        claim = KnowledgeClaim(
            text="Both Alicia and Al appear.",
            source_document_id=doc.id,
            entity_ids=[absorbed_a.id, absorbed_b.id],
            curation_state=ClaimCurationState.unreviewed,
            confidence=0.8,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.save(claim)
        r = client.post(
            "/api/kg/entity-curation/merge",
            json={
                "absorbing_entity_id": absorber.id,
                "absorbed_entity_ids": [absorbed_a.id, absorbed_b.id],
            },
        )
        assert r.status_code == 200
        claim_after = db.get(KnowledgeClaim, claim.id)
        assert claim_after.entity_ids == [absorber.id]

    def test_merge_absorber_not_found(self, client):
        r = client.post(
            "/api/kg/entity-curation/merge",
            json={"absorbing_entity_id": "missing", "absorbed_entity_ids": ["also-missing"]},
        )
        assert r.status_code == 404

    def test_merge_absorbed_not_found(self, client, db):
        absorber = _make_entity(db, "Alice")
        r = client.post(
            "/api/kg/entity-curation/merge",
            json={"absorbing_entity_id": absorber.id, "absorbed_entity_ids": ["missing"]},
        )
        assert r.status_code == 404

    def test_merge_already_merged_entity_rejected(self, client, db):
        absorber = _make_entity(db, "Alice")
        intermediate = _make_entity(db, "Alicia")
        target = _make_entity(db, "Al")
        # First merge intermediate → absorber
        client.post(
            "/api/kg/entity-curation/merge",
            json={"absorbing_entity_id": absorber.id, "absorbed_entity_ids": [intermediate.id]},
        )
        # Try to merge the already-merged entity again — should 409
        r = client.post(
            "/api/kg/entity-curation/merge",
            json={"absorbing_entity_id": target.id, "absorbed_entity_ids": [intermediate.id]},
        )
        assert r.status_code == 409

    def test_merge_retry_into_same_absorber_is_idempotent(self, client, db):
        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")
        payload = {
            "absorbing_entity_id": absorber.id,
            "absorbed_entity_ids": [absorbed.id],
        }
        assert client.post("/api/kg/entity-curation/merge", json=payload).status_code == 200
        assert client.post("/api/kg/entity-curation/merge", json=payload).status_code == 200

    def test_merge_with_custom_description(self, client, db):
        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")
        r = client.post(
            "/api/kg/entity-curation/merge",
            json={
                "absorbing_entity_id": absorber.id,
                "absorbed_entity_ids": [absorbed.id],
                "merged_description": "Unified Alice entity",
            },
        )
        assert r.status_code == 200
        absorber_after = db.get(KnowledgeEntity, absorber.id)
        assert absorber_after.description == "Unified Alice entity"

    def test_merge_writes_action_audit_and_emits(self, client, db, monkeypatch):
        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")
        calls: list[tuple] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )

        r = client.post(
            "/api/kg/entity-curation/merge",
            json={
                "absorbing_entity_id": absorber.id,
                "absorbed_entity_ids": [absorbed.id],
            },
        )

        assert r.status_code == 200
        audits = [row for row in db.all(ActionAudit) if row.action_name == "entity.merge"]
        assert len(audits) == 1
        assert audits[0].target_ids == [absorber.id, absorbed.id]
        assert calls[-1][1]["type"] == "entity.merged"
        assert calls[-1][1]["entity_ids"] == [absorber.id, absorbed.id]


class TestBatchEntityCuration:
    def test_batch_updates_entities_and_logs_mutations(self, client, db):
        left = _make_entity(db, "Alice")
        right = _make_entity(db, "Bob")

        r = client.patch(
            "/api/kg/entities/batch-curation",
            json={
                "entity_ids": [left.id, right.id],
                "curation_state": "verified",
            },
        )

        assert r.status_code == 200
        assert r.json() == {
            "updated": 2,
            "entity_ids": [left.id, right.id],
        }
        assert db.get(KnowledgeEntity, left.id).curation_state.value == "verified"
        assert db.get(KnowledgeEntity, right.id).curation_state.value == "verified"

        logs = [m for m in db.all(MutationLog) if m.entity_type == "KnowledgeEntity"]
        assert len(logs) == 2
        assert {m.entity_id for m in logs} == {left.id, right.id}
        for log in logs:
            assert log.operation.value == "update"
            assert log.changed_fields == ["curation_state"]
            assert log.before_state["curation_state"] == "unreviewed"
            assert log.after_state["curation_state"] == "verified"

    def test_batch_skips_unchanged_entities(self, client, db):
        entity = _make_entity(db, "Alice")
        entity.curation_state = EntityCurationState.unreviewed
        db.save(entity)

        r = client.patch(
            "/api/kg/entities/batch-curation",
            json={
                "entity_ids": [entity.id],
                "curation_state": "unreviewed",
            },
        )

        assert r.status_code == 200
        assert r.json() == {"updated": 0, "entity_ids": []}
        assert db.all(MutationLog) == []


# ---------------------------------------------------------------------------
# POST /api/kg/entity-curation/split
# ---------------------------------------------------------------------------


class TestSplitEntity:
    def test_split_unmerges_entity(self, client, db):
        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")
        # First merge
        merge_r = client.post(
            "/api/kg/entity-curation/merge",
            json={"absorbing_entity_id": absorber.id, "absorbed_entity_ids": [absorbed.id]},
        )
        assert merge_r.status_code == 200
        absorbed_after = db.get(KnowledgeEntity, absorbed.id)
        assert absorbed_after.merged_into_id == absorber.id

        # Now split it back
        r = client.post(
            "/api/kg/entity-curation/split",
            json={"primary_entity_id": absorber.id, "split_off_entity_ids": [absorbed.id]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["operation_type"] == "split"
        absorbed_split = db.get(KnowledgeEntity, absorbed.id)
        assert absorbed_split.merged_into_id is None

    def test_split_primary_not_found(self, client):
        r = client.post(
            "/api/kg/entity-curation/split",
            json={"primary_entity_id": "missing", "split_off_entity_ids": []},
        )
        assert r.status_code == 404

    def test_split_moves_aliases(self, client, db):
        absorber = _make_entity(db, "Alice")
        absorber.aliases = ["alice", "moved-alias"]
        db.save(absorber)
        absorbed = _make_entity(db, "Alicia")
        client.post(
            "/api/kg/entity-curation/merge",
            json={"absorbing_entity_id": absorber.id, "absorbed_entity_ids": [absorbed.id]},
        )
        r = client.post(
            "/api/kg/entity-curation/split",
            json={
                "primary_entity_id": absorber.id,
                "split_off_entity_ids": [absorbed.id],
                "aliases_to_move": ["moved-alias"],
            },
        )
        assert r.status_code == 200
        absorber_after = db.get(KnowledgeEntity, absorber.id)
        assert "moved-alias" not in absorber_after.aliases


# ---------------------------------------------------------------------------
# GET /api/kg/entity-curation/audit
# ---------------------------------------------------------------------------


class TestListEntityAudits:
    def test_empty(self, client):
        r = client.get("/api/kg/entity-curation/audit")
        assert r.status_code == 200
        body = r.json()
        assert body["items"] == []
        assert body["count"] == 0

    def test_audit_appears_after_merge(self, client, db):
        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")
        client.post(
            "/api/kg/entity-curation/merge",
            json={"absorbing_entity_id": absorber.id, "absorbed_entity_ids": [absorbed.id]},
        )
        r = client.get("/api/kg/entity-curation/audit")
        assert r.status_code == 200
        assert r.json()["count"] >= 1

    def test_filter_by_entity(self, client, db):
        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")
        other = _make_entity(db, "Bob")
        other2 = _make_entity(db, "Robert")
        client.post(
            "/api/kg/entity-curation/merge",
            json={"absorbing_entity_id": absorber.id, "absorbed_entity_ids": [absorbed.id]},
        )
        client.post(
            "/api/kg/entity-curation/merge",
            json={"absorbing_entity_id": other.id, "absorbed_entity_ids": [other2.id]},
        )
        r = client.get(f"/api/kg/entity-curation/audit?entity_id={absorber.id}")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["target_entity_id"] == absorber.id


class TestUndoEntityOperation:
    def test_undo_writes_action_audit_and_emits(self, client, db, monkeypatch):
        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")
        merge = client.post(
            "/api/kg/entity-curation/merge",
            json={
                "absorbing_entity_id": absorber.id,
                "absorbed_entity_ids": [absorbed.id],
            },
        )
        calls: list[tuple] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )

        r = client.post(f"/api/kg/entity-curation/audit/{merge.json()['id']}/undo")

        assert r.status_code == 200
        audits = [row for row in db.all(ActionAudit) if row.action_name == "entity.unmerge"]
        assert len(audits) == 1
        assert audits[0].target_ids == [absorber.id, absorbed.id]
        assert calls[-1][1]["type"] == "entity.split"
        assert calls[-1][1]["entity_ids"] == [absorber.id, absorbed.id]
