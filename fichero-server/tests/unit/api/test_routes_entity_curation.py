"""HTTP route tests for entity merge / split / undo / audit (#1135).

Covers POST /api/kg/entity-curation/merge, /split, /undo/{audit_id}, and
GET /api/kg/entity-curation/audit.  Uses the shared ``client`` + ``db``
fixtures from tests/conftest.py (real in-memory DuckDB database).
"""

from __future__ import annotations

from datetime import datetime

from fichero_server.models.knowledge import (
    ClaimCurationState,
    EntityCurationState,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    MutationLog,
)
from fichero_server.models import ActionAudit, DocType, Document


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
            "fichero_server.api.change_stream.emit_change",
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
# entity.split (#4831) -- was a bare route, writes an ActionAudit now.
# ---------------------------------------------------------------------------


class TestSplitEntityAction:
    def test_route_now_writes_an_action_audit(self, client, db):
        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")
        client.post(
            "/api/kg/entity-curation/merge",
            json={"absorbing_entity_id": absorber.id, "absorbed_entity_ids": [absorbed.id]},
        )

        r = client.post(
            "/api/kg/entity-curation/split",
            json={"primary_entity_id": absorber.id, "split_off_entity_ids": [absorbed.id]},
        )

        assert r.status_code == 200
        audits = [row for row in db.all(ActionAudit) if row.action_name == "entity.split"]
        assert len(audits) == 1
        assert set(audits[0].target_ids) == {absorber.id, absorbed.id}

    def test_action_is_invokable_directly(self, db):
        from fichero_server.actions.registry import ActionContext, registry

        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")
        absorbed.merged_into_id = absorber.id
        db.save(absorbed)
        ctx = ActionContext(actor="mcp-agent", library_path="/lib/test.fichero")

        result = registry.invoke(
            db, "entity.split",
            {"primary_entity_id": absorber.id, "split_off_entity_ids": [absorbed.id]},
            ctx,
        )

        assert result.ok is True
        assert db.get(KnowledgeEntity, absorbed.id).merged_into_id is None

    def test_split_is_undoable_via_the_existing_undo_endpoint(self, client, db):
        """`undo_entity_operation_impl` already handles `operation_type ==
        split` -- confirmed real, not just marked undoable=True hopefully.
        Verified at the code (not assumed): undo-of-split restores the
        aliases the split moved away, it does NOT re-merge the split-off
        entities (`merged_into_id` is never touched in that branch)."""
        from fichero_server.models.knowledge import EntityMergeAudit

        absorber = _make_entity(db, "Alice")
        absorber.aliases = ["alice", "moved-alias"]
        db.save(absorber)
        absorbed = _make_entity(db, "Alicia")
        client.post(
            "/api/kg/entity-curation/merge",
            json={"absorbing_entity_id": absorber.id, "absorbed_entity_ids": [absorbed.id]},
        )
        split = client.post(
            "/api/kg/entity-curation/split",
            json={
                "primary_entity_id": absorber.id,
                "split_off_entity_ids": [absorbed.id],
                "aliases_to_move": ["moved-alias"],
            },
        )
        assert "moved-alias" not in db.get(KnowledgeEntity, absorber.id).aliases

        r = client.post(f"/api/kg/entity-curation/audit/{split.json()['id']}/undo")

        assert r.status_code == 200
        undo_audits = [row for row in db.all(EntityMergeAudit) if row.operation_type.value == "undo_split"]
        assert len(undo_audits) == 1
        assert "moved-alias" in db.get(KnowledgeEntity, absorber.id).aliases
        # Split-off status is untouched by undo (verified real behavior).
        assert db.get(KnowledgeEntity, absorbed.id).merged_into_id is None

    def test_a_split_entity_survives_the_nlp_draft_purge(self, db):
        """Closing the loop with entity.purge_nlp_draft, same shape as the
        entity.link_authority test (#4829)."""
        import fichero_server.api.routes.kg.nlp_draft_purge  # noqa: F401
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.importers.nlp_draft import run_nlp_draft
        from fichero_server.knowledge.spacy_ner import EntitySpan
        from fichero_server.knowledge.spacy_svo import ProposedTriple
        from fichero_server.models import Document, DocType, FileType, Status

        doc = Document(
            name="a.md", doc_type=DocType.file, file_type=FileType.text,
            status=Status.pending, page_content="Alice firmó la escritura.",
        )
        db.save(doc)

        def _stub_ner(text, language=None):
            return [EntitySpan(text="Alice", fichero_type="person", start=0, end=5, label="PERSON")]

        def _stub_svo(text, language=None):
            return [ProposedTriple(subject="Alice", verb="firmó", object="la escritura", sentence=text, char_start=0, char_end=len(text))]

        run_nlp_draft(db, doc, ner_fn=_stub_ner, svo_fn=_stub_svo, filter_fn=lambda p, t: (p, []))
        entity = db.query(KnowledgeEntity, canonical_name="Alice")[0]
        other = _make_entity(db, "A. Perez")

        ctx = ActionContext(actor="human", library_path="/lib/test.fichero")
        registry.invoke(
            db, "entity.split",
            {"primary_entity_id": entity.id, "split_off_entity_ids": [other.id]},
            ctx,
        )

        result = registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id, "dry_run": False}, ctx,
        )

        assert db.get(KnowledgeEntity, entity.id) is not None
        assert any(
            "entity.split" in reason for reason in result.result["protected_reasons"]
        )


# ---------------------------------------------------------------------------
# entity.batch_curation (#4831) -- was a bare route, writes an ActionAudit
# now.
# ---------------------------------------------------------------------------


class TestBatchCurationAction:
    def test_route_now_writes_an_action_audit(self, client, db):
        left = _make_entity(db, "Alice")
        right = _make_entity(db, "Bob")

        r = client.patch(
            "/api/kg/entities/batch-curation",
            json={"entity_ids": [left.id, right.id], "curation_state": "verified"},
        )

        assert r.status_code == 200
        audits = [
            row for row in db.all(ActionAudit) if row.action_name == "entity.batch_curation"
        ]
        assert len(audits) == 1
        assert set(audits[0].target_ids) == {left.id, right.id}

    def test_action_is_invokable_directly(self, db):
        from fichero_server.actions.registry import ActionContext, registry

        entity = _make_entity(db, "Alice")
        ctx = ActionContext(actor="mcp-agent", library_path="/lib/test.fichero")

        result = registry.invoke(
            db, "entity.batch_curation",
            {"entity_ids": [entity.id], "curation_state": "verified"},
            ctx,
        )

        assert result.ok is True
        assert db.get(KnowledgeEntity, entity.id).curation_state.value == "verified"

    def test_a_curated_entity_survives_the_nlp_draft_purge(self, db):
        """Unlike `entity.split`/`entity.link_authority`, `entity.batch_
        curation` changes `curation_state` itself -- so a curated entity
        is excluded by `entity.purge_nlp_draft`'s BASE candidate rule
        (curation_state != unreviewed) before `_protected_ids`'s
        ActionAudit check ever runs on it, not because that check named
        it. Empirically confirmed: asserting an "entity.batch_curation"
        reason here fails, because the entity is never even a candidate.
        This test asserts the (correct) outcome -- survival, and NOT a
        candidate at all -- rather than a reason that cannot fire."""
        import fichero_server.api.routes.kg.nlp_draft_purge  # noqa: F401
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.importers.nlp_draft import run_nlp_draft
        from fichero_server.knowledge.spacy_ner import EntitySpan
        from fichero_server.knowledge.spacy_svo import ProposedTriple
        from fichero_server.models import Document, DocType, FileType, Status

        doc = Document(
            name="a.md", doc_type=DocType.file, file_type=FileType.text,
            status=Status.pending, page_content="Alice firmó la escritura.",
        )
        db.save(doc)

        def _stub_ner(text, language=None):
            return [EntitySpan(text="Alice", fichero_type="person", start=0, end=5, label="PERSON")]

        def _stub_svo(text, language=None):
            return [ProposedTriple(subject="Alice", verb="firmó", object="la escritura", sentence=text, char_start=0, char_end=len(text))]

        run_nlp_draft(db, doc, ner_fn=_stub_ner, svo_fn=_stub_svo, filter_fn=lambda p, t: (p, []))
        entity = db.query(KnowledgeEntity, canonical_name="Alice")[0]

        ctx = ActionContext(actor="human", library_path="/lib/test.fichero")
        registry.invoke(
            db, "entity.batch_curation",
            {"entity_ids": [entity.id], "curation_state": "verified"},
            ctx,
        )

        result = registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id, "dry_run": False}, ctx,
        )

        assert db.get(KnowledgeEntity, entity.id) is not None
        assert result.result["entity_count"] == 0
        # Not a candidate at all (curation_state no longer unreviewed) --
        # so it is not counted as "protected" either; it never reached
        # `_protected_ids`.
        assert result.result["protected_count"] == 0


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
            "fichero_server.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )

        r = client.post(f"/api/kg/entity-curation/audit/{merge.json()['id']}/undo")

        assert r.status_code == 200
        audits = [row for row in db.all(ActionAudit) if row.action_name == "entity.unmerge"]
        assert len(audits) == 1
        assert audits[0].target_ids == [absorber.id, absorbed.id]
        assert calls[-1][1]["type"] == "entity.split"
        assert calls[-1][1]["entity_ids"] == [absorber.id, absorbed.id]


# ---------------------------------------------------------------------------
# entity.link_authority (#4829) -- was a bare route, writes an ActionAudit
# now. Mirrors TestMergeEntities/TestUndoEntityOperation's own shape.
# ---------------------------------------------------------------------------


def _make_authority_snapshot(db, authority: str = "wikidata", authority_id: str = "Q1") -> "AuthoritySnapshot":
    from fichero_server.models.knowledge import AuthoritySnapshot

    snapshot = AuthoritySnapshot(
        authority=authority,
        authority_id=authority_id,
        label="Test Authority Record",
        source_url="https://example.org/Q1",
    )
    db.save(snapshot)
    return snapshot


class TestLinkAuthorityAction:
    def test_route_still_returns_the_same_shape(self, client, db):
        """Same URL, same request/response as the bare route (#4829)."""
        entity = _make_entity(db, "Alice")
        _make_authority_snapshot(db)

        r = client.post(
            "/api/kg/entity-curation/authority/link",
            json={"entity_id": entity.id, "authority": "wikidata", "authority_id": "Q1"},
        )

        assert r.status_code == 200
        body = r.json()
        operation_type = body.get("operationType") or body.get("operation_type")
        target_entity_id = body.get("targetEntityId") or body.get("target_entity_id")
        assert operation_type == "authority_link"
        assert target_entity_id == entity.id

    def test_route_now_writes_an_action_audit(self, client, db):
        """This is THE gap #4829 exists to close -- before, this route
        produced zero ActionAudit rows."""
        entity = _make_entity(db, "Alice")
        _make_authority_snapshot(db)

        client.post(
            "/api/kg/entity-curation/authority/link",
            json={"entity_id": entity.id, "authority": "wikidata", "authority_id": "Q1"},
        )

        audits = [row for row in db.all(ActionAudit) if row.action_name == "entity.link_authority"]
        assert len(audits) == 1
        assert audits[0].target_ids == [entity.id]

    def test_route_still_writes_the_entity_merge_audit(self, client, db):
        """The inspector's curation history reads EntityMergeAudit -- must
        keep existing, unchanged in shape, regardless of the action wrapper."""
        from fichero_server.models.knowledge import EntityMergeAudit, EntityMergeOperationType

        entity = _make_entity(db, "Alice")
        _make_authority_snapshot(db)

        client.post(
            "/api/kg/entity-curation/authority/link",
            json={"entity_id": entity.id, "authority": "wikidata", "authority_id": "Q1"},
        )

        merge_audits = [
            row for row in db.all(EntityMergeAudit)
            if row.operation_type == EntityMergeOperationType.authority_link
        ]
        assert len(merge_audits) == 1
        assert merge_audits[0].target_entity_id == entity.id
        assert merge_audits[0].created_by == "human"

    def test_route_still_writes_entity_metadata(self, client, db):
        entity = _make_entity(db, "Alice")
        _make_authority_snapshot(db)

        client.post(
            "/api/kg/entity-curation/authority/link",
            json={"entity_id": entity.id, "authority": "wikidata", "authority_id": "Q1"},
        )

        refreshed = db.get(KnowledgeEntity, entity.id)
        assert refreshed.metadata.get("authority_links") == [
            {"authority": "wikidata", "authority_id": "Q1"}
        ]

    def test_route_404s_on_missing_snapshot_unchanged(self, client, db):
        entity = _make_entity(db, "Alice")

        r = client.post(
            "/api/kg/entity-curation/authority/link",
            json={"entity_id": entity.id, "authority": "wikidata", "authority_id": "Q999"},
        )

        assert r.status_code == 404

    def test_route_404s_on_missing_entity_unchanged(self, client, db):
        _make_authority_snapshot(db)

        r = client.post(
            "/api/kg/entity-curation/authority/link",
            json={"entity_id": "nonexistent", "authority": "wikidata", "authority_id": "Q1"},
        )

        assert r.status_code == 404

    def test_action_is_invokable_directly_not_only_through_the_route(self, db):
        """Reachable via /api/actions/invoke (agent/CLI/MCP) -- the whole
        point of #4829."""
        from fichero_server.actions.registry import ActionContext, registry

        entity = _make_entity(db, "Alice")
        _make_authority_snapshot(db)
        ctx = ActionContext(actor="mcp-agent", library_path="/lib/test.fichero")

        result = registry.invoke(
            db, "entity.link_authority",
            {"entity_id": entity.id, "authority": "wikidata", "authority_id": "Q1"},
            ctx,
        )

        assert result.ok is True
        audits = [row for row in db.all(ActionAudit) if row.action_name == "entity.link_authority"]
        assert len(audits) == 1

    def test_not_undoable_no_regression_from_bare_route(self, db):
        """No undo-* machinery exists for authority_link -- confirmed at
        `undo_entity_operation_impl`, which 409s on anything but merge/
        split. Registering the action must not silently promise an undo
        the endpoint cannot deliver."""
        from fichero_server.actions.registry import registry

        entry = registry._actions["entity.link_authority"]
        assert entry.undoable is False

    def test_a_linked_entity_survives_the_nlp_draft_purge(self, db):
        """Closing the loop with #4823's purge: an entity linked through
        the ACTION now shows up via the ActionAudit protection check, not
        just the EntityMergeAudit/metadata fallbacks."""
        import fichero_server.api.routes.kg.nlp_draft_purge  # noqa: F401
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.importers.nlp_draft import run_nlp_draft
        from fichero_server.knowledge.spacy_ner import EntitySpan
        from fichero_server.knowledge.spacy_svo import ProposedTriple
        from fichero_server.models import Document, DocType, FileType, Status

        doc = Document(
            name="a.md", doc_type=DocType.file, file_type=FileType.text,
            status=Status.pending, page_content="Alice firmó la escritura.",
        )
        db.save(doc)

        def _stub_ner(text, language=None):
            return [EntitySpan(text="Alice", fichero_type="person", start=0, end=5, label="PERSON")]

        def _stub_svo(text, language=None):
            return [ProposedTriple(subject="Alice", verb="firmó", object="la escritura", sentence=text, char_start=0, char_end=len(text))]

        run_nlp_draft(db, doc, ner_fn=_stub_ner, svo_fn=_stub_svo, filter_fn=lambda p, t: (p, []))
        entity = db.query(KnowledgeEntity, canonical_name="Alice")[0]
        _make_authority_snapshot(db)

        ctx = ActionContext(actor="human", library_path="/lib/test.fichero")
        registry.invoke(
            db, "entity.link_authority",
            {"entity_id": entity.id, "authority": "wikidata", "authority_id": "Q1"},
            ctx,
        )

        result = registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id, "dry_run": False}, ctx,
        )

        assert db.get(KnowledgeEntity, entity.id) is not None
        assert any(
            "entity.link_authority" in reason
            for reason in result.result["protected_reasons"]
        )
