"""MCP server surface contract (#4250): tools list + one live call per tool.

Drives the SHIPPED ``fichero-mcp`` FastMCP server (fichero_mcp.server) against
a spawned engine + seeded disposable library. Two guarantees:

1. The advertised tool surface is exactly the committed list below — a tool
   rename/removal breaks agents' configured toolsets, so it must be a
   deliberate diff here.
2. Every read tool answers a real call against seeded data (one call per
   tool). Mutating workspace/import/run tools are exercised only where a
   disposable target exists (create_note); the rest are covered by the
   surface snapshot.
"""

from __future__ import annotations

import json

import pytest

from tests.integration._cli_live import cli_live_engine  # noqa: F401  (fixture)

EXPECTED_TOOLS = {
    "fichero_health",
    "fichero_import",
    "fichero_docs_list",
    "fichero_docs_get",
    "fichero_create_note",
    "fichero_list_notes",
    "fichero_get_note",
    "fichero_workflow_list",
    "fichero_workflow_run",
    "fichero_workflow_status",
    "fichero_artifacts",
    "fichero_kg_entities",
    "fichero_kg_claims",
    "fichero_kg_search",
    "fichero_document_inspector",
    "fichero_search",
    "fichero_activity",
    "fichero_workspace_add_source",
    "fichero_workspace_remove_source",
    "fichero_workspace_surface_claim",
    "fichero_workspace_add_note",
    "fichero_reveal_location",
    "fichero_kg_neighborhood",
    "fichero_document_kg",
    "fichero_artifact_get",
}


@pytest.fixture()
def mcp_server(cli_live_engine):  # noqa: F811
    """The shipped FastMCP instance, pointed at the live seeded engine."""
    from fichero_mcp import server

    old = dict(server._CONFIG)
    server._CONFIG["base_url"] = cli_live_engine["base_url"]
    server._CONFIG["library_path"] = str(cli_live_engine["library"])
    yield server.mcp
    server._CONFIG.update(old)


async def call(mcp, name: str, arguments: dict, allow_empty: bool = False):
    """Call one tool through the MCP surface; return parsed payload(s).

    FastMCP may emit one content block per list element, so a list-returning
    tool comes back as several TextContent items — re-assembled here.
    """
    contents = await mcp.call_tool(name, arguments)
    if isinstance(contents, tuple):  # newer FastMCP: (content, structured)
        contents = contents[0]
    payloads = []
    for content in contents:
        text = getattr(content, "text", None)
        if text is None:
            continue
        try:
            payloads.append(json.loads(text))
        except json.JSONDecodeError:
            payloads.append(text)
    if not allow_empty:
        assert payloads, f"tool {name} returned no content"
    return payloads[0] if len(payloads) == 1 else payloads


@pytest.mark.asyncio
async def test_tool_surface_is_exactly_the_committed_list(mcp_server):
    tools = await mcp_server.list_tools()
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS, (
        f"MCP tool surface drifted.\n+ new: {sorted(names - EXPECTED_TOOLS)}\n"
        f"- gone: {sorted(EXPECTED_TOOLS - names)}"
    )


@pytest.mark.asyncio
async def test_every_tool_declares_a_description(mcp_server):
    for tool in await mcp_server.list_tools():
        assert tool.description, f"tool {tool.name} has no description"


@pytest.mark.asyncio
async def test_read_tools_answer_against_seeded_library(mcp_server, cli_live_engine):  # noqa: F811
    summary = cli_live_engine["summary"]
    doc_id = summary["keys"]["doc_letter"]
    entity_id = summary["keys"]["entity_person"]
    artifact_id = summary["keys"]["artifact"]

    health = await call(mcp_server, "fichero_health", {})
    assert health.get("status") == "healthy"

    docs = await call(mcp_server, "fichero_docs_list", {})
    assert doc_id in json.dumps(docs)

    doc = await call(mcp_server, "fichero_docs_get", {"doc_id": doc_id})
    assert doc.get("name") == "Letter 1933"

    workflows = await call(mcp_server, "fichero_workflow_list", {})
    flat = json.dumps(workflows)
    assert summary["keys"]["workflow"] in flat

    artifacts = await call(mcp_server, "fichero_artifacts", {"doc_id": doc_id})
    assert artifact_id in json.dumps(artifacts)

    artifact = await call(mcp_server, "fichero_artifact_get", {"artifact_id": artifact_id})
    assert "Eugenio" in json.dumps(artifact)

    entities = await call(mcp_server, "fichero_kg_entities", {})
    assert entity_id in json.dumps(entities)

    claims = await call(mcp_server, "fichero_kg_claims", {})
    assert summary["ids"]["claims"][0] in json.dumps(claims)

    kg_hits = await call(mcp_server, "fichero_kg_search", {"query": "Eugenio"})
    assert kg_hits is not None

    neighborhood = await call(
        mcp_server, "fichero_kg_neighborhood", {"entity_id": entity_id}
    )
    assert neighborhood is not None

    doc_kg = await call(mcp_server, "fichero_document_kg", {"doc_id": doc_id})
    assert doc_kg is not None

    inspector = await call(mcp_server, "fichero_document_inspector", {"doc_id": doc_id})
    assert doc_id in json.dumps(inspector)

    hits = await call(mcp_server, "fichero_search", {"query": "Eugenio"})
    assert "Letter 1933" in json.dumps(hits) or "test-doc-letter" in json.dumps(hits)

    # empty on a fresh library is a legitimate answer for these two
    activity = await call(mcp_server, "fichero_activity", {}, allow_empty=True)
    assert isinstance(activity, (list, dict))

    notes = await call(mcp_server, "fichero_list_notes", {}, allow_empty=True)
    assert isinstance(notes, (list, dict))


@pytest.mark.asyncio
async def test_note_create_get_round_trip(mcp_server):
    created = await call(
        mcp_server,
        "fichero_create_note",
        {"body": "MCP contract note", "title": "MCP contract"},
    )
    note_id = created.get("id") if isinstance(created, dict) else None
    assert note_id, f"create_note returned no id: {created!r}"
    fetched = await call(mcp_server, "fichero_get_note", {"note_id": note_id})
    assert "MCP contract note" in json.dumps(fetched)
