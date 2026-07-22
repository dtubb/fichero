"""Tests for review queue routes.

The review queue manages KnowledgeClaim curation state transitions
(unreviewed → shortlisted → curated/rejected). Routes live under
/api/claims/... because the router uses prefix="/claims" and is mounted
at /api.
"""

from fichero.models.knowledge import (
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
    ClaimCurationState,
    ClaimRelationType,
    ClaimSuppressionRule,
    ClaimType,
    EpistemicStatus,
    MutationLog,
)
from fichero.models import ActionAudit, DocType, Document


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(name: str = "Alice", entity_id: str = "ent-1") -> KnowledgeEntity:
    return KnowledgeEntity(id=entity_id, canonical_name=name)


def _make_claim(
    claim_id: str = "claim-1",
    text: str = "Paris is the capital of France.",
    curation_state: ClaimCurationState = ClaimCurationState.unreviewed,
    entity_ids: list[str] | None = None,
    source_document_id: str = "doc-1",
    confidence: float = 0.8,
    subject_canonical: str | None = None,
    predicate_verb: str | None = None,
    object_phrase: str | None = None,
) -> KnowledgeClaim:
    return KnowledgeClaim(
        id=claim_id,
        text=text,
        source_document_id=source_document_id,
        source_ids=[source_document_id],
        claim_type=ClaimType.fact,
        epistemic_status=EpistemicStatus.tentative,
        curation_state=curation_state,
        confidence=confidence,
        entity_ids=entity_ids or [],
        subject_canonical=subject_canonical,
        predicate_verb=predicate_verb,
        object_phrase=object_phrase,
    )


# ---------------------------------------------------------------------------
# PATCH /api/claims/{claim_id}/transition
# ---------------------------------------------------------------------------


class TestTransitionClaim:
    def test_transition_to_shortlisted(self, client, db):
        claim = _make_claim()
        db.save(claim)

        r = client.patch(f"/api/claims/{claim.id}/transition", json={
            "to_state": "shortlisted",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["from_state"] == "unreviewed"
        assert data["to_state"] == "shortlisted"

    def test_transition_to_curated(self, client, db):
        claim = _make_claim(curation_state=ClaimCurationState.shortlisted)
        db.save(claim)

        r = client.patch(f"/api/claims/{claim.id}/transition", json={
            "to_state": "curated",
            "reason": "Verified",
        })
        assert r.status_code == 200
        assert r.json()["to_state"] == "curated"

    def test_transition_to_rejected(self, client, db):
        claim = _make_claim()
        db.save(claim)

        r = client.patch(f"/api/claims/{claim.id}/transition", json={
            "to_state": "rejected",
            "reason": "Duplicate",
        })
        assert r.status_code == 200
        assert r.json()["to_state"] == "rejected"

    def test_transition_missing_claim_returns_404(self, client):
        r = client.patch("/api/claims/no-such-claim/transition", json={
            "to_state": "shortlisted",
        })
        assert r.status_code == 404

    def test_transition_invalid_state_returns_400(self, client, db):
        claim = _make_claim()
        db.save(claim)

        r = client.patch(f"/api/claims/{claim.id}/transition", json={
            "to_state": "invalid-state",
        })
        assert r.status_code == 400

    def test_transition_writes_action_audit_and_emits(self, client, db, monkeypatch):
        claim = _make_claim()
        db.save(claim)
        calls: list[tuple] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )

        r = client.patch(f"/api/claims/{claim.id}/transition", json={"to_state": "shortlisted"})

        assert r.status_code == 200
        audits = [row for row in db.all(ActionAudit) if row.action_name == "claim.transition"]
        assert len(audits) == 1
        assert audits[0].target_ids == [claim.id]
        assert calls[-1][1]["type"] == "claim.updated"
        assert calls[-1][1]["claim_ids"] == [claim.id]


# ---------------------------------------------------------------------------
# POST /api/claims/batch/transition
# ---------------------------------------------------------------------------


class TestBatchTransition:
    def test_batch_transitions_succeed(self, client, db):
        c1 = _make_claim("c-1", "Claim one")
        c2 = _make_claim("c-2", "Claim two")
        db.save(c1)
        db.save(c2)

        r = client.post("/api/claims/batch/transition", json={
            "claim_ids": ["c-1", "c-2"],
            "to_state": "shortlisted",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert data["succeeded"] == 2
        assert data["failed"] == 0

    def test_batch_transition_with_missing_claims(self, client, db):
        c1 = _make_claim("c-1", "Claim one")
        db.save(c1)

        r = client.post("/api/claims/batch/transition", json={
            "claim_ids": ["c-1", "no-such-claim"],
            "to_state": "shortlisted",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["succeeded"] == 1
        assert data["failed"] == 1

    def test_batch_transition_invalid_state_returns_400(self, client):
        r = client.post("/api/claims/batch/transition", json={
            "claim_ids": ["c-1"],
            "to_state": "bogus",
        })
        assert r.status_code == 400


class TestBatchClaimCuration:
    def test_batch_updates_claims_and_logs_mutations(self, client, db):
        c1 = _make_claim("c-1", "Claim one")
        c2 = _make_claim("c-2", "Claim two")
        db.save(c1)
        db.save(c2)

        r = client.patch("/api/kg/claims/batch-curation", json={
            "claim_ids": ["c-1", "c-2"],
            "curation_state": "curated",
        })

        assert r.status_code == 200
        assert r.json() == {
            "updated": 2,
            "claim_ids": ["c-1", "c-2"],
        }
        assert db.get(KnowledgeClaim, "c-1").curation_state == ClaimCurationState.curated
        assert db.get(KnowledgeClaim, "c-2").curation_state == ClaimCurationState.curated

        logs = [m for m in db.all(MutationLog) if m.entity_type == "KnowledgeClaim"]
        assert len(logs) == 2
        assert {m.entity_id for m in logs} == {"c-1", "c-2"}
        for log in logs:
            assert log.operation.value == "update"
            assert log.changed_fields == ["curation_state"]
            assert log.before_state["curation_state"] == "unreviewed"
            assert log.after_state["curation_state"] == "curated"

    def test_batch_skips_unchanged_claims(self, client, db):
        claim = _make_claim("c-1", curation_state=ClaimCurationState.shortlisted)
        db.save(claim)

        r = client.patch("/api/kg/claims/batch-curation", json={
            "claim_ids": ["c-1"],
            "curation_state": "shortlisted",
        })

        assert r.status_code == 200
        assert r.json() == {"updated": 0, "claim_ids": []}
        assert db.all(MutationLog) == []

    def test_batch_curation_writes_action_audit_and_emits(self, client, db, monkeypatch):
        c1 = _make_claim("c-1", "Claim one")
        c2 = _make_claim("c-2", "Claim two")
        db.save(c1)
        db.save(c2)
        calls: list[tuple] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )

        r = client.patch("/api/kg/claims/batch-curation", json={
            "claim_ids": ["c-1", "c-2"],
            "curation_state": "curated",
        })

        assert r.status_code == 200
        audits = [
            row for row in db.all(ActionAudit) if row.action_name == "claim.batch_curation"
        ]
        assert len(audits) == 1
        assert audits[0].target_ids == ["c-1", "c-2"]
        assert calls[-1][1]["type"] == "claim.updated"
        assert calls[-1][1]["claim_ids"] == ["c-1", "c-2"]


class TestClaimMerge:
    def test_merge_consolidates_provenance_and_repoints_links(self, client, db):
        db.save(_make_entity("Alice", "ent-1"))
        db.save(_make_entity("Alicia", "ent-2"))
        survivor = _make_claim(
            "claim-survivor",
            text="Alice was born in 1923.",
            entity_ids=["ent-1"],
            source_document_id="doc-1",
            subject_canonical="Alice",
            predicate_verb="was born in",
            object_phrase="1923",
        )
        survivor.source_page_label = "1"
        survivor.source_ids = ["doc-1"]
        survivor.corroborating_source_ids = ["doc-1"]
        survivor.corroboration_count = 1
        survivor.source_languages = ["en"]
        absorbed = _make_claim(
            "claim-absorbed",
            text="Alice was born in 1923.",
            entity_ids=["ent-2"],
            source_document_id="doc-2",
            subject_canonical="Alice",
            predicate_verb="was born in",
            object_phrase="1923",
        )
        absorbed.source_page_label = "2"
        absorbed.source_ids = ["doc-2"]
        absorbed.corroborating_source_ids = ["doc-2"]
        absorbed.corroboration_count = 1
        absorbed.source_languages = ["es"]
        db.save(survivor)
        db.save(absorbed)
        db.save(KnowledgeClaimLink(
            id="dup-link",
            claim_id=absorbed.id,
            related_claim_id=survivor.id,
            relation_type=ClaimRelationType.duplicate_of,
        ))
        db.save(KnowledgeClaimLink(
            id="supports-link",
            claim_id=absorbed.id,
            related_claim_id="claim-other",
            relation_type=ClaimRelationType.supports,
        ))

        r = client.post(
            "/api/kg/claims/merge",
            json={
                "surviving_claim_id": survivor.id,
                "absorbed_claim_ids": [absorbed.id],
            },
        )

        assert r.status_code == 200
        body = r.json()
        assert body["operation_type"] == "merge"
        assert body["target_claim_id"] == survivor.id
        assert body["source_claim_ids"] == [absorbed.id]

        survivor_after = db.get(KnowledgeClaim, survivor.id)
        absorbed_after = db.get(KnowledgeClaim, absorbed.id)
        assert sorted(survivor_after.corroborating_source_ids) == ["doc-1", "doc-2"]
        assert sorted(survivor_after.source_ids) == ["doc-2"]
        assert sorted(survivor_after.entity_ids) == ["ent-1", "ent-2"]
        assert sorted(survivor_after.source_page_labels) == ["1", "2"]
        assert absorbed_after.merged_into_id == survivor.id
        assert absorbed_after.curation_state == ClaimCurationState.rejected
        assert db.get(KnowledgeClaimLink, "dup-link") is None
        repointed = db.get(KnowledgeClaimLink, "supports-link")
        assert repointed.claim_id == survivor.id
        assert repointed.related_claim_id == "claim-other"

    def test_unmerge_restores_claims_and_links(self, client, db):
        survivor = _make_claim("claim-survivor", source_document_id="doc-1")
        absorbed = _make_claim("claim-absorbed", source_document_id="doc-2")
        db.save(survivor)
        db.save(absorbed)
        db.save(KnowledgeClaimLink(
            id="dup-link",
            claim_id=absorbed.id,
            related_claim_id=survivor.id,
            relation_type=ClaimRelationType.duplicate_of,
        ))

        merge = client.post(
            "/api/kg/claims/merge",
            json={
                "surviving_claim_id": survivor.id,
                "absorbed_claim_ids": [absorbed.id],
            },
        )
        assert merge.status_code == 200
        audit_id = merge.json()["id"]

        unmerge = client.post("/api/kg/claims/unmerge", json={"audit_id": audit_id})

        assert unmerge.status_code == 200
        assert unmerge.json()["operation_type"] == "unmerge"
        restored_survivor = db.get(KnowledgeClaim, survivor.id)
        restored_absorbed = db.get(KnowledgeClaim, absorbed.id)
        assert restored_survivor.merged_into_id is None
        assert restored_absorbed.merged_into_id is None
        assert restored_absorbed.curation_state == ClaimCurationState.unreviewed
        restored_link = db.get(KnowledgeClaimLink, "dup-link")
        assert restored_link is not None
        assert restored_link.claim_id == absorbed.id
        assert restored_link.related_claim_id == survivor.id

    def test_merge_rejects_already_merged_claim(self, client, db):
        survivor = _make_claim("claim-survivor")
        second_survivor = _make_claim("claim-survivor-2")
        absorbed = _make_claim("claim-absorbed")
        db.save(survivor)
        db.save(second_survivor)
        db.save(absorbed)
        first = client.post(
            "/api/kg/claims/merge",
            json={
                "surviving_claim_id": survivor.id,
                "absorbed_claim_ids": [absorbed.id],
            },
        )
        assert first.status_code == 200

        second = client.post(
            "/api/kg/claims/merge",
            json={
                "surviving_claim_id": second_survivor.id,
                "absorbed_claim_ids": [absorbed.id],
            },
        )
        assert second.status_code == 409

    def test_unmerge_is_not_idempotent(self, client, db):
        survivor = _make_claim("claim-survivor")
        absorbed = _make_claim("claim-absorbed")
        db.save(survivor)
        db.save(absorbed)
        merge = client.post(
            "/api/kg/claims/merge",
            json={
                "surviving_claim_id": survivor.id,
                "absorbed_claim_ids": [absorbed.id],
            },
        )
        audit_id = merge.json()["id"]

        first = client.post("/api/kg/claims/unmerge", json={"audit_id": audit_id})
        second = client.post("/api/kg/claims/unmerge", json={"audit_id": audit_id})

        assert first.status_code == 200
        assert second.status_code == 409

    def test_merge_writes_action_audit_and_emits(self, client, db, monkeypatch):
        survivor = _make_claim("claim-survivor")
        absorbed = _make_claim("claim-absorbed")
        db.save(survivor)
        db.save(absorbed)
        calls: list[tuple] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )

        r = client.post(
            "/api/kg/claims/merge",
            json={
                "surviving_claim_id": survivor.id,
                "absorbed_claim_ids": [absorbed.id],
            },
        )

        assert r.status_code == 200
        audits = [row for row in db.all(ActionAudit) if row.action_name == "claim.merge"]
        assert len(audits) == 1
        assert audits[0].target_ids == [survivor.id, absorbed.id]
        assert calls[-1][1]["type"] == "claim.merged"
        assert calls[-1][1]["claim_ids"] == [survivor.id, absorbed.id]


class TestPruneTrivialClaims:
    def test_prunes_document_scoped_trivial_claims_only(self, client, db):
        db.save(Document(id="doc-1", name="Page 1", doc_type=DocType.page))
        db.save(Document(id="doc-2", name="Page 2", doc_type=DocType.page))
        trivial = _make_claim(
            "c-trivial",
            text="Andagoya is a place.",
            source_document_id="doc-1",
            subject_canonical="Andagoya",
            predicate_verb="is",
            object_phrase="a place",
            confidence=0.9,
        )
        substantive = _make_claim(
            "c-substantive",
            text="Andagoya was founded in 1851.",
            source_document_id="doc-1",
            subject_canonical="Andagoya",
            predicate_verb="was founded in",
            object_phrase="1851",
        )
        out_of_scope = _make_claim(
            "c-out-of-scope",
            text="Tumaco is a place.",
            source_document_id="doc-2",
            subject_canonical="Tumaco",
            predicate_verb="is",
            object_phrase="a place",
        )
        db.save(trivial)
        db.save(substantive)
        db.save(out_of_scope)

        r = client.post("/api/kg/claims/prune-trivial", json={"document_id": "doc-1"})

        assert r.status_code == 200
        assert r.json() == {
            "scope_type": "document",
            "scope_document_ids": ["doc-1"],
            "identified_count": 1,
            "suppressed_count": 1,
            "suppressed_claim_ids": ["c-trivial"],
            "rules_written": 0,
        }
        assert db.get(KnowledgeClaim, "c-trivial").curation_state == ClaimCurationState.rejected
        assert db.get(KnowledgeClaim, "c-trivial").confidence == 0.2
        assert db.get(KnowledgeClaim, "c-substantive").curation_state == ClaimCurationState.unreviewed
        assert db.get(KnowledgeClaim, "c-out-of-scope").curation_state == ClaimCurationState.unreviewed

    def test_prunes_folder_scope_via_descendants(self, client, db):
        db.save(Document(id="folder-1", name="Folder", doc_type=DocType.folder))
        db.save(Document(id="page-1", name="Page", doc_type=DocType.page, parent_id="folder-1"))
        db.save(Document(id="page-2", name="Page 2", doc_type=DocType.page))
        db.save(_make_claim(
            "c-folder",
            text="Andagoya is a place.",
            source_document_id="page-1",
            subject_canonical="Andagoya",
            predicate_verb="is",
            object_phrase="a place",
        ))
        db.save(_make_claim(
            "c-other",
            text="Tumaco is a place.",
            source_document_id="page-2",
            subject_canonical="Tumaco",
            predicate_verb="is",
            object_phrase="a place",
        ))

        r = client.post("/api/kg/claims/prune-trivial", json={"folder_id": "folder-1"})

        assert r.status_code == 200
        payload = r.json()
        assert payload["scope_type"] == "folder"
        assert payload["scope_document_ids"] == ["folder-1", "page-1"]
        assert payload["identified_count"] == 1
        assert payload["suppressed_count"] == 1
        assert payload["suppressed_claim_ids"] == ["c-folder"]
        assert db.get(KnowledgeClaim, "c-folder").curation_state == ClaimCurationState.rejected
        assert db.get(KnowledgeClaim, "c-other").curation_state == ClaimCurationState.unreviewed

    def test_library_wide_run_is_idempotent_and_writes_one_rule(self, client, db):
        db.save(_make_claim(
            "c-library",
            text="Andagoya is a place.",
            subject_canonical="Andagoya",
            predicate_verb="is",
            object_phrase="a place",
        ))

        first = client.post("/api/kg/claims/prune-trivial", json={"library_wide": True})
        second = client.post("/api/kg/claims/prune-trivial", json={"library_wide": True})

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["identified_count"] == 1
        assert first.json()["suppressed_count"] == 1
        assert first.json()["rules_written"] == 1
        assert second.json()["identified_count"] == 1
        assert second.json()["suppressed_count"] == 0
        assert second.json()["rules_written"] == 0

        rules = db.all(ClaimSuppressionRule)
        assert len(rules) == 1
        assert rules[0].suppress_is_a_copulas is True
        assert rules[0].match_subject_name is None

    def test_prune_trivial_writes_action_audit_and_emits(self, client, db, monkeypatch):
        db.save(_make_claim(
            "c-library",
            text="Andagoya is a place.",
            subject_canonical="Andagoya",
            predicate_verb="is",
            object_phrase="a place",
        ))
        calls: list[tuple] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )

        r = client.post("/api/kg/claims/prune-trivial", json={"library_wide": True})

        assert r.status_code == 200
        audits = [
            row for row in db.all(ActionAudit) if row.action_name == "claim.prune_trivial"
        ]
        assert len(audits) == 1
        assert audits[0].target_ids == ["c-library"]
        assert calls[-1][1]["type"] == "claim.updated"
        assert calls[-1][1]["claim_ids"] == ["c-library"]


# ---------------------------------------------------------------------------
# GET /api/claims/queues/unreviewed
# ---------------------------------------------------------------------------


class TestUnreviewedQueue:
    def test_empty_queue(self, client):
        r = client.get("/api/claims/queues/unreviewed")
        assert r.status_code == 200
        data = r.json()
        assert data["queue"] == "unreviewed"
        assert data["claims"] == []
        assert data["total"] == 0

    def test_returns_unreviewed_claims(self, client, db):
        claim = _make_claim(curation_state=ClaimCurationState.unreviewed)
        db.save(claim)

        r = client.get("/api/claims/queues/unreviewed")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["claims"][0]["claim_id"] == claim.id

    def test_does_not_return_shortlisted_claims(self, client, db):
        claim = _make_claim(curation_state=ClaimCurationState.shortlisted)
        db.save(claim)

        r = client.get("/api/claims/queues/unreviewed")
        assert r.status_code == 200
        assert r.json()["total"] == 0


# ---------------------------------------------------------------------------
# GET /api/claims/queues/shortlisted
# ---------------------------------------------------------------------------


class TestShortlistedQueue:
    def test_returns_shortlisted_claims(self, client, db):
        claim = _make_claim(curation_state=ClaimCurationState.shortlisted)
        db.save(claim)

        r = client.get("/api/claims/queues/shortlisted")
        assert r.status_code == 200
        assert r.json()["total"] == 1
        assert r.json()["queue"] == "shortlisted"


# ---------------------------------------------------------------------------
# GET /api/claims/queues/curated
# ---------------------------------------------------------------------------


class TestCuratedQueue:
    def test_returns_curated_claims(self, client, db):
        claim = _make_claim(curation_state=ClaimCurationState.curated)
        db.save(claim)

        r = client.get("/api/claims/queues/curated")
        assert r.status_code == 200
        assert r.json()["total"] == 1
        assert r.json()["queue"] == "curated"


# ---------------------------------------------------------------------------
# GET /api/claims/queues/rejected
# ---------------------------------------------------------------------------


class TestRejectedQueue:
    def test_returns_rejected_claims(self, client, db):
        claim = _make_claim(curation_state=ClaimCurationState.rejected)
        db.save(claim)

        r = client.get("/api/claims/queues/rejected")
        assert r.status_code == 200
        assert r.json()["total"] == 1
        assert r.json()["queue"] == "rejected"

    def test_filter_by_question(self, client, db):
        c1 = _make_claim("c-1", "Paris is the capital", ClaimCurationState.rejected)
        c2 = _make_claim("c-2", "The sky is blue", ClaimCurationState.rejected)
        db.save(c1)
        db.save(c2)

        r = client.get("/api/claims/queues/rejected?question=Paris")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["claims"][0]["claim_id"] == "c-1"
