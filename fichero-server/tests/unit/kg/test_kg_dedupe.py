"""Batch KG dedupe: the planner and the dry-run/apply routes (#4508).

Planner: pure-function tests of the matching tiers and their quality gates
(cross-type impossible, unreviewed-only default, similarity opt-in, survivor
rank). Routes: dry-run touches nothing, apply drives the audited merge
actions, and dry-run/apply plan the SAME groups (parity).
"""

from __future__ import annotations

from fichero_server.knowledge.dedupe import (
    normalize_name,
    plan_claim_dedupe,
    plan_entity_dedupe,
)
from fichero_server.models import ActionAudit, DocType, Document
from fichero_server.models.knowledge import (
    ClaimCurationState,
    ClaimMergeAudit,
    EntityCurationState,
    EntityMergeAudit,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)


def _entity(
    name: str,
    entity_type: EntityType = EntityType.person,
    *,
    aliases: list[str] | None = None,
    curation_state: EntityCurationState = EntityCurationState.unreviewed,
    corroboration_count: int = 0,
    merged_into_id: str | None = None,
) -> KnowledgeEntity:
    return KnowledgeEntity(
        canonical_name=name,
        entity_type=entity_type,
        aliases=aliases or [],
        curation_state=curation_state,
        corroboration_count=corroboration_count,
        merged_into_id=merged_into_id,
    )


def _claim(
    text: str,
    *,
    subject_entity_id: str | None = "ent-1",
    subject_canonical: str | None = None,
    predicate_verb: str | None = None,
    object_phrase: str | None = None,
    source_document_id: str | None = None,
    curation_state: ClaimCurationState = ClaimCurationState.unreviewed,
    corroboration_count: int = 0,
) -> KnowledgeClaim:
    return KnowledgeClaim(
        text=text,
        subject_entity_id=subject_entity_id,
        subject_canonical=subject_canonical,
        predicate_verb=predicate_verb,
        object_phrase=object_phrase,
        source_document_id=source_document_id,
        curation_state=curation_state,
        corroboration_count=corroboration_count,
        confidence=0.9,
    )


# ---------------------------------------------------------------------------
# normalize_name — the forms the Marshall survey actually found
# ---------------------------------------------------------------------------


class TestNormalizeName:
    def test_accents_case_punctuation_whitespace(self):
        assert normalize_name("Quibdó") == normalize_name("Quibdo")
        assert normalize_name("Jorge\nCardenas") == normalize_name("Jorge Cardenas")
        assert normalize_name("B'na") == normalize_name("B/na")
        assert normalize_name('"La Piedra"') == normalize_name("La Piedra")
        assert normalize_name("Laura C. Hall") == normalize_name("Laura C Hall")

    def test_distinct_names_stay_distinct(self):
        assert normalize_name("Laura Hall") != normalize_name("Laura C Hall")


# ---------------------------------------------------------------------------
# plan_entity_dedupe
# ---------------------------------------------------------------------------


class TestPlanEntityDedupe:
    def test_exact_normalized_name_groups(self):
        a, b = _entity("Quibdó", EntityType.location), _entity("Quibdo", EntityType.location)
        groups = plan_entity_dedupe([a, b])
        assert len(groups) == 1
        assert {groups[0].survivor.id, *(e.id for e in groups[0].absorbed)} == {a.id, b.id}
        assert groups[0].basis == "normalized-name"

    def test_cross_type_never_grouped(self):
        # 'Davis' the person and 'Davis' the organization are different things.
        person = _entity("Davis", EntityType.person)
        org = _entity("Davis", EntityType.organization)
        assert plan_entity_dedupe([person, org]) == []

    def test_alias_collision_groups(self):
        a = _entity("William Marshall", aliases=["W. Marshall"])
        b = _entity("Bill Marshall", aliases=["w marshall"])
        groups = plan_entity_dedupe([a, b])
        assert len(groups) == 1
        assert groups[0].basis == "alias-collision"

    def test_alias_matching_other_canonical_name_groups(self):
        a = _entity("William Marshall")
        b = _entity("Bill Marshall", aliases=["william marshall"])
        groups = plan_entity_dedupe([a, b])
        assert len(groups) == 1

    def test_rejected_and_already_merged_never_participate(self):
        keep = _entity("Quibdo", EntityType.location)
        rejected = _entity(
            "Quibdó", EntityType.location, curation_state=EntityCurationState.rejected
        )
        merged = _entity("Quibdo", EntityType.location, merged_into_id="elsewhere")
        assert plan_entity_dedupe([keep, rejected, merged]) == []

    def test_reviewed_entities_not_absorbed_by_default(self):
        curated = _entity(
            "Quibdo", EntityType.location, curation_state=EntityCurationState.verified
        )
        dup = _entity("Quibdó", EntityType.location)
        groups = plan_entity_dedupe([curated, dup])
        # The curated row survives; only the unreviewed duplicate is absorbed.
        assert len(groups) == 1
        assert groups[0].survivor.id == curated.id
        assert [e.id for e in groups[0].absorbed] == [dup.id]

        two_curated = _entity(
            "Quibdó", EntityType.location, curation_state=EntityCurationState.verified
        )
        assert plan_entity_dedupe([curated, two_curated]) == []
        assert len(plan_entity_dedupe([curated, two_curated], include_reviewed=True)) == 1

    def test_survivor_prefers_corroboration(self):
        weak = _entity("Quibdo", EntityType.location)
        strong = _entity("Quibdó", EntityType.location, corroboration_count=5)
        groups = plan_entity_dedupe([weak, strong])
        assert groups[0].survivor.id == strong.id

    def test_survivor_prefers_cleaner_name_on_ties(self):
        messy = _entity("Jorge\nCardenas")
        clean = _entity("Jorge Cardenas")
        groups = plan_entity_dedupe([messy, clean])
        assert groups[0].survivor.id == clean.id

    def test_similarity_tier_is_opt_in(self):
        a, b = _entity("Rodolfo Arriaga"), _entity("Rudolfo Arriaga")
        assert plan_entity_dedupe([a, b]) == []
        groups = plan_entity_dedupe([a, b], min_similarity=0.9)
        assert len(groups) == 1
        assert groups[0].basis == "similarity"
        assert groups[0].similarity is not None and groups[0].similarity >= 0.9

    def test_similarity_stays_within_type(self):
        a = _entity("Marin", EntityType.person)
        b = _entity("Marín", EntityType.location)
        assert plan_entity_dedupe([a, b], min_similarity=0.9) == []


# ---------------------------------------------------------------------------
# plan_claim_dedupe
# ---------------------------------------------------------------------------


class TestPlanClaimDedupe:
    def test_exact_svo_duplicates_group_across_documents(self):
        a = _claim(
            "Marshall arrived at Quibdo.",
            predicate_verb="arrived at",
            object_phrase="Quibdo",
            source_document_id="doc-1",
        )
        b = _claim(
            "Marshall arrived at Quibdo!",
            predicate_verb="Arrived at",
            object_phrase="Quibdo.",
            source_document_id="doc-2",
        )
        groups = plan_claim_dedupe([a, b])
        assert len(groups) == 1
        assert groups[0].basis == "normalized-name"

    def test_different_subjects_never_group(self):
        a = _claim("X did Y", subject_entity_id="ent-1", predicate_verb="did", object_phrase="Y")
        b = _claim("Z did Y", subject_entity_id="ent-2", predicate_verb="did", object_phrase="Y")
        assert plan_claim_dedupe([a, b]) == []

    def test_no_svo_falls_back_to_normalized_text(self):
        a = _claim("A legal holiday at the office.", subject_canonical="Office", subject_entity_id=None)
        b = _claim('A legal holiday, at the office', subject_canonical="office", subject_entity_id=None)
        assert len(plan_claim_dedupe([a, b])) == 1

    def test_subjectless_claims_are_left_alone(self):
        a = _claim("Same text.", subject_entity_id=None)
        b = _claim("Same text.", subject_entity_id=None)
        assert plan_claim_dedupe([a, b]) == []

    def test_near_duplicate_tier_is_opt_in_and_token_gated(self):
        a = _claim("t", predicate_verb="gave", object_phrase="the deed to Pedro")
        b = _claim("t", predicate_verb="gave", object_phrase="to Pedro the deed")
        assert plan_claim_dedupe([a, b]) == []
        groups = plan_claim_dedupe([a, b], near_duplicate_threshold=0.6)
        assert len(groups) == 1
        # Different token sets never merge, however close the ratio.
        c = _claim("t", predicate_verb="gave", object_phrase="the deed to Pablo")
        assert plan_claim_dedupe([a, c], near_duplicate_threshold=0.6) == []

    def test_rejected_and_reviewed_gates(self):
        survivor = _claim(
            "s",
            predicate_verb="did",
            object_phrase="thing",
            curation_state=ClaimCurationState.curated,
        )
        dup = _claim("s", predicate_verb="did", object_phrase="thing")
        rejected = _claim(
            "s",
            predicate_verb="did",
            object_phrase="thing",
            curation_state=ClaimCurationState.rejected,
        )
        groups = plan_claim_dedupe([survivor, dup, rejected])
        assert len(groups) == 1
        assert groups[0].survivor.id == survivor.id
        assert [c.id for c in groups[0].absorbed] == [dup.id]


# ---------------------------------------------------------------------------
# Routes: dry-run/apply parity, audited apply
# ---------------------------------------------------------------------------


def _save_entities(db, *entities: KnowledgeEntity) -> None:
    for entity in entities:
        db.save(entity)


class TestEntityDedupeRoute:
    def test_dry_run_plans_and_touches_nothing(self, client, db):
        a, b = _entity("Quibdó", EntityType.location), _entity("Quibdo", EntityType.location)
        _save_entities(db, a, b)
        r = client.post("/api/kg/entity-curation/dedupe", json={})
        assert r.status_code == 200
        body = r.json()
        assert body["dry_run"] is True
        assert body["merges_applied"] == 0
        assert body["duplicates_found"] == 1
        assert len(body["groups"]) == 1
        assert body["groups"][0]["audit_id"] is None
        assert db.get(KnowledgeEntity, a.id).merged_into_id is None
        assert db.get(KnowledgeEntity, b.id).merged_into_id is None
        assert list(db.query(EntityMergeAudit)) == []

    def test_apply_merges_exactly_the_dry_run_plan(self, client, db):
        a = _entity("Quibdó", EntityType.location, corroboration_count=3)
        b = _entity("Quibdo", EntityType.location)
        c = _entity("Laura C. Hall")
        d = _entity("Laura C Hall")
        lone = _entity("Unrelated")
        _save_entities(db, a, b, c, d, lone)

        dry = client.post("/api/kg/entity-curation/dedupe", json={}).json()
        applied = client.post("/api/kg/entity-curation/dedupe", json={"apply": True}).json()

        # Parity: same groups, same survivors, same absorbed ids.
        strip = lambda g: {k: g[k] for k in ("survivor_id", "absorbed_ids", "basis")}  # noqa: E731
        assert [strip(g) for g in dry["groups"]] == [strip(g) for g in applied["groups"]]
        assert applied["dry_run"] is False
        assert applied["merges_applied"] == 2
        assert all(g["audit_id"] for g in applied["groups"])

        # The merges actually happened, through the audited path.
        assert db.get(KnowledgeEntity, b.id).merged_into_id == a.id
        # The absorbed spelling survives as an alias on the survivor.
        assert "Quibdo" in db.get(KnowledgeEntity, a.id).aliases
        audits = list(db.query(EntityMergeAudit))
        assert len(audits) == 2
        action_audits = [
            row for row in db.query(ActionAudit) if row.action_name == "entity.merge"
        ]
        assert len(action_audits) == 2

        # Re-planning finds nothing left.
        again = client.post("/api/kg/entity-curation/dedupe", json={}).json()
        assert again["groups"] == []

    def test_apply_repoints_claims_to_survivor(self, client, db):
        a = _entity("Quibdó", EntityType.location, corroboration_count=1)
        b = _entity("Quibdo", EntityType.location)
        _save_entities(db, a, b)
        doc = Document(name="Doc", doc_type=DocType.file)
        db.save(doc)
        claim = _claim(
            "About Quibdo", subject_entity_id=None, source_document_id=doc.id
        )
        claim.entity_ids = [b.id]
        db.save(claim)
        r = client.post("/api/kg/entity-curation/dedupe", json={"apply": True})
        assert r.status_code == 200
        assert db.get(KnowledgeClaim, claim.id).entity_ids == [a.id]


class TestClaimDedupeRoute:
    def _seed_duplicate_claims(self, db) -> tuple[KnowledgeClaim, KnowledgeClaim]:
        doc1 = Document(name="Doc 1", doc_type=DocType.file)
        doc2 = Document(name="Doc 2", doc_type=DocType.file)
        db.save(doc1)
        db.save(doc2)
        a = _claim(
            "Marshall arrived at Quibdo.",
            predicate_verb="arrived at",
            object_phrase="Quibdo",
            source_document_id=doc1.id,
        )
        b = _claim(
            "Marshall arrived at Quibdo",
            predicate_verb="arrived at",
            object_phrase="Quibdo.",
            source_document_id=doc2.id,
        )
        db.save(a)
        db.save(b)
        return a, b

    def test_dry_run_then_apply_parity_and_corroboration(self, client, db):
        a, b = self._seed_duplicate_claims(db)
        dry = client.post("/api/kg/claims/dedupe", json={}).json()
        assert dry["dry_run"] is True
        assert dry["duplicates_found"] == 1
        assert list(db.query(ClaimMergeAudit)) == []

        applied = client.post("/api/kg/claims/dedupe", json={"apply": True}).json()
        assert [g["survivor_id"] for g in applied["groups"]] == [
            g["survivor_id"] for g in dry["groups"]
        ]
        assert applied["merges_applied"] == 1

        survivor_id = applied["groups"][0]["survivor_id"]
        absorbed_id = ({a.id, b.id} - {survivor_id}).pop()
        survivor = db.get(KnowledgeClaim, survivor_id)
        absorbed = db.get(KnowledgeClaim, absorbed_id)
        assert absorbed.merged_into_id == survivor_id
        # Two distinct source documents → corroboration incremented to 2.
        assert survivor.corroboration_count == 2
        assert len(list(db.query(ClaimMergeAudit))) == 1

        # Nothing left to plan.
        assert client.post("/api/kg/claims/dedupe", json={}).json()["groups"] == []
