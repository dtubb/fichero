"""Unit tests for the Fichero MCP server.

The MCP server is a thin wrapper over ``FicheroClient``; these tests cover tool
registration and argument passthrough with the HTTP layer mocked
(``httpx.MockTransport``) — no live backend required.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager

import httpx
import pytest

from fichero_mcp import server as mcp_server
from fichero_cli import FicheroClient, FicheroError

# The hand-written tools left after #5453 retired every tool a generated one covers: each does
# something a single route does not (see each docstring's "Kept" line). Everything else on the
# surface is generated from the contract or an operator alias of a generated tool.
HAND_WRITTEN_TOOLS = {
    "fichero_health",
    "fichero_use_library",
    "fichero_docs_list",
    "fichero_workflow_list",
    "fichero_page_import",
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
def test_the_hand_written_tools_are_registered_beside_the_generated_ones():
    """WHY: the default surface is the hand-written few, the default toolsets' generated tools
    and the operator aliases; a hand-written tool going missing breaks an agent's configuration."""
    names = {tool.name for tool in _list_tools()}
    assert HAND_WRITTEN_TOOLS <= names
    assert set(mcp_server.OPERATOR_ALIASES) <= names

def test_no_stale_tools_remain():
    """Surfaces with no FicheroClient backing stay gone (hermeneutics, research,
    chains). Mind Palace is back (#1269) because the client now wraps its routes."""
    names = {tool.name for tool in _list_tools()}
    for stale in (
        "fichero_hm_list_frameworks",
        "fichero_rs_list_agents",
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
    # list_workflows() returns list[WorkflowResponse]; mock serves a list shape.
    with _mock_client(monkeypatch, body=[]) as seen:
        mcp_server.fichero_workflow_list()
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/workflows"


def _workflow_item(workflow_id: str, name: str, **overrides) -> dict:
    """One item as /api/workflows actually serves it."""
    item = {
        "id": workflow_id,
        "name": name,
        "description": "",
        "provider": "",
        "model": "",
        "format": "nodes",
        "nodes": [],
        "edges": [],
        "folder_path": "/",
        "sort_order": 0,
        "untested": False,
        "direct_runnable": True,
        "accepts_model_override": True,
        "requires_vision": False,
    }
    item.update(overrides)
    return item


def test_workflow_list_tells_the_agent_what_it_cannot_run(monkeypatch):
    """#3804: the engine refuses to run an internal component standalone. The
    list parsed items into the STORAGE model, which has no direct_runnable, so
    Pydantic dropped the refusal and an agent reading this tool saw only names
    — every one of which looked runnable. An agent cannot be expected to obey
    a rule it is never shown."""
    body = [
        _workflow_item("wf-parent", "Transcribe Spanish Script", requires_vision=True),
        _workflow_item("wf-child", "Spanish Script Passes", direct_runnable=False),
    ]
    with _mock_client(monkeypatch, body=body):
        workflows = mcp_server.fichero_workflow_list()

    assert len(workflows) == 2, "fixture must contain a runnable AND a component"
    # #4983-adjacent fix: `fichero_workflow_list` returns LEAN DICTS, not
    # model objects — deliberate since Aug 27 2026 (`e90907d0f`, "lean list
    # payloads"): the full node/edge dump was 450KB, the same reason
    # `fichero_docs_list` slims to dicts too (both tools are
    # JSON-serialisable summaries an agent reads, not typed objects). This
    # test predates that refactor (written for #3804, Aug 3) and was never
    # updated to the dict contract — the code is right, the test was stale.
    by_name = {w["name"]: w for w in workflows}
    assert by_name["Spanish Script Passes"]["direct_runnable"] is False
    assert by_name["Transcribe Spanish Script"]["direct_runnable"] is True
    assert by_name["Transcribe Spanish Script"]["requires_vision"] is True


def test_docs_list_passes_filters(monkeypatch):
    # list_documents() returns list[Document]; mock serves a list shape.
    with _mock_client(monkeypatch, body=[]) as seen:
        mcp_server.fichero_docs_list(doc_type="pdf", limit=5)
    params = dict(seen[0].url.params)
    assert params == {"doc_type": "pdf", "limit": "5", "offset": "0"}


def test_page_import_posts_the_file_and_hands_back_what_landed(monkeypatch, tmp_path):
    """`source.format.everywhere`'s other direction. The agent is handed the RECOGNISED
    format and the repair count, not a success flag: a model told only that the import
    worked will describe a page as cleanly imported when forty of its boxes were
    repaired."""
    source = tmp_path / "folio.xml"
    source.write_text("<PcGts/>", encoding="utf-8")
    body = {"pass_id": "p9", "format": "pagexml", "segments": 812, "readings": 806,
            "order_entries": 812, "checksum": "abc123", "geometry_problems": 40}
    with _mock_client(monkeypatch, body=body) as seen:
        out = mcp_server.fichero_page_import("d1", str(source), format="pagexml", name="theirs")
    assert seen[0].url.path == "/api/documents/d1/import"
    assert dict(seen[0].url.params) == {"format": "pagexml", "name": "theirs"}
    assert seen[0].method == "POST"
    assert out["format"] == "pagexml" and out["geometry_problems"] == 40
    assert out["pass_id"] == "p9"


def test_use_library_takes_a_project_name_as_the_sidebar_shows_it(monkeypatch):
    """#5567: an operator had to find the .fichero path; the name a person sees is enough. The
    engine resolves it, and the session then sends that project's path with every call."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/registry/resolve":
            return httpx.Response(200, json={"path": "/Users/x/Istmina Full.fichero", "name": "Istmina Full"})
        return httpx.Response(200, json=[])

    seen: list[httpx.Request] = []
    with _mock_client(monkeypatch, handler=handler):
        out = mcp_server.fichero_use_library("Istmina Full")
    assert out == {"library_path": "/Users/x/Istmina Full.fichero", "status": "selected"}
    assert dict(seen[0].url.params) == {"name": "Istmina Full"}
    assert seen[1].url.path == "/api/documents"
    assert mcp_server._CONFIG["library_path"] == "/Users/x/Istmina Full.fichero"


def test_use_library_refuses_an_unknown_name_with_the_engine_s_sentence(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "No known project is called 'Istmina'. Known: ['Istmina Full']"})

    with _mock_client(monkeypatch, handler=handler):
        with pytest.raises(Exception, match="Istmina Full"):
            mcp_server.fichero_use_library("Istmina")
    assert mcp_server._CONFIG["library_path"] is None


def test_use_library_still_takes_a_path_without_asking_the_registry(monkeypatch):
    with _mock_client(monkeypatch, body=[]) as seen:
        mcp_server.fichero_use_library("/tmp/Lib.fichero")
    assert [r.url.path for r in seen] == ["/api/documents"]


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

