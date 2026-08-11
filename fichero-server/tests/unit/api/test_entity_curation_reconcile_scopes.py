"""Cross-cutting reconciliation scope hardening (#3636)."""

from types import SimpleNamespace

import networkx as nx
import pytest

from fichero_server.api.routes import kg_entity_curation
from fichero_server.api.routes.kg_entity_curation import EntityMergeRequest, merge_entities_impl
from fichero_server.db import Database
from fichero_server.models.knowledge import (
    EntityCurationState,
    EntityResolutionRule,
    EntityResolutionRuleType,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)


def _request():
    return SimpleNamespace(state=SimpleNamespace(bootstrap_auth=True, user=None))


def _seed_graph_pair(db: Database) -> tuple[KnowledgeEntity, KnowledgeEntity]:
    first = KnowledgeEntity(id="first", canonical_name="Alice", entity_type=EntityType.person)
    second = KnowledgeEntity(id="second", canonical_name="Alicia", entity_type=EntityType.person)
    place = KnowledgeEntity(id="place", canonical_name="Paris", entity_type=EntityType.location)
    organisation = KnowledgeEntity(id="org", canonical_name="Archive", entity_type=EntityType.organization)
    for entity in (first, second, place, organisation):
        db.save(entity)
    db.save(KnowledgeClaim(id="c1", text="one", source_document_id="page", entity_ids=["first", "place"]))
    db.save(KnowledgeClaim(id="c2", text="two", source_document_id="page", entity_ids=["first", "org"]))
    db.save(KnowledgeClaim(id="c3", text="three", source_document_id="page", entity_ids=["second", "place"]))
    db.save(KnowledgeClaim(id="c4", text="four", source_document_id="page", entity_ids=["second", "org"]))
    return first, second


def _graph(_db: Database) -> nx.Graph:
    graph = nx.Graph()
    graph.add_edges_from(
        [("first", "place"), ("first", "org"), ("second", "place"), ("second", "org")]
    )
    return graph


async def _candidates(db: Database, *, scope: str, folder_id: str | None = None):
    return await kg_entity_curation.candidate_pairs(
        request=_request(),
        min_jaccard=0.5,
        top_k=20,
        same_type_only=True,
        scope=scope,
        folder_id=folder_id,
        db=db,
    )


@pytest.mark.asyncio
async def test_library_and_folder_scopes_apply_rules_and_rejected_state(tmp_path, monkeypatch):
    db = Database(path=tmp_path / "library.fichero" / "fichero.duckdb")
    first, _ = _seed_graph_pair(db)
    monkeypatch.setattr("fichero_server.knowledge.graph.build_full_cooccurrence", _graph)
    monkeypatch.setattr("fichero_server.api.routes.claim.claims._descendant_doc_ids", lambda *_: {"page"})
    try:
        assert (await _candidates(db, scope="library")).count == 1
        assert (await _candidates(db, scope="folder", folder_id="folder")).count == 1

        db.save(EntityResolutionRule(
            rule_type=EntityResolutionRuleType.suppress,
            match_canonical_name="Alice",
            match_entity_type=EntityType.person,
            reason="known distinct",
        ))
        assert (await _candidates(db, scope="library")).count == 0
        assert (await _candidates(db, scope="folder", folder_id="folder")).count == 0

        db.delete(db.query(EntityResolutionRule)[0])
        first.curation_state = EntityCurationState.rejected
        db.save(first)
        assert (await _candidates(db, scope="library")).count == 0
        assert (await _candidates(db, scope="folder", folder_id="folder")).count == 0
    finally:
        db.conn.close()


@pytest.mark.asyncio
async def test_cross_library_scope_is_open_only_and_rule_aware(tmp_path, monkeypatch):
    first_path = str((tmp_path / "First.fichero").resolve())
    second_path = str((tmp_path / "Second.fichero").resolve())
    closed_path = str((tmp_path / "Closed.fichero").resolve())
    first = Database(path=tmp_path / "First.fichero" / "fichero.duckdb")
    second = Database(path=tmp_path / "Second.fichero" / "fichero.duckdb")
    closed = Database(path=tmp_path / "Closed.fichero" / "fichero.duckdb")
    first.save(KnowledgeEntity(id="open-a", canonical_name="Rosario", entity_type=EntityType.person))
    second.save(KnowledgeEntity(id="open-b", canonical_name="Rosario", entity_type=EntityType.person))
    closed.save(KnowledgeEntity(id="closed", canonical_name="Rosario", entity_type=EntityType.person))
    open_databases = {first_path: first, second_path: second}
    monkeypatch.setattr(kg_entity_curation.db_manager, "open_library_paths", lambda: list(open_databases))
    monkeypatch.setattr(kg_entity_curation.db_manager, "get_database", open_databases.__getitem__)
    try:
        candidates = await _candidates(first, scope="cross-library")
        assert candidates.count == 1
        assert closed_path not in {
            candidates.items[0].entity_a_library_path,
            candidates.items[0].entity_b_library_path,
        }

        second.save(EntityResolutionRule(
            rule_type=EntityResolutionRuleType.suppress,
            match_canonical_name="Rosario",
            match_entity_type=EntityType.person,
            reason="known distinct",
        ))
        assert (await _candidates(first, scope="cross-library")).count == 0
        monkeypatch.setattr(kg_entity_curation.db_manager, "open_library_paths", lambda: [first_path])
        assert (await _candidates(first, scope="cross-library")).count == 0
    finally:
        first.conn.close()
        second.conn.close()
        closed.conn.close()


def test_confirmed_merge_persists_and_is_idempotent(tmp_path):
    db = Database(path=tmp_path / "library.fichero" / "fichero.duckdb")
    survivor = KnowledgeEntity(id="survivor", canonical_name="Rosario", entity_type=EntityType.person)
    absorbed = KnowledgeEntity(id="absorbed", canonical_name="Rosario R.", entity_type=EntityType.person)
    db.save(survivor)
    db.save(absorbed)
    try:
        first_audit, _, _ = merge_entities_impl(
            db, EntityMergeRequest(absorbing_entity_id=survivor.id, absorbed_entity_ids=[absorbed.id])
        )
        second_audit, _, _ = merge_entities_impl(
            db, EntityMergeRequest(absorbing_entity_id=survivor.id, absorbed_entity_ids=[absorbed.id])
        )
        assert db.get(KnowledgeEntity, absorbed.id).merged_into_id == survivor.id
        assert db.get(type(first_audit), first_audit.id) is not None
        assert db.get(type(second_audit), second_audit.id) is not None
    finally:
        db.conn.close()
