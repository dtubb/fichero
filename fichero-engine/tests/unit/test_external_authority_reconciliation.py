"""Cached, opt-in external authority reconciliation (#3528)."""

import pytest
from fastapi import HTTPException

from fichero.api.routes import kg_entity_curation as curation
from fichero.db import Database
from fichero.models.knowledge import (
    AuthoritySnapshot,
    EntityType,
    KnowledgeEntity,
    LibrarySetting,
)


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
async def test_viaf_and_loc_refresh_parse_mocked_responses(monkeypatch):
    async def fake_json(name, *_args):
        if name == "VIAF":
            return {"result": [{"viafid": "123", "term": "Rosario", "nametype": "Personal"}]}
        return {"hits": [{"uri": "https://id.loc.gov/authorities/names/n123", "a": "Rosario"}]}

    monkeypatch.setattr(curation, "_authority_json", fake_json)
    viaf = await curation._fetch_viaf_snapshots("Rosario", 1)
    loc = await curation._fetch_loc_snapshots("Rosario", 1)

    assert [(row.authority, row.authority_id) for row in viaf + loc] == [
        ("viaf", "123"), ("loc", "n123")
    ]


@pytest.mark.asyncio
async def test_refresh_is_opt_in_and_cache_only_matching(tmp_path, monkeypatch):
    enabled_db = Database(path=tmp_path / "enabled" / "fichero.duckdb")
    disabled_db = Database(path=tmp_path / "disabled" / "fichero.duckdb")
    entity = KnowledgeEntity(canonical_name="Douglas Adams", entity_type=EntityType.person)
    enabled_db.save(entity)
    enabled_db.save(LibrarySetting(id="external_authority_enabled", value="true"))
    monkeypatch.setattr(curation, "_fetch_authority_snapshots", lambda *_args: pytest.fail("network must be blocked"))
    try:
        assert not (await curation.get_external_authority_settings(disabled_db)).external_authority_enabled
        with pytest.raises(HTTPException, match="disabled"):
            await curation.refresh_external_authority(
                curation.AuthorityRefreshRequest(query="Douglas Adams"), disabled_db
            )

        async def fake_fetch(*_args):
            return [
                AuthoritySnapshot(
                    authority="wikidata", authority_id="Q42", label="Douglas Adams",
                    aliases=["D. Adams"], source_url="https://www.wikidata.org/wiki/Q42",
                )
            ]

        monkeypatch.setattr(curation, "_fetch_authority_snapshots", fake_fetch)
        refreshed = await curation.refresh_external_authority(
            curation.AuthorityRefreshRequest(query="Douglas Adams"), enabled_db
        )
        assert refreshed.count == 1
        assert enabled_db.query(AuthoritySnapshot)[0].authority_id == "Q42"
        assert disabled_db.query(AuthoritySnapshot) == []

        matched = await curation.candidate_pairs(
            request=None, scope="external-authority",
            entity_id=entity.id, same_type_only=True, top_k=20, db=enabled_db,
        )
        assert matched.items[0]["authority_id"] == "Q42"
    finally:
        enabled_db.conn.close()
        disabled_db.conn.close()


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

        monkeypatch.setattr(curation, "_fetch_authority_snapshots", failing_fetch)
        monkeypatch.setattr(curation, "_external_authority_enabled", lambda *_args: True)
        with pytest.raises(HTTPException, match="timeout"):
            await curation.refresh_external_authority(
                curation.AuthorityRefreshRequest(query="Rosario"), db
            )
    finally:
        db.conn.close()
