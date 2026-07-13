"""Cached, opt-in external authority reconciliation (#3528)."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from fichero.api.routes import kg_entity_curation as curation
from fichero.db import Database
from fichero.knowledge_models import AuthoritySnapshot, EntityType, KnowledgeEntity


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {"search": [{"id": "Q42", "label": "Douglas Adams", "aliases": ["D. Adams"]}]}


class _Client:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, *_args, **_kwargs):
        return _Response()


@pytest.mark.asyncio
async def test_wikidata_refresh_parses_mocked_response(monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: _Client())
    rows = await curation._fetch_wikidata_snapshots("Douglas Adams", 1)

    assert [(row.authority, row.authority_id, row.label) for row in rows] == [
        ("wikidata", "Q42", "Douglas Adams")
    ]


@pytest.mark.asyncio
async def test_refresh_is_opt_in_and_cache_only_matching(tmp_path, monkeypatch):
    db = Database(path=tmp_path / "library" / "fichero.duckdb")
    entity = KnowledgeEntity(canonical_name="Douglas Adams", entity_type=EntityType.person)
    db.save(entity)
    settings = SimpleNamespace(get_setting=lambda _key: None)
    monkeypatch.setattr(curation, "get_app_db", lambda: settings)
    monkeypatch.setattr(curation, "_fetch_wikidata_snapshots", lambda *_args: pytest.fail("network must be blocked"))
    try:
        with pytest.raises(HTTPException, match="disabled"):
            await curation.refresh_external_authority(
                curation.AuthorityRefreshRequest(query="Douglas Adams"), db
            )

        async def fake_fetch(*_args):
            return [
                AuthoritySnapshot(
                    authority="wikidata", authority_id="Q42", label="Douglas Adams",
                    aliases=["D. Adams"], source_url="https://www.wikidata.org/wiki/Q42",
                )
            ]

        settings.get_setting = lambda _key: "true"
        monkeypatch.setattr(curation, "_fetch_wikidata_snapshots", fake_fetch)
        refreshed = await curation.refresh_external_authority(
            curation.AuthorityRefreshRequest(query="Douglas Adams"), db
        )
        assert refreshed.count == 1
        assert db.query(AuthoritySnapshot)[0].authority_id == "Q42"

        matched = await curation.candidate_pairs(
            request=SimpleNamespace(state=SimpleNamespace()), scope="external-authority",
            entity_id=entity.id, same_type_only=True, top_k=20, db=db,
        )
        assert matched.items[0]["authority_id"] == "Q42"
    finally:
        db.conn.close()


@pytest.mark.asyncio
async def test_authority_link_is_persisted_and_refresh_failure_is_loud(tmp_path, monkeypatch):
    db = Database(path=tmp_path / "library" / "fichero.duckdb")
    entity = KnowledgeEntity(canonical_name="Rosario")
    db.save(entity)
    db.save(AuthoritySnapshot(
        authority="wikidata", authority_id="Q1", label="Rosario",
        source_url="https://www.wikidata.org/wiki/Q1",
    ))
    try:
        audit = await curation.link_external_authority(
            curation.AuthorityLinkRequest(entity_id=entity.id, authority="wikidata", authority_id="Q1"), db
        )
        assert audit.operation_type.value == "authority_link"
        assert db.get(KnowledgeEntity, entity.id).metadata["authority_links"] == [
            {"authority": "wikidata", "authority_id": "Q1"}
        ]

        async def failing_fetch(*_args):
            raise HTTPException(status_code=502, detail="Wikidata refresh failed: timeout")

        monkeypatch.setattr(curation, "_fetch_wikidata_snapshots", failing_fetch)
        monkeypatch.setattr(curation, "_external_authority_enabled", lambda: True)
        with pytest.raises(HTTPException, match="timeout"):
            await curation.refresh_external_authority(
                curation.AuthorityRefreshRequest(query="Rosario"), db
            )
    finally:
        db.conn.close()
