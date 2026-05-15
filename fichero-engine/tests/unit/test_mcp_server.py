"""Unit tests for the Fichero MCP server.

The MCP server is a thin wrapper over ``FicheroClient``; these tests cover tool
registration and argument passthrough with the HTTP layer mocked
(``httpx.MockTransport``) — no live backend required.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager

import httpx
import pytest

from fichero import mcp_server
from fichero.cli import FicheroClient, FicheroError

# Every tool the server is expected to expose — one per `fichero` CLI command.
EXPECTED_TOOLS = {
    "fichero_health",
    "fichero_import",
    "fichero_docs_list",
    "fichero_docs_get",
    "fichero_workflow_list",
    "fichero_workflow_run",
    "fichero_workflow_status",
    "fichero_artifacts",
    "fichero_kg_entities",
    "fichero_kg_claims",
    "fichero_kg_search",
    "fichero_search",
    "fichero_activity",
}


def _list_tools() -> list:
    return asyncio.run(mcp_server.mcp.list_tools())


@contextmanager
def _mock_client(monkeypatch, *, handler=None, status=200, body=None):
    """Patch mcp_server._client to return a MockTransport-backed FicheroClient.

    Yields the list of seen httpx.Request objects.
    """
    seen: list[httpx.Request] = []

    def _default_handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={"ok": True} if body is None else body)

    transport = httpx.MockTransport(handler or _default_handler)

    def _build() -> FicheroClient:
        return FicheroClient(
            base_url="http://test",
            library_path="/tmp/Lib.fichero",
            token="test-token",
            transport=transport,
        )

    monkeypatch.setattr(mcp_server, "_client", _build)
    yield seen


# -- tool registration -----------------------------------------------------
def test_all_expected_tools_are_registered():
    names = {tool.name for tool in _list_tools()}
    assert names == EXPECTED_TOOLS


def test_no_stale_tools_remain():
    """The old divergent surface (mind-palace, hermeneutics, research...) is gone."""
    names = {tool.name for tool in _list_tools()}
    for stale in (
        "fichero_mp_create_room",
        "fichero_hm_list_frameworks",
        "fichero_run_chain",
    ):
        assert stale not in names


def test_tools_have_descriptions_and_schemas():
    for tool in _list_tools():
        assert tool.description, f"{tool.name} has no description"
        assert tool.inputSchema is not None


# -- argument passthrough --------------------------------------------------
def test_health_hits_health_endpoint(monkeypatch):
    with _mock_client(monkeypatch) as seen:
        mcp_server.fichero_health()
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/health"


def test_workflow_list_hits_workflows_endpoint(monkeypatch):
    with _mock_client(monkeypatch) as seen:
        mcp_server.fichero_workflow_list()
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/workflows"


def test_docs_get_builds_path(monkeypatch):
    with _mock_client(monkeypatch) as seen:
        mcp_server.fichero_docs_get("doc-42")
    assert seen[0].url.path == "/api/documents/doc-42"


def test_docs_list_passes_filters(monkeypatch):
    with _mock_client(monkeypatch) as seen:
        mcp_server.fichero_docs_list(doc_type="pdf", limit=5)
    params = dict(seen[0].url.params)
    assert params == {"doc_type": "pdf", "limit": "5", "offset": "0"}


def test_workflow_run_builds_execute_body(monkeypatch):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(202, json={"thread_id": "t1"})

    with _mock_client(monkeypatch, handler=handler):
        mcp_server.fichero_workflow_run("wf-1", "doc-9", skip_cache=True)
    assert seen[0] == {
        "workflow_id": "wf-1",
        "inputs": {"files": ["doc-9"]},
        "force_new": False,
        "skip_cache": True,
    }


def test_workflow_status_builds_path(monkeypatch):
    with _mock_client(monkeypatch) as seen:
        mcp_server.fichero_workflow_status("thread-7")
    assert seen[0].url.path == "/api/workflow-execution/threads/thread-7/status"


def test_artifacts_builds_path_and_params(monkeypatch):
    with _mock_client(monkeypatch) as seen:
        mcp_server.fichero_artifacts("doc-3", artifact_type="catalogue", limit=10)
    assert seen[0].url.path == "/api/artifacts/document/doc-3"
    assert dict(seen[0].url.params)["artifact_type"] == "catalogue"


def test_kg_search_passes_query_param(monkeypatch):
    with _mock_client(monkeypatch) as seen:
        mcp_server.fichero_kg_search("migration", limit=10)
    assert dict(seen[0].url.params) == {"q": "migration", "limit": "10"}


def test_search_builds_post_body(monkeypatch):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"results": []})

    with _mock_client(monkeypatch, handler=handler):
        mcp_server.fichero_search("ledgers", limit=3)
    assert seen[0]["query"] == "ledgers"
    assert seen[0]["limit"] == 3
    assert seen[0]["search_type"] == "hybrid"
    assert seen[0]["min_score"] == 0.3


def test_import_sends_multipart(monkeypatch, tmp_path):
    sample = tmp_path / "note.txt"
    sample.write_text("hello")
    with _mock_client(monkeypatch) as seen:
        mcp_server.fichero_import(str(sample), parent_id="folder-1")
    assert seen[0].url.path == "/api/documents/import"
    assert dict(seen[0].url.params) == {"parent_id": "folder-1"}
    assert "multipart/form-data" in seen[0].headers["content-type"]


def test_auth_and_library_headers_are_set(monkeypatch):
    with _mock_client(monkeypatch) as seen:
        mcp_server.fichero_activity()
    assert seen[0].headers["authorization"] == "Bearer test-token"
    assert seen[0].headers["x-fichero-library-path"] == "/tmp/Lib.fichero"


# -- error propagation -----------------------------------------------------
def test_backend_error_propagates_not_swallowed(monkeypatch):
    """A non-2xx response must raise, not return a silent {"error": ...} dict."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with _mock_client(monkeypatch, handler=handler):
        with pytest.raises(FicheroError, match="500"):
            mcp_server.fichero_health()


def test_connect_failure_propagates(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with _mock_client(monkeypatch, handler=handler):
        with pytest.raises(FicheroError, match="Is the engine running"):
            mcp_server.fichero_health()


# -- config wiring ---------------------------------------------------------
def test_client_uses_config_base_url(monkeypatch):
    monkeypatch.setitem(mcp_server._CONFIG, "base_url", "http://configured:9000")
    monkeypatch.setitem(mcp_server._CONFIG, "library_path", "/cfg/Lib.fichero")
    client = mcp_server._client()
    try:
        assert client.base_url == "http://configured:9000"
        assert client.library_path == "/cfg/Lib.fichero"
    finally:
        client.close()


def test_main_populates_config_from_args(monkeypatch):
    # This test only checks arg -> _CONFIG wiring. main() also runs a no-token
    # startup probe; a test asserting that warning must patch _TOKEN_PATH and
    # FICHERO_API_KEY (see test_mcp_warns_without_token in test_integration_security).
    captured: dict = {}
    monkeypatch.setattr(
        mcp_server.mcp, "run", lambda *a, **k: captured.setdefault("ran", True)
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "fichero-mcp",
            "--api-url",
            "http://cli:1234",
            "--library-path",
            "/cli/L.fichero",
        ],
    )
    monkeypatch.setitem(mcp_server._CONFIG, "base_url", None)
    monkeypatch.setitem(mcp_server._CONFIG, "library_path", None)
    mcp_server.main()
    assert captured["ran"] is True
    assert mcp_server._CONFIG["base_url"] == "http://cli:1234"
    assert mcp_server._CONFIG["library_path"] == "/cli/L.fichero"
