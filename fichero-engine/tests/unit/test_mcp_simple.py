"""Unit tests for simplified MCP surface (#1327)."""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager

import httpx

from fichero.mcp import simple as mcp_simple
from fichero.cli import FicheroClient

EXPECTED_TOOLS = {
    "health",
    "list_documents",
    "get_document",
    "run_workflow",
    "workflow_status",
    "list_artifacts",
    "kg_search",
    "kg_claims",
    "create_note",
    "list_notes",
}


def _list_tools() -> list:
    return asyncio.run(mcp_simple.mcp.list_tools())


@contextmanager
def _mock_client(monkeypatch, *, handler=None, status=200, body=None):
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

    monkeypatch.setattr(mcp_simple, "_client", _build)
    yield seen


def test_registers_small_stable_tool_surface():
    names = {tool.name for tool in _list_tools()}
    assert names == EXPECTED_TOOLS


def test_tools_have_descriptions_and_schemas():
    for tool in _list_tools():
        assert tool.description
        assert tool.inputSchema is not None


def test_run_workflow_builds_execute_body(monkeypatch):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            202,
            json={
                "thread_id": "t1",
                "workflow_id": "wf-1",
                "workflow_name": "Test",
                "status": "accepted",
                "stream_url": "/api/workflow-execution/stream/t1",
            },
        )

    with _mock_client(monkeypatch, handler=handler):
        mcp_simple.run_workflow(
            mcp_simple.RunWorkflowInput(
                workflow_id="wf-1",
                doc_id="doc-9",
                skip_cache=True,
            )
        )

    assert seen[0] == {
        "workflow_id": "wf-1",
        "inputs": {"files": ["doc-9"]},
        "force_new": False,
        "skip_cache": True,
    }
