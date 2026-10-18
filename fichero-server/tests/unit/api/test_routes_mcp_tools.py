"""Auth on the MCP tool adapter route (`POST /api/mcp/tools/check/verdicts`), the one that remains after the
knowledge wrappers were retired (#1439). Tests use the real in-memory DB via the client fixture."""

from fastapi.testclient import TestClient

from fichero_server.security import accounts
from fichero_server.security import authz
from fichero_server.api.main import app

BASE = "/api/mcp/tools"
VERDICT = {"layer": "readings", "target_id": "nope", "verdict": "confirm", "reasons": "reads so"}


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


class TestMcpToolAuth:
    def test_multiuser_requires_real_auth(self, monkeypatch, app_db, test_package):
        monkeypatch.setenv("FICHERO_MULTIUSER", "1")
        unauth_client = TestClient(app)

        response = unauth_client.post(
            f"{BASE}/check/verdicts", json=VERDICT, headers={"Authorization": "Bearer wrong-token"}
        )

        assert response.status_code == 401

    def test_multiuser_authenticated_request_is_not_refused_as_unauthenticated(self, monkeypatch, app_db, test_package):
        authed_client = _authed_multiuser_client(monkeypatch, app_db, str(test_package))

        response = authed_client.post(
            f"{BASE}/check/verdicts", json=VERDICT, headers={"X-Fichero-Library-Path": str(test_package)}
        )

        assert response.status_code != 401
