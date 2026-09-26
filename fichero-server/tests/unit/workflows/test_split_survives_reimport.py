"""#5072 split: the durable record IS the un-merged row (merged_into_id=None). Re-import and
dedupe must not recombine what a person split. Round trip: real entity.merge, real entity.split,
real _write_kg_rows / plan_entity_dedupe."""

import fichero_server.api.routes.kg_entity_curation  # noqa: F401  (registers entity.merge/split)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.knowledge.dedupe import plan_entity_dedupe
from fichero_server.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity
from fichero_server.workflows.tools.extractors import _write_kg_rows

CTX = ActionContext(actor="ui", library_path="/lib/test.fichero")


def _import(db, name, doc):
    _write_kg_rows(
        db,
        section={"name": "people", "entity_type": EntityType.person},
        items=[{"name": name, "verb": "signed", "object": "the deed"}],
        container_id=doc,
        page_label="1",
        source_excerpt=f"{name} signed the deed.",
    )


class TestSplitSurvivesReimport:
    def _merged_then_split(self, db):
        _import(db, "John Marshall", "doc-a")
        _import(db, "the Major", "doc-a")
        by = {e.canonical_name: e for e in db.query(KnowledgeEntity)}
        registry.invoke(db, "entity.merge", {"absorbing_entity_id": by["John Marshall"].id,
                        "absorbed_entity_ids": [by["the Major"].id]}, CTX)
        registry.invoke(db, "entity.split", {"primary_entity_id": by["John Marshall"].id,
                        "split_off_entity_ids": [by["the Major"].id]}, CTX)
        return by

    def test_reimported_name_attaches_to_the_split_off_entity(self, db):
        by = self._merged_then_split(db)
        _import(db, "the Major", "doc-b")
        (claim,) = [c for c in db.query(KnowledgeClaim) if c.source_document_id == "doc-b"]
        assert claim.subject_entity_id == by["the Major"].id
        assert db.get(KnowledgeEntity, by["the Major"].id).merged_into_id is None

    def test_no_entity_is_recombined_by_reimport_or_dedupe(self, db):
        by = self._merged_then_split(db)
        _import(db, "the Major", "doc-b")
        _import(db, "John Marshall", "doc-b")
        live = [e for e in db.query(KnowledgeEntity) if e.merged_into_id is None]
        assert sorted(e.canonical_name for e in live) == ["John Marshall", "the Major"]
        assert plan_entity_dedupe(live) == []

    def test_alias_the_merge_left_on_the_primary_does_not_pull_the_name_back(self, db):
        _import(db, "John Marshall", "doc-a")
        _import(db, "the Major", "doc-a")
        by = {e.canonical_name: e for e in db.query(KnowledgeEntity)}
        registry.invoke(db, "entity.merge", {"absorbing_entity_id": by["John Marshall"].id,
                        "absorbed_entity_ids": [by["the Major"].id],
                        "merged_aliases": ["the Major"]}, CTX)
        assert "the Major" in db.get(KnowledgeEntity, by["John Marshall"].id).aliases
        registry.invoke(db, "entity.split", {"primary_entity_id": by["John Marshall"].id,
                        "split_off_entity_ids": [by["the Major"].id]}, CTX)
        _import(db, "the Major", "doc-b")
        (claim,) = [c for c in db.query(KnowledgeClaim) if c.source_document_id == "doc-b"]
        assert claim.subject_entity_id == by["the Major"].id
        live = [e for e in db.query(KnowledgeEntity) if e.merged_into_id is None]
        assert plan_entity_dedupe(live) == []
