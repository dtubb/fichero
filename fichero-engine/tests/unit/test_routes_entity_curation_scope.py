"""Scoped entity-reconciliation candidate route coverage (#3318, #3527)."""

from types import SimpleNamespace

import pytest

from fichero.api.routes import kg_entity_curation
from fichero.db import Database
from fichero.models.knowledge import (
    EntityResolutionRule,
    EntityResolutionRuleType,
    EntityType,
    KnowledgeEntity,
)


def test_folder_scope_requires_folder_id(client):
    response = client.get("/api/kg/entity-curation/candidates?scope=folder")

    assert response.status_code == 422
    assert "folder_id is required" in response.json()["detail"]


def test_library_scope_is_the_default(client):
    response = client.get("/api/kg/entity-curation/candidates")

    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}


@pytest.mark.asyncio
async def test_cross_library_scope_matches_open_libraries_and_respects_rules(
    tmp_path, monkeypatch
):
    first_path = str((tmp_path / "First.fichero").resolve())
    second_path = str((tmp_path / "Second.fichero").resolve())
    first = Database(path=tmp_path / "First.fichero" / "fichero.duckdb")
    second = Database(path=tmp_path / "Second.fichero" / "fichero.duckdb")
    first_entity = KnowledgeEntity(canonical_name="Rosario", entity_type=EntityType.person)
    second_entity = KnowledgeEntity(canonical_name="Rosario", entity_type=EntityType.person)
    first.save(first_entity)
    second.save(second_entity)
    databases = {first_path: first, second_path: second}
    monkeypatch.setattr(
        kg_entity_curation.db_manager, "open_library_paths", lambda: list(databases)
    )
    monkeypatch.setattr(
        kg_entity_curation.db_manager, "get_database", databases.__getitem__
    )
    request = SimpleNamespace(
        state=SimpleNamespace(bootstrap_auth=True, user=None)
    )
    try:
        response = await kg_entity_curation.candidate_pairs(
            request=request, scope="cross-library", same_type_only=True, top_k=20, db=first
        )
        assert response.count == 1
        pair = response.items[0]
        assert {pair.entity_a_library_path, pair.entity_b_library_path} == set(databases)
        assert {pair.entity_a_id, pair.entity_b_id} == {first_entity.id, second_entity.id}

        second.save(
            EntityResolutionRule(
                rule_type=EntityResolutionRuleType.suppress,
                match_canonical_name="Rosario",
                match_entity_type=EntityType.person,
                reason="not a reconciliation candidate",
            )
        )
        suppressed = await kg_entity_curation.candidate_pairs(
            request=request, scope="cross-library", same_type_only=True, top_k=20, db=first
        )
        assert suppressed.count == 0
    finally:
        first.conn.close()
        second.conn.close()
