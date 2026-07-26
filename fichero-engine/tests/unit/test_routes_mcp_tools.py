"""Tests for MCP tool adapter routes.

MCP tools provide thin REST wrappers around canonical Knowledge API operations
(entity upsert, claim create, entity/claim CRUD, list). Routes are mounted at
/api/mcp/tools. Tests use the real in-memory DB via the client fixture.
"""

from fastapi.testclient import TestClient

from fichero.security import accounts
from fichero.security import authz
from fichero.api.main import app
from fichero.models.knowledge import (
    KnowledgeEntity,
    KnowledgeClaim,
    ClaimType,
    EpistemicStatus,
    ClaimCurationState,
    EntityType,
)


BASE = "/api/mcp/tools"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(name: str = "Berlin", entity_id: str | None = None) -> KnowledgeEntity:
    return KnowledgeEntity(
        id=entity_id or "ent-1",
        canonical_name=name,
        entity_type=EntityType.location,
    )


def _make_claim(claim_id: str = "claim-1", text: str = "Berlin is in Germany") -> KnowledgeClaim:
    return KnowledgeClaim(
        id=claim_id,
        text=text,
        source_document_id="doc-1",
        source_ids=["doc-1"],
        claim_type=ClaimType.fact,
        epistemic_status=EpistemicStatus.tentative,
        curation_state=ClaimCurationState.unreviewed,
        confidence=0.8,
    )


def _authed_multiuser_client(monkeypatch, app_db, library_path: str, *, role: str = "viewer") -> TestClient:
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    user = app_db.create_user(
        username="mcp-user",
        display_name="MCP User",
        password_hash=accounts.hash_password("password"),
        is_owner=(role == "owner"),
    )
    app_db.set_library_role(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        role=role,
    )
    raw_token = accounts.new_session_token()
    app_db.create_device(
        name="MCP Device",
        user_id=user.id,
        token_hash=accounts.hash_token(raw_token),
    )
    return TestClient(app, headers={"Authorization": f"Bearer {raw_token}"})


# ---------------------------------------------------------------------------
# POST /api/mcp/tools/knowledge/entities/upsert
# ---------------------------------------------------------------------------


class TestMcpEntityUpsert:
    def test_create_entity(self, client):
        r = client.post(f"{BASE}/knowledge/entities/upsert", json={
            "canonical_name": "Paris",
            "entity_type": "location",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["operation"] == "created"
        assert "entity_id" in data

    def test_update_entity(self, client, db):
        entity = _make_entity("Paris", "ent-paris")
        db.save(entity)

        r = client.post(f"{BASE}/knowledge/entities/upsert", json={
            "id": "ent-paris",
            "canonical_name": "Paris, France",
            "entity_type": "location",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["operation"] == "updated"
        assert data["entity_id"] == "ent-paris"

    def test_invalid_entity_type_returns_400(self, client):
        r = client.post(f"{BASE}/knowledge/entities/upsert", json={
            "canonical_name": "Paris",
            "entity_type": "not-a-valid-type",
        })
        assert r.status_code == 400

    def test_extra_field_returns_422(self, client):
        r = client.post(f"{BASE}/knowledge/entities/upsert", json={
            "canonical_name": "Paris",
            "entity_type": "location",
            "unexpected": True,
        })
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/mcp/tools/knowledge/claims/create
# ---------------------------------------------------------------------------


class TestMcpClaimCreate:
    def test_create_claim(self, client):
        r = client.post(f"{BASE}/knowledge/claims/create", json={
            "text": "The Eiffel Tower is in Paris.",
            "source_document_id": "doc-1",
            "claim_type": "fact",
            "epistemic_status": "tentative",
            "curation_state": "unreviewed",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "claim_id" in data

    def test_create_claim_no_source_returns_400(self, client):
        r = client.post(f"{BASE}/knowledge/claims/create", json={
            "text": "No source given.",
            "claim_type": "fact",
        })
        assert r.status_code == 400

    def test_create_claim_invalid_entity_returns_400(self, client):
        r = client.post(f"{BASE}/knowledge/claims/create", json={
            "text": "Links to missing entity.",
            "source_document_id": "doc-1",
            "entity_ids": ["no-such-entity"],
        })
        assert r.status_code == 400

    def test_create_claim_invalid_claim_type_returns_400(self, client):
        r = client.post(f"{BASE}/knowledge/claims/create", json={
            "text": "Bad type.",
            "source_document_id": "doc-1",
            "claim_type": "bad-type",
        })
        assert r.status_code == 400

    def test_extra_field_returns_422(self, client):
        r = client.post(f"{BASE}/knowledge/claims/create", json={
            "text": "The Eiffel Tower is in Paris.",
            "source_document_id": "doc-1",
            "unexpected": True,
        })
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/mcp/tools/knowledge/entities/{entity_id}
# ---------------------------------------------------------------------------


class TestMcpEntityGet:
    def test_get_existing_entity(self, client, db):
        entity = _make_entity("Tokyo", "ent-tokyo")
        db.save(entity)

        r = client.get(f"{BASE}/knowledge/entities/ent-tokyo")
        assert r.status_code == 200
        assert r.json()["canonical_name"] == "Tokyo"

    def test_get_missing_entity_returns_404(self, client):
        r = client.get(f"{BASE}/knowledge/entities/no-such")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/mcp/tools/knowledge/claims/{claim_id}
# ---------------------------------------------------------------------------


class TestMcpClaimGet:
    def test_get_existing_claim(self, client, db):
        claim = _make_claim("claim-42", "Rome was not built in a day.")
        db.save(claim)

        r = client.get(f"{BASE}/knowledge/claims/claim-42")
        assert r.status_code == 200
        assert r.json()["text"] == "Rome was not built in a day."

    def test_get_missing_claim_returns_404(self, client):
        r = client.get(f"{BASE}/knowledge/claims/no-such")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/mcp/tools/knowledge/entities/{entity_id}
# ---------------------------------------------------------------------------


class TestMcpEntityDelete:
    def test_delete_entity(self, client, db):
        entity = _make_entity("Cairo", "ent-cairo")
        db.save(entity)

        r = client.delete(f"{BASE}/knowledge/entities/ent-cairo")
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["operation"] == "deleted"

    def test_delete_missing_entity_returns_404(self, client):
        r = client.delete(f"{BASE}/knowledge/entities/no-such")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/mcp/tools/knowledge/claims/{claim_id}
# ---------------------------------------------------------------------------


class TestMcpClaimDelete:
    def test_delete_claim(self, client, db):
        claim = _make_claim("del-claim", "Claim to delete.")
        db.save(claim)

        r = client.delete(f"{BASE}/knowledge/claims/del-claim")
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["operation"] == "deleted"

    def test_delete_missing_claim_returns_404(self, client):
        r = client.delete(f"{BASE}/knowledge/claims/no-such")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/mcp/tools/knowledge/entities
# ---------------------------------------------------------------------------


class TestMcpEntityList:
    def test_empty_list(self, client):
        r = client.get(f"{BASE}/knowledge/entities")
        assert r.status_code == 200
        data = r.json()
        assert "entities" in data
        assert "total" in data

    def test_returns_entities(self, client, db):
        db.save(_make_entity("London", "ent-london"))
        db.save(_make_entity("Madrid", "ent-madrid"))

        r = client.get(f"{BASE}/knowledge/entities")
        assert r.status_code == 200
        assert r.json()["total"] == 2

    def test_filter_by_query(self, client, db):
        db.save(_make_entity("Amsterdam", "ent-am"))
        db.save(_make_entity("Budapest", "ent-bud"))

        r = client.get(f"{BASE}/knowledge/entities?q=amsterdam")
        assert r.status_code == 200
        assert len(r.json()["entities"]) == 1

    def test_limit_is_bounded(self, client):
        r = client.get(f"{BASE}/knowledge/entities?limit=1000")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/mcp/tools/knowledge/claims
# ---------------------------------------------------------------------------


class TestMcpClaimList:
    def test_empty_list(self, client):
        r = client.get(f"{BASE}/knowledge/claims")
        assert r.status_code == 200
        data = r.json()
        assert "claims" in data
        assert "total" in data

    def test_returns_claims(self, client, db):
        db.save(_make_claim("c-1", "First claim."))
        db.save(_make_claim("c-2", "Second claim."))

        r = client.get(f"{BASE}/knowledge/claims")
        assert r.status_code == 200
        assert r.json()["total"] == 2

    def test_filter_by_text(self, client, db):
        db.save(_make_claim("c-1", "Napoleon was exiled."))
        db.save(_make_claim("c-2", "The moon is round."))

        r = client.get(f"{BASE}/knowledge/claims?q=napoleon")
        assert r.status_code == 200
        assert len(r.json()["claims"]) == 1

    def test_limit_is_bounded(self, client):
        r = client.get(f"{BASE}/knowledge/claims?limit=1000")
        assert r.status_code == 422


class TestMcpToolAuth:
    def test_multiuser_requires_real_auth(self, monkeypatch, app_db, test_package):
        monkeypatch.setenv("FICHERO_MULTIUSER", "1")
        unauth_client = TestClient(app)

        response = unauth_client.get(
            f"{BASE}/knowledge/entities",
            headers={"Authorization": "Bearer wrong-token"},
        )

        assert response.status_code == 401

    def test_multiuser_authenticated_request_succeeds(self, monkeypatch, app_db, test_package):
        authed_client = _authed_multiuser_client(monkeypatch, app_db, str(test_package))

        response = authed_client.get(
            f"{BASE}/knowledge/entities",
            headers={"X-Fichero-Library-Path": str(test_package)},
        )

        assert response.status_code == 200
