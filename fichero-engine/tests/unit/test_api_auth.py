from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fichero.api.auth import attach_auth_middleware


def _app_with_auth() -> FastAPI:
    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    @app.get("/docs/")
    async def docs_index():
        return {"docs": True}

    @app.get("/api/private")
    async def private():
        return {"private": True}

    attach_auth_middleware(app, "test-token")
    return app


def test_docs_subpath_is_unauthenticated():
    client = TestClient(_app_with_auth())
    response = client.get("/docs/")
    assert response.status_code == 200
    assert response.json() == {"docs": True}


def test_private_endpoint_still_requires_bearer_token():
    client = TestClient(_app_with_auth())
    no_auth = client.get("/api/private")
    assert no_auth.status_code == 401

    authed = client.get(
        "/api/private",
        headers={"Authorization": "Bearer test-token"},
    )
    assert authed.status_code == 200
