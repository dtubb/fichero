"""Fichero MCP server — exposes the CLI's HTTP operations as MCP tools.

This is a thin wrapper over :class:`fichero.cli.FicheroClient`: every tool is
one client call, one tool per ``fichero`` CLI command. There is no backend
logic and no second HTTP layer here — the client owns auth, the library-path
header, and error handling. A :class:`~fichero.cli.FicheroError` raised by the
client propagates out of the tool; FastMCP turns it into an error tool result
rather than letting it pass silently.

Usage::

    python -m fichero.mcp_server [--api-url URL] [--library-path PATH]

The console entry point ``fichero-mcp = "fichero.mcp_server:main"`` is declared
in pyproject.toml. Configuration falls back to the environment
(``FICHERO_API_URL``, ``FICHERO_LIBRARY_PATH``, ``FICHERO_API_KEY``) — the same
variables the CLI honours.
"""

from __future__ import annotations

import argparse
import logging
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from fichero.cli import FicheroClient

logger = logging.getLogger(__name__)

mcp = FastMCP("fichero")

# Populated by main() from CLI args; None means "discover from environment",
# which FicheroClient already does.
_CONFIG: dict[str, Optional[str]] = {"base_url": None, "library_path": None}


def _client() -> FicheroClient:
    """Build a client from the server config (env-discovered when unset).

    The tools below use this synchronous client directly on the event loop.
    That is sound because this server only runs over stdio (see ``main``),
    where MCP dispatches one request at a time — there is no concurrency to
    block. A non-stdio transport would need an async client instead.
    """
    return FicheroClient(
        base_url=_CONFIG["base_url"],
        library_path=_CONFIG["library_path"],
    )


# -- health ----------------------------------------------------------------
@mcp.tool()
def fichero_health() -> Any:
    """Check that the Fichero backend is reachable."""
    with _client() as client:
        return client.health()


# -- documents -------------------------------------------------------------
@mcp.tool()
def fichero_import(path: str, parent_id: Optional[str] = None) -> Any:
    """Import a file into the library.

    Args:
        path: Path to the file to upload.
        parent_id: Optional parent folder document ID.
    """
    with _client() as client:
        return client.import_file(path, parent_id=parent_id)


@mcp.tool()
def fichero_docs_list(
    parent_id: Optional[str] = None,
    doc_type: Optional[str] = None,
    file_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> Any:
    """List documents in the library, optionally filtered."""
    with _client() as client:
        return client.list_documents(
            parent_id=parent_id,
            doc_type=doc_type,
            file_type=file_type,
            status=status,
            limit=limit,
            offset=offset,
        )


@mcp.tool()
def fichero_docs_get(doc_id: str) -> Any:
    """Fetch a single document by ID."""
    with _client() as client:
        return client.get_document(doc_id)


# -- workflows -------------------------------------------------------------
@mcp.tool()
def fichero_workflow_list() -> Any:
    """List available workflows."""
    with _client() as client:
        return client.list_workflows()


@mcp.tool()
def fichero_workflow_run(
    workflow_id: str,
    doc_id: str,
    force_new: bool = False,
    skip_cache: bool = False,
) -> Any:
    """Run a workflow on a document.

    Args:
        workflow_id: The workflow's ID (use ``fichero_workflow_list`` to find it).
        doc_id: The document ID to run the workflow on.
        force_new: Start a fresh run even if one already exists.
        skip_cache: Bypass the tool-result cache for this run.

    Returns the execution handle, including the ``thread_id`` to poll with
    ``fichero_workflow_status``.
    """
    with _client() as client:
        return client.run_workflow(
            workflow_id,
            {"files": [doc_id]},
            force_new=force_new,
            skip_cache=skip_cache,
        )


@mcp.tool()
def fichero_workflow_status(thread_id: str) -> Any:
    """Get the current status of a workflow execution.

    Args:
        thread_id: The execution thread ID returned by ``fichero_workflow_run``.
    """
    with _client() as client:
        return client.execution_status(thread_id)


# -- artifacts -------------------------------------------------------------
@mcp.tool()
def fichero_artifacts(
    doc_id: str,
    artifact_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    include_descendants: bool = True,
) -> Any:
    """List a document's artifacts (transcriptions, catalogues, etc.)."""
    with _client() as client:
        return client.list_artifacts(
            doc_id,
            artifact_type=artifact_type,
            limit=limit,
            offset=offset,
            include_descendants=include_descendants,
        )


# -- knowledge graph -------------------------------------------------------
@mcp.tool()
def fichero_kg_entities(
    query: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = 50,
) -> Any:
    """List knowledge-graph entities, optionally filtered by name or type."""
    with _client() as client:
        return client.list_entities(
            query=query, entity_type=entity_type, limit=limit
        )


@mcp.tool()
def fichero_kg_claims(
    query: Optional[str] = None,
    source_document_id: Optional[str] = None,
    entity_id: Optional[str] = None,
    claim_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """List knowledge-graph claims, optionally filtered."""
    with _client() as client:
        return client.list_claims(
            query=query,
            source_document_id=source_document_id,
            entity_id=entity_id,
            claim_type=claim_type,
            limit=limit,
            offset=offset,
        )


@mcp.tool()
def fichero_kg_search(query: str, limit: int = 50) -> Any:
    """Search the knowledge graph (entities, claims, notes, annotations)."""
    with _client() as client:
        return client.kg_search(query, limit=limit)


@mcp.tool()
def fichero_document_inspector(doc_id: str) -> Any:
    """Return the document inspector view (entities, claims, artifacts) for a doc."""
    with _client() as client:
        return client.document_inspector(doc_id)


# -- search ----------------------------------------------------------------
@mcp.tool()
def fichero_search(
    query: str,
    limit: int = 10,
    search_type: str = "hybrid",
    min_score: float = 0.3,
) -> Any:
    """Search documents (semantic / keyword / hybrid)."""
    with _client() as client:
        return client.search(
            query, limit=limit, search_type=search_type, min_score=min_score
        )


# -- activity --------------------------------------------------------------
@mcp.tool()
def fichero_activity(limit: int = 50) -> Any:
    """Show recent workflow activity."""
    with _client() as client:
        return client.recent_activity(limit=limit)


# -- mind palace (the AI's spatial workspace, #1269) -----------------------
@mcp.tool()
def fichero_palace_rooms() -> Any:
    """List the Mind Palace rooms (spatial workspaces) in the library."""
    with _client() as client:
        return client.palace_rooms()


@mcp.tool()
def fichero_palace_scene(room_id: str) -> Any:
    """Read a room's full spatial scene: nodes, connections, and stacks.

    Use this to see what's currently in the room before rearranging it.
    """
    with _client() as client:
        return client.palace_scene(room_id)


@mcp.tool()
def fichero_palace_place_node(
    room_id: str,
    node_type: str,
    source_id: Optional[str] = None,
    label: str = "",
    position_x: float = 0.0,
    position_y: float = 0.0,
    position_z: float = 0.0,
) -> Any:
    """Place a node in a room.

    Args:
        room_id: Target room.
        node_type: One of source, claim, note, entity, transcription.
        source_id: Optional document/claim/entity ID this node represents.
        label: Display label.
        position_x/y/z: Initial position in the room's 3D space.
    """
    with _client() as client:
        return client.palace_place_node(
            room_id,
            node_type,
            source_id=source_id,
            label=label,
            position_x=position_x,
            position_y=position_y,
            position_z=position_z,
        )


@mcp.tool()
def fichero_palace_move_node(
    node_id: str,
    position_x: float,
    position_y: float,
    position_z: float = 0.0,
    scale: Optional[float] = None,
) -> Any:
    """Move (and optionally scale) a node — how the AI rearranges the palace."""
    with _client() as client:
        return client.palace_move_node(
            node_id,
            position_x=position_x,
            position_y=position_y,
            position_z=position_z,
            scale=scale,
        )


@mcp.tool()
def fichero_palace_connect(
    room_id: str,
    source_node_id: str,
    target_node_id: str,
    connection_type: str = "semantic",
) -> Any:
    """Draw a connection between two nodes.

    connection_type: one of evidentiary, semantic, ontological, hermeneutic,
    user_drawn.
    """
    with _client() as client:
        return client.palace_connect(
            room_id,
            source_node_id,
            target_node_id,
            connection_type=connection_type,
        )


@mcp.tool()
def fichero_palace_arrange(
    room_id: str,
    node_ids: list[str],
    arrangement_type: str = "semantic",
) -> Any:
    """Auto-arrange the given nodes by a strategy.

    arrangement_type: one of semantic, chronological, thematic.
    """
    with _client() as client:
        return client.palace_arrange(
            room_id, node_ids, arrangement_type=arrangement_type
        )


@mcp.tool()
def fichero_palace_focus(room_id: str, node_id: Optional[str] = None) -> Any:
    """Focus the room's camera on a node (or clear focus when node_id is None)."""
    with _client() as client:
        return client.palace_focus(room_id, node_id)


def main() -> None:
    """Console entry point — runs the MCP server over stdio."""
    parser = argparse.ArgumentParser(description="Fichero MCP server")
    parser.add_argument(
        "--api-url",
        help="Backend base URL (default: $FICHERO_API_URL or http://127.0.0.1:8765).",
    )
    parser.add_argument(
        "--library-path",
        help="Path to the .fichero library package (default: $FICHERO_LIBRARY_PATH).",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.api_url:
        _CONFIG["base_url"] = args.api_url
    if args.library_path:
        _CONFIG["library_path"] = args.library_path
    # A missing token is not fatal — unauthenticated endpoints still work — but
    # every authenticated tool call will then fail with a 401. Flag it once at
    # startup; each authenticated call also still raises a clear FicheroError.
    with _client() as probe:
        if not probe.token:
            logger.warning(
                "No Fichero auth token found. Set FICHERO_API_KEY, or start the "
                "engine (it writes the key file). Authenticated tool calls will "
                "be rejected until a token is available."
            )
    mcp.run()


if __name__ == "__main__":
    main()
