"""Enrich preview/import routes + SPARQL-endpoints settings (offline)."""

import pytest
from fastapi import HTTPException

from fichero_server.api.routes.kg import entity_curation as curation
from fichero_server.api.routes.system import settings as settings_routes
from fichero_server.db import Database
from fichero_server.knowledge import wikidata_enrich as we
from fichero_server.models.knowledge import (
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    LibrarySetting,
)


def _linked_entity(db: Database, qid: str = "Q42") -> KnowledgeEntity:
    entity = KnowledgeEntity(canonical_name="Douglas Adams", entity_type=EntityType.person)
    entity.metadata["authority_links"] = [{"authority": "wikidata", "authority_id": qid}]
    db.save(entity)
    return entity


_STATEMENTS = [
    we.WikidataStatement(
        property_id="P569", property_label="date of birth", value_label="1952-03-11"
    ),
    we.WikidataStatement(
        property_id="P19",
        property_label="place of birth",
        value_label="Cambridge",
        value_qid="Q350",
        value_url="http://www.wikidata.org/entity/Q350",
    ),
]


@pytest.mark.asyncio
async def test_preview_is_opt_in(tmp_path):
    db = Database(path=tmp_path / "lib" / "fichero.duckdb")
    try:
        entity = _linked_entity(db)
        with pytest.raises(HTTPException, match="disabled"):
            await curation.enrich_preview(
                curation.EnrichPreviewRequest(entity_id=entity.id), db
            )
    finally:
        db.conn.close()


@pytest.mark.asyncio
async def test_preview_resolves_qid_and_returns_statements(tmp_path, monkeypatch):
    db = Database(path=tmp_path / "lib" / "fichero.duckdb")
    try:
        entity = _linked_entity(db, "Q42")
        db.save(LibrarySetting(id="external_authority_enabled", value="true"))

        captured = {}

        async def fake_fetch(qid, endpoint, **_kwargs):
            captured["qid"] = qid
            captured["endpoint"] = endpoint
            return _STATEMENTS

        monkeypatch.setattr(we, "fetch_statements_sparql", fake_fetch)
        monkeypatch.setattr(
            settings_routes, "resolve_selected_endpoint", lambda _db: "https://ep/sparql"
        )
        monkeypatch.setattr(curation, "get_library_database_for_write", lambda: db, raising=False)
        import fichero_server.db.app as app_db

        monkeypatch.setattr(app_db, "get_app_db", lambda: object())

        result = await curation.enrich_preview(
            curation.EnrichPreviewRequest(entity_id=entity.id), db
        )
        assert captured == {"qid": "Q42", "endpoint": "https://ep/sparql"}
        assert result.qid == "Q42"
        assert result.subject_label == "Douglas Adams"
        assert {s.property_id for s in result.statements} == {"P569", "P19"}
        assert result.statements[0].statement_id
    finally:
        db.conn.close()


@pytest.mark.asyncio
async def test_preview_without_link_needs_qid(tmp_path):
    db = Database(path=tmp_path / "lib" / "fichero.duckdb")
    try:
        entity = KnowledgeEntity(canonical_name="Nobody")
        db.save(entity)
        db.save(LibrarySetting(id="external_authority_enabled", value="true"))
        with pytest.raises(HTTPException, match="No Wikidata QID"):
            await curation.enrich_preview(
                curation.EnrichPreviewRequest(entity_id=entity.id), db
            )
    finally:
        db.conn.close()


@pytest.mark.asyncio
async def test_import_marks_claims_wikidata_sourced(tmp_path):
    db = Database(path=tmp_path / "lib" / "fichero.duckdb")
    try:
        entity = _linked_entity(db, "Q42")
        result = await curation.enrich_import(
            curation.EnrichImportRequest(
                entity_id=entity.id,
                qid="Q42",
                statements=[
                    curation.EnrichImportStatement(
                        property_id="P19",
                        property_label="place of birth",
                        value_label="Cambridge",
                        value_qid="Q350",
                    )
                ],
            ),
            db,
            actor="tester",
        )
        assert result.imported == 1
        claim = db.get(KnowledgeClaim, result.claim_ids[0])
        assert claim.source_document_id is None  # not "the diary says"
        assert claim.created_by == "wikidata"
        assert claim.confidence_source == "wikidata"
        assert claim.metadata["authority"] == "wikidata"
        assert claim.metadata["authority_id"] == "Q42"
        assert claim.entity_ids == [entity.id]
        assert claim.text == "Douglas Adams — place of birth: Cambridge"
        assert claim.subject_entity_id == entity.id
    finally:
        db.conn.close()


# --- SPARQL-endpoints settings ---------------------------------------------


class _FakeAppDB:
    def __init__(self):
        self._store: dict[str, str] = {}

    def get_setting(self, key):
        return self._store.get(key)

    def set_setting(self, key, value):
        self._store[key] = value


def test_sparql_endpoints_default_when_unset():
    config = settings_routes.load_sparql_endpoints(_FakeAppDB())
    assert config.selected_url == we.DEFAULT_WIKIDATA_SPARQL_ENDPOINT
    assert config.endpoints[0].url == we.DEFAULT_WIKIDATA_SPARQL_ENDPOINT


def test_sparql_endpoints_malformed_falls_back_to_default():
    db = _FakeAppDB()
    db.set_setting("sparql_endpoints", "{not json")
    assert (
        settings_routes.resolve_selected_endpoint(db) == we.DEFAULT_WIKIDATA_SPARQL_ENDPOINT
    )


def test_put_sparql_endpoints_keeps_default_and_persists(monkeypatch):
    db = _FakeAppDB()
    import fichero_server.db.app as app_db

    monkeypatch.setattr(app_db, "get_app_db", lambda: db)

    body = settings_routes.SparqlEndpointsConfig(
        endpoints=[settings_routes.SparqlEndpoint(name="Local", url="http://localhost:9999/sparql")],
        selected_url="http://localhost:9999/sparql",
    )
    saved = settings_routes.set_sparql_endpoints(body, request=None, _owner=None)
    # Wikidata default is always kept present, even though the caller omitted it.
    assert any(e.url == we.DEFAULT_WIKIDATA_SPARQL_ENDPOINT for e in saved.endpoints)
    assert saved.selected_url == "http://localhost:9999/sparql"
    # Round-trips through the store.
    assert settings_routes.resolve_selected_endpoint(db) == "http://localhost:9999/sparql"


def test_put_sparql_endpoints_rejects_unknown_selection(monkeypatch):
    db = _FakeAppDB()
    import fichero_server.db.app as app_db

    monkeypatch.setattr(app_db, "get_app_db", lambda: db)
    body = settings_routes.SparqlEndpointsConfig(endpoints=[], selected_url="http://evil/sparql")
    saved = settings_routes.set_sparql_endpoints(body, request=None, _owner=None)
    assert saved.selected_url == we.DEFAULT_WIKIDATA_SPARQL_ENDPOINT
