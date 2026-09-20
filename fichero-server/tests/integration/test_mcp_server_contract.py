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
    # Source-model slice 1 (2026-09-19): read-only segments seam
    # (source.one-store, source.seam.read-either-store).
    "fichero_segments",
    # Source-model slice 4/5 (#4955 item C): the three real-Segment reads
    # the HTTP API offers beyond the slice-1 list -- one segment's live row
    # (resolved through forwarding), its version history, and its citable
    # reference. Parity pinned by
    # test_segment_detail_versions_reference_hard_gate_same_everywhere.
    "fichero_segment",
    "fichero_segment_versions",
    "fichero_segment_reference",
    # #4485: KG writes through the audited /api/mcp/tools/knowledge/* path
    # (actor from auth state, change events emitted).
    "fichero_kg_entity_upsert",
    "fichero_kg_claim_create",
    # Library selection: the server binds NO library by default (one server,
    # all libraries), so an agent lists the registry and scopes the session.
    "fichero_list_libraries",
    "fichero_use_library",
    # Authoring/canvas writes through the audited action layer (#4469, #4192).
    "fichero_workflow_create",
    "fichero_document_move",
    # #4914 gate follow-up: verified as one deliberate, single-commit
    # addition (76297c956, 2026-09-06, "add provider / local-runtime /
    # model / Kraken / HPC tools to the fichero MCP surface") -- all 19
    # confirmed `@mcp.tool()`-registered in fichero_mcp/server.py, not
    # accidental surface leaks. This list had gone 18 days without being
    # updated for them (EXPECTED_TOOLS itself last touched 2026-09-01).
    "fichero_providers",
    "fichero_provider_catalog",
    "fichero_local_runtimes",
    "fichero_models_catalog",
    "fichero_model_download",
    "fichero_model_download_status",
    "fichero_model_download_cancel",
    "fichero_model_delete",
    "fichero_runtime_status",
    "fichero_runtime_provision",
    "fichero_local_models",
    "fichero_local_model_download",
    "fichero_kraken_status",
    "fichero_kraken_install",
    "fichero_hpc_clusters",
    "fichero_hpc_configure_cluster",
    "fichero_hpc_delete_cluster",
    "fichero_hpc_test_cluster",
    "fichero_hpc_dry_run_submit",
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

    # source-model slice 1: no artifact in this seed carries ocr_geometry, so
    # an empty segment list is the honest answer, not an error.
    segments = await call(mcp_server, "fichero_segments", {"doc_id": doc_id})
    assert segments.get("document_id") == doc_id
    assert segments.get("segments") == []

    # empty on a fresh library is a legitimate answer for these two
    activity = await call(mcp_server, "fichero_activity", {}, allow_empty=True)
    assert isinstance(activity, (list, dict))

    notes = await call(mcp_server, "fichero_list_notes", {}, allow_empty=True)
    assert isinstance(notes, (list, dict))


@pytest.mark.asyncio
async def test_segments_hard_gate_same_ids_and_rects_everywhere(mcp_server, cli_live_engine):  # noqa: F811
    """`source.one-store`/`source.seam.read-either-store` hard gate: the
    route, the MCP tool and the generated CLI command must resolve through
    the same mapping function and agree byte-for-byte on ids and rects.
    """
    import httpx
    from typer.testing import CliRunner

    from fichero_cli import __main__ as cli

    base_url = cli_live_engine["base_url"]
    library_path = str(cli_live_engine["library"])
    headers = {"X-Fichero-Library-Path": library_path}

    with httpx.Client(base_url=base_url, headers=headers, timeout=10.0) as http:
        doc = http.post("/api/documents", json={"name": "hard-gate.jpg"}).json()
        artifact = http.post(
            "/api/artifacts/",
            json={"document_id": doc["id"], "artifact_type": "regions"},
        ).json()
        http.put(
            f"/api/artifacts/{artifact['id']}/regions",
            json={
                "op": "add",
                "bbox": [0.1, 0.2, 0.3, 0.1],
                "text": "hard gate segment",
                "level": "region",
            },
        ).raise_for_status()

        # 1. The route, direct.
        route_body = http.get(f"/api/segments/document/{doc['id']}").json()

    def _ids_and_rects(segments: list[dict]) -> list[tuple[str, list[float], object]]:
        # page_index (slice 1b, #4919) rides in this tuple too: unset here
        # (the live regions-edit route has no page_index field to set), but
        # the three paths must still agree it is unset the same way.
        return [(s["id"], s["anchor"]["rect"], s["page_index"]) for s in segments]

    route_pairs = _ids_and_rects(route_body["segments"])
    assert route_pairs == [
        ("legacy:" + artifact["id"] + ":0", [0.1, 0.2, 0.3, 0.1], None)
    ]
    route_pass_text = route_body["passes"][0]["text"]

    # 2. The MCP tool, in-process against the same live engine.
    mcp_result = await call(mcp_server, "fichero_segments", {"doc_id": doc["id"]})
    assert _ids_and_rects(mcp_result["segments"]) == route_pairs
    assert mcp_result["passes"][0]["text"] == route_pass_text

    # 3. The generated CLI command, against the same live engine.
    runner = CliRunner()
    env = {
        "FICHERO_API_URL": base_url,
        "FICHERO_LIBRARY_PATH": library_path,
        "FICHERO_DISABLE_AUTH": "1",
    }
    result = runner.invoke(
        cli.app, ["--json", "segments", "list-document", doc["id"]], env=env
    )
    assert result.exit_code == 0, result.output
    cli_body = json.loads(result.output)
    assert _ids_and_rects(cli_body["segments"]) == route_pairs
    assert cli_body["passes"][0]["text"] == route_pass_text


@pytest.mark.asyncio
async def test_segment_detail_versions_reference_hard_gate_same_everywhere(
    mcp_server, cli_live_engine,  # noqa: F811
):
    """#4955 item C: every read the HTTP API offers for a real (slice
    3/4/5) Segment -- its live row (resolved through forwarding), its
    version history, and its citable reference -- must be reachable
    through the MCP tools and the generated CLI command with the SAME
    result as the route itself. Uses a REAL ``Segment`` row (not the
    slice-1 legacy/provisional blob path above): `get_segment`/
    `list_segment_versions`/`segment_reference` all refuse a provisional
    id, so this needs `POST /api/segments/passes` + `POST /api/segments`,
    then one `PUT` update to produce a version row worth reading.
    """
    import httpx
    from typer.testing import CliRunner

    from fichero_cli import __main__ as cli

    base_url = cli_live_engine["base_url"]
    library_path = str(cli_live_engine["library"])
    headers = {"X-Fichero-Library-Path": library_path}

    with httpx.Client(base_url=base_url, headers=headers, timeout=10.0) as http:
        doc = http.post("/api/documents", json={"name": "hard-gate-segment.jpg"}).json()
        pass_row = http.post(
            "/api/segments/passes", json={"document_id": doc["id"], "name": "hard-gate-pass"}
        ).json()
        segment = http.post(
            "/api/segments",
            json={
                "document_id": doc["id"], "pass_id": pass_row["id"], "kind": "word",
                "anchor": {"document_id": doc["id"], "rect": [0.1, 0.1, 0.2, 0.1]},
            },
        ).json()
        segment_id = segment["id"]
        http.request(
            "PUT", f"/api/segments/{segment_id}",
            json={"segment_id": segment_id, "expected_version": 1, "kind_raw": "hard-gate-edit"},
        ).raise_for_status()

        # 1. The route, direct.
        route_detail = http.get(f"/api/segments/{segment_id}").json()
        route_versions = http.get(f"/api/segments/{segment_id}/versions").json()
        route_reference = http.get(f"/api/segments/{segment_id}/reference").json()

    assert route_detail["segment"]["kind_raw"] == "hard-gate-edit"
    assert len(route_versions) == 1
    assert route_reference["segment_id"] == segment_id

    # 2. The MCP tools, in-process against the same live engine.
    mcp_detail = await call(mcp_server, "fichero_segment", {"segment_id": segment_id})
    assert mcp_detail == route_detail

    mcp_versions = await call(mcp_server, "fichero_segment_versions", {"segment_id": segment_id})
    # `call()`'s own docstring: a single-element list comes back as ONE
    # content block, unwrapped to the bare dict rather than `[dict]`.
    if isinstance(mcp_versions, dict):
        mcp_versions = [mcp_versions]
    assert mcp_versions == route_versions

    mcp_reference = await call(
        mcp_server, "fichero_segment_reference", {"segment_id": segment_id}
    )
    assert mcp_reference == route_reference

    # 3. The generated CLI command, against the same live engine.
    runner = CliRunner()
    env = {
        "FICHERO_API_URL": base_url,
        "FICHERO_LIBRARY_PATH": library_path,
        "FICHERO_DISABLE_AUTH": "1",
    }
    detail_result = runner.invoke(cli.app, ["--json", "segments", "get", segment_id], env=env)
    assert detail_result.exit_code == 0, detail_result.output
    assert json.loads(detail_result.output) == route_detail

    versions_result = runner.invoke(
        cli.app, ["--json", "segments", "list-versions", segment_id], env=env
    )
    assert versions_result.exit_code == 0, versions_result.output
    assert json.loads(versions_result.output) == route_versions

    reference_result = runner.invoke(
        cli.app, ["--json", "segments", "reference", segment_id], env=env
    )
    assert reference_result.exit_code == 0, reference_result.output
    assert json.loads(reference_result.output) == route_reference


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
