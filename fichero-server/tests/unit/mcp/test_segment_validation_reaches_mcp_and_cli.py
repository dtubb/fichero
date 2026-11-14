"""The page's segment problems reach an agent and the command line as the app gets them.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.validate-before-export` ("MCP and the CLI
get the same list"). The MCP tool and the CLI command are generated from the one route; driven here against the real
app, each must answer exactly what the route answers, a problem included.
"""
from __future__ import annotations

import json

import httpx

from fichero_cli import FicheroClient
from tests.unit.api.test_segments_validate import _box, _page, _segment
from tests.unit.mcp.test_generated_mcp_tools_reach_the_engine import (  # noqa: F401 (the fixture)
    _call,
    _payload,
    mcp_on_the_real_app,
)


def _page_with_a_problem(db, client):
    doc, pass_id = _page(db, client)
    _segment(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.8, 0.05))  # a line with no baseline
    return doc


def test_the_mcp_tool_answers_the_routes_problems(mcp_on_the_real_app, client, db):  # noqa: F811
    doc = _page_with_a_problem(db, client)
    expected = client.get(f"/api/segments/document/{doc.id}/validate").json()
    assert expected["problems"], "the page has something to fix"

    result = _call(mcp_on_the_real_app, "fichero_segments_validate_document", {"doc_id": doc.id})
    assert result.isError is False, result.content
    assert _payload(result) == expected


def test_the_cli_command_answers_the_routes_problems(client, db, test_package, monkeypatch):
    from typer.testing import CliRunner

    from fichero_cli import __main__ as cli

    doc = _page_with_a_problem(db, client)

    def forward(request: httpx.Request) -> httpx.Response:
        answered = client.request(request.method, request.url.path, params=dict(request.url.params))
        return httpx.Response(answered.status_code, content=answered.content,
                              headers={"content-type": "application/json"})

    def on_the_real_app(*args, **kwargs):
        return FicheroClient(*args, **{**kwargs, "transport": httpx.MockTransport(forward)})

    monkeypatch.setattr(cli, "FicheroClient", on_the_real_app)
    result = CliRunner().invoke(cli.app, ["--json", "--library", str(test_package), "segments", "validate-document", doc.id])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == client.get(f"/api/segments/document/{doc.id}/validate").json()
