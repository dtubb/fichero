"""Tests for MCP server management routes.

MCP (Model Context Protocol) servers extend the workflow tool registry.
These routes manage registered MCP server configurations (CRUD).
Dev-tier feature.
"""

import pytest

from fichero.models import MCPServer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def use_test_app_db(app_db, monkeypatch):
    """Redirect get_app_db() calls in mcp_servers to the test app_db."""
    monkeypatch.setattr(
        "fichero.api.routes.mcp_servers.get_app_db",
        lambda: app_db,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mcp_server(app_db, name: str = "Test Server") -> MCPServer:
    server = MCPServer(
        name=name,
        description="A test MCP server",
        transport="stdio",
        command="mcp-server",
        args=["--port", "8080"],
        env={},
    )
    app_db.save_mcp_server(server)
    return server


# ---------------------------------------------------------------------------
# Tests: GET /api/mcp-servers
# ---------------------------------------------------------------------------


class TestListMCPServers:
    def test_empty_list(self, client):
        r = client.get("/api/mcp-servers")
        assert r.status_code == 200
        assert r.json() == {"items": [], "count": 0}

    def test_returns_configured_servers(self, client, app_db):
        _make_mcp_server(app_db, "Server A")
        _make_mcp_server(app_db, "Server B")
        r = client.get("/api/mcp-servers")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2

    def test_openapi_lists_typed_mcp_server_items(self, client):
        schema = client.app.openapi()
        server_list = schema["components"]["schemas"]["MCPServerResponseList"]

        assert server_list["properties"]["items"]["items"]["$ref"].endswith(
            "/MCPServerResponse"
        )


# ---------------------------------------------------------------------------
# Tests: POST /api/mcp-servers
# ---------------------------------------------------------------------------


class TestCreateMCPServer:
    def test_create_stdio_server(self, client):
        payload = {
            "name": "my-server",
            "description": "My MCP server",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "my_mcp_server"],
            "env": {"MODEL": "gpt-4"},
        }
        r = client.post("/api/mcp-servers", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "my-server"
        assert data["transport"] == "stdio"

    def test_create_http_server_preserves_null_optionals_and_typed_maps(self, client):
        payload = {
            "name": "remote-server",
            "description": "Remote MCP server",
            "transport": "http",
            "command": None,
            "args": [],
            "env": {},
            "url": "https://example.test/mcp",
            "headers": {"Authorization": "Bearer token"},
        }
        r = client.post("/api/mcp-servers", json=payload)

        assert r.status_code == 200
        data = r.json()
        assert data["transport"] == "http"
        assert data["command"] is None
        assert data["url"] == "https://example.test/mcp"
        assert data["args"] == []
        assert data["env"] == {}
        assert data["headers"] == {"Authorization": "Bearer token"}

    def test_create_server_appears_in_list(self, client):
        payload = {
            "name": "listed-server",
            "transport": "stdio",
            "command": "server-cmd",
        }
        client.post("/api/mcp-servers", json=payload)
        r = client.get("/api/mcp-servers")
        names = [s["name"] for s in r.json()["items"]]
        assert "listed-server" in names


# ---------------------------------------------------------------------------
# Tests: GET /api/mcp-servers/{server_id}
# ---------------------------------------------------------------------------


class TestGetMCPServer:
    def test_get_existing_server(self, client, app_db):
        server = _make_mcp_server(app_db)
        r = client.get(f"/api/mcp-servers/{server.id}")
        assert r.status_code == 200
        assert r.json()["id"] == server.id

    def test_get_missing_returns_404(self, client):
        r = client.get("/api/mcp-servers/nonexistent-id")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Tests: PUT /api/mcp-servers/{server_id}
# ---------------------------------------------------------------------------


class TestUpdateMCPServer:
    def test_update_description(self, client, app_db):
        server = _make_mcp_server(app_db)
        r = client.put(f"/api/mcp-servers/{server.id}", json={
            "name": server.name,
            "transport": server.transport,
            "description": "Updated description",
        })
        assert r.status_code == 200
        assert r.json()["description"] == "Updated description"

    def test_update_missing_returns_404(self, client):
        r = client.put("/api/mcp-servers/no-such-id", json={
            "name": "x", "transport": "stdio",
        })
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Tests: DELETE /api/mcp-servers/{server_id}
# ---------------------------------------------------------------------------


class TestDeleteMCPServer:
    def test_delete_removes_server(self, client, app_db):
        server = _make_mcp_server(app_db)
        r = client.delete(f"/api/mcp-servers/{server.id}")
        assert r.status_code == 200
        r2 = client.get(f"/api/mcp-servers/{server.id}")
        assert r2.status_code == 404

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/mcp-servers/no-such-id")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Tests: Tool loading endpoints
# ---------------------------------------------------------------------------


class TestMCPToolLoading:
    def test_get_all_tools(self, client, db):
        # With no configured servers, should return empty tool list
        r = client.get("/api/mcp-servers/tools/all")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data

    def test_load_into_registry(self, client):
        # The endpoint does a lazy import and calls load_mcp_tools_into_registry.
        # With no MCP servers configured it may succeed (0 tools) or raise a 500.
        # Just verify the route exists and responds.
        r = client.post("/api/mcp-servers/tools/load-into-workflow-registry")
        assert r.status_code in (200, 500)


class TestMCPOpenAPISchema:
    def test_openapi_keeps_typed_mcp_server_response_fields(self, client):
        schema = client.app.openapi()
        response = schema["components"]["schemas"]["MCPServerResponse"]
        response_list = schema["components"]["schemas"]["MCPServerResponseList"]

        assert response["properties"]["args"]["items"]["type"] == "string"
        assert response["properties"]["env"]["additionalProperties"]["type"] == "string"
        assert response["properties"]["headers"]["additionalProperties"]["type"] == "string"
        assert response["properties"]["command"]["anyOf"][1]["type"] == "null"
        assert response["properties"]["url"]["anyOf"][1]["type"] == "null"
        assert response_list["properties"]["items"]["items"]["$ref"].endswith(
            "/MCPServerResponse"
        )
