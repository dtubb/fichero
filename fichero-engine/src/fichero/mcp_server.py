"""Fichero MCP server — exposes the CLI's HTTP operations as MCP tools.

This is a thin wrapper over :class:`fichero.cli.FicheroClient`: every tool is
one client call. There is no backend logic and no second HTTP layer here — the
client owns auth, the library-path header, and error handling. A
:class:`~fichero.cli.FicheroError` raised by the client propagates out of the
tool; FastMCP turns it into an error tool result rather than letting it pass
silently.

Two tool families (#1269 — "MCP access to the app"):

* **Read** — search documents, query the knowledge graph
  (entities / claims / neighborhood), and pull a document's content, artifacts,
  and canonical KG so an agent can reason over the catalogue.
* **Mind Palace** (``fichero_mp_*``) — *arrange* the Layer-6 spatial workspace:
  create rooms, place / move / remove nodes, draw connections, build stacks,
  suggest layouts, and save the camera. This is how an agent "thinks visually."
  The mind-palace router is **dev-tier**: the engine must run with
  ``FICHERO_FEATURE_TIER=dev`` for these tools to resolve (the app-embedded
  backend already sets this; a standalone ``release`` engine returns 404).

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
from fichero.api.routes.mind_palace import MindPalaceDeletedResponse
from fichero.knowledge_models import Note, NoteKind
from fichero.spatial_models import NativeNote

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


# -- notes -----------------------------------------------------------------
@mcp.tool()
def fichero_create_note(
    body: str,
    title: Optional[str] = None,
    kind: NoteKind = NoteKind.zettel,
    tags: Optional[list[str]] = None,
    linked_note_ids: Optional[list[str]] = None,
    linked_entity_ids: Optional[list[str]] = None,
    linked_claim_ids: Optional[list[str]] = None,
    linked_document_ids: Optional[list[str]] = None,
    address: Optional[str] = None,
    parent_address: Optional[str] = None,
) -> Note:
    """Create a Zettelkasten note linked to documents, entities, claims, or notes."""
    with _client() as client:
        return client.create_note(
            title=title,
            body=body,
            kind=kind,
            tags=tags,
            linked_note_ids=linked_note_ids,
            linked_entity_ids=linked_entity_ids,
            linked_claim_ids=linked_claim_ids,
            linked_document_ids=linked_document_ids,
            address=address,
            parent_address=parent_address,
        )


@mcp.tool()
def fichero_list_notes(
    kind: Optional[NoteKind] = None,
    tag: Optional[str] = None,
    linked_entity_id: Optional[str] = None,
    linked_claim_id: Optional[str] = None,
    linked_document_id: Optional[str] = None,
    query: Optional[str] = None,
) -> list[Note]:
    """List Zettelkasten notes, optionally filtered by kind, tag, link, or text."""
    with _client() as client:
        return client.list_notes(
            kind=kind,
            tag=tag,
            linked_entity_id=linked_entity_id,
            linked_claim_id=linked_claim_id,
            linked_document_id=linked_document_id,
            query=query,
        )


@mcp.tool()
def fichero_get_note(note_id: str) -> Note:
    """Fetch a single Zettelkasten note by ID."""
    with _client() as client:
        return client.get_note(note_id)


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


# -- knowledge graph / content (read) --------------------------------------
@mcp.tool()
def fichero_kg_neighborhood(
    entity_id: str,
    hops: int = 1,
    limit: int = 50,
    rank: str = "edge_weight",
) -> Any:
    """Get the graph neighborhood around an entity (connected entities + edges).

    Args:
        entity_id: The entity to centre the neighborhood on.
        hops: How many edges out to traverse (default 1).
        limit: Max neighbors to return.
        rank: Ranking strategy for which neighbors to keep (e.g. edge_weight).
    """
    with _client() as client:
        return client.entity_neighborhood(
            entity_id, hops=hops, limit=limit, rank=rank
        )


@mcp.tool()
def fichero_document_kg(doc_id: str, include_children: bool = False) -> Any:
    """Canonical knowledge graph for a document — deduped, merge-resolved.

    Args:
        doc_id: The document ID.
        include_children: Include child docs (e.g. PDF pages) in the rollup.
    """
    with _client() as client:
        return client.document_knowledge_graph(
            doc_id, include_children=include_children
        )


@mcp.tool()
def fichero_artifact_get(artifact_id: str) -> Any:
    """Fetch a single artifact (transcription, catalogue, …) including its content."""
    with _client() as client:
        return client.get_artifact(artifact_id)


# -- mind palace: rooms (#1269) --------------------------------------------
@mcp.tool()
def fichero_mp_list_rooms(
    room_type: Optional[str] = None, owner_id: Optional[str] = None
) -> Any:
    """List Mind Palace rooms. room_type: research / synthesis / presentation."""
    with _client() as client:
        return client.mp_list_rooms(room_type=room_type, owner_id=owner_id)


@mcp.tool()
def fichero_mp_get_room(room_id: str) -> Any:
    """Fetch a single Mind Palace room by ID."""
    with _client() as client:
        return client.mp_get_room(room_id)


@mcp.tool()
def fichero_mp_create_room(
    name: str,
    description: str = "",
    room_type: str = "research",
    owner_id: str = "user",
) -> Any:
    """Create a Mind Palace room. room_type: research / synthesis / presentation."""
    with _client() as client:
        return client.mp_create_room(
            name, description=description, room_type=room_type, owner_id=owner_id
        )


@mcp.tool()
def fichero_mp_scene_summary(room_id: str) -> Any:
    """Get a room's scene summary: node/connection/stack/note counts + node-type breakdown."""
    with _client() as client:
        return client.mp_scene_summary(room_id)


# -- mind palace: notes ---------------------------------------------------
@mcp.tool()
def fichero_mp_create_note(
    content: str,
    room_id: Optional[str] = None,
    note_type: str = "user",
    author_id: str = "user",
    linked_claim_ids: Optional[list[str]] = None,
    linked_source_ids: Optional[list[str]] = None,
    linked_entity_ids: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> NativeNote:
    """Create a first-class text note in Mind Palace."""
    with _client() as client:
        return client.mp_create_note(
            content,
            room_id=room_id,
            note_type=note_type,
            author_id=author_id,
            linked_claim_ids=linked_claim_ids,
            linked_source_ids=linked_source_ids,
            linked_entity_ids=linked_entity_ids,
            metadata=metadata,
        )


@mcp.tool()
def fichero_mp_list_notes(
    room_id: Optional[str] = None,
    note_type: Optional[str] = None,
    status: Optional[str] = None,
    author_id: Optional[str] = None,
) -> list[NativeNote]:
    """List Mind Palace notes, optionally filtered by room / type / status."""
    with _client() as client:
        return client.mp_list_notes(
            room_id=room_id,
            note_type=note_type,
            status=status,
            author_id=author_id,
        )


@mcp.tool()
def fichero_mp_get_note(note_id: str) -> NativeNote:
    """Fetch a single Mind Palace note by ID."""
    with _client() as client:
        return client.mp_get_note(note_id)


@mcp.tool()
def fichero_mp_update_note(
    note_id: str,
    content: Optional[str] = None,
    note_type: Optional[str] = None,
    status: Optional[str] = None,
    linked_claim_ids: Optional[list[str]] = None,
    linked_source_ids: Optional[list[str]] = None,
    linked_entity_ids: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> NativeNote:
    """Patch a Mind Palace note."""
    with _client() as client:
        return client.mp_update_note(
            note_id,
            content=content,
            note_type=note_type,
            status=status,
            linked_claim_ids=linked_claim_ids,
            linked_source_ids=linked_source_ids,
            linked_entity_ids=linked_entity_ids,
            metadata=metadata,
        )


@mcp.tool()
def fichero_mp_delete_note(note_id: str) -> MindPalaceDeletedResponse:
    """Delete a Mind Palace note."""
    with _client() as client:
        return client.mp_delete_note(note_id)


# -- mind palace: nodes ----------------------------------------------------
@mcp.tool()
def fichero_mp_list_nodes(room_id: str, node_type: Optional[str] = None) -> Any:
    """List nodes in a room. node_type: source / claim / note / entity / transcription."""
    with _client() as client:
        return client.mp_list_nodes(room_id, node_type=node_type)


@mcp.tool()
def fichero_mp_get_node(node_id: str) -> Any:
    """Fetch a single spatial node by ID."""
    with _client() as client:
        return client.mp_get_node(node_id)


@mcp.tool()
def fichero_mp_place_node(
    room_id: str,
    node_type: str,
    source_id: Optional[str] = None,
    label: str = "",
    position_x: float = 0.0,
    position_y: float = 0.0,
    position_z: float = 0.0,
    scale: float = 1.0,
) -> Any:
    """Place a node in a room at a 3D position.

    Args:
        room_id: The room to place the node in.
        node_type: source / claim / note / entity / transcription.
        source_id: Optional ID of the backing document / claim / entity.
        label: Display label for the node.
        position_x, position_y, position_z: 3D position (defaults to origin).
        scale: Node scale (default 1.0).
    """
    with _client() as client:
        return client.mp_place_node(
            room_id,
            node_type,
            source_id=source_id,
            label=label,
            position_x=position_x,
            position_y=position_y,
            position_z=position_z,
            scale=scale,
        )


@mcp.tool()
def fichero_mp_move_node(
    node_id: str,
    position_x: float,
    position_y: float,
    position_z: float,
    scale: Optional[float] = None,
) -> Any:
    """Move (and optionally rescale) a node to a new 3D position."""
    with _client() as client:
        return client.mp_move_node(
            node_id, position_x, position_y, position_z, scale=scale
        )


@mcp.tool()
def fichero_mp_remove_node(node_id: str) -> Any:
    """Remove a node from its room."""
    with _client() as client:
        return client.mp_remove_node(node_id)


# -- mind palace: connections ----------------------------------------------
@mcp.tool()
def fichero_mp_list_connections(
    room_id: str, connection_type: Optional[str] = None
) -> Any:
    """List connections in a room. connection_type: evidentiary / semantic / ontological / hermeneutic / user_drawn."""
    with _client() as client:
        return client.mp_list_connections(
            room_id, connection_type=connection_type
        )


@mcp.tool()
def fichero_mp_create_connection(
    room_id: str,
    source_node_id: str,
    target_node_id: str,
    connection_type: str,
    link_subtype: Optional[str] = None,
) -> Any:
    """Draw a typed connection between two nodes.

    connection_type: evidentiary / semantic / ontological / hermeneutic / user_drawn.
    """
    with _client() as client:
        return client.mp_create_connection(
            room_id,
            source_node_id,
            target_node_id,
            connection_type,
            link_subtype=link_subtype,
        )


@mcp.tool()
def fichero_mp_remove_connection(connection_id: str) -> Any:
    """Remove a connection between nodes."""
    with _client() as client:
        return client.mp_remove_connection(connection_id)


# -- mind palace: stacks ---------------------------------------------------
@mcp.tool()
def fichero_mp_list_stacks(room_id: str) -> Any:
    """List stacks (grouped node piles) in a room."""
    with _client() as client:
        return client.mp_list_stacks(room_id)


@mcp.tool()
def fichero_mp_get_stack(stack_id: str) -> Any:
    """Fetch a single stack by ID."""
    with _client() as client:
        return client.mp_get_stack(stack_id)


@mcp.tool()
def fichero_mp_create_stack(
    room_id: str,
    name: str = "",
    node_ids: Optional[list[str]] = None,
    position_x: float = 0.0,
    position_y: float = 0.0,
    position_z: float = 0.0,
) -> Any:
    """Create a stack that groups nodes together at a position."""
    with _client() as client:
        return client.mp_create_stack(
            room_id,
            name=name,
            node_ids=node_ids,
            position_x=position_x,
            position_y=position_y,
            position_z=position_z,
        )


@mcp.tool()
def fichero_mp_add_to_stack(stack_id: str, node_id: str) -> Any:
    """Add a node to an existing stack."""
    with _client() as client:
        return client.mp_add_to_stack(stack_id, node_id)


@mcp.tool()
def fichero_mp_remove_from_stack(stack_id: str, node_id: str) -> Any:
    """Remove a node from a stack."""
    with _client() as client:
        return client.mp_remove_from_stack(stack_id, node_id)


# -- mind palace: viewport / focus / arrange -------------------------------
@mcp.tool()
def fichero_mp_get_viewport(room_id: str, user_id: str = "user") -> Any:
    """Get the saved camera viewport for a room."""
    with _client() as client:
        return client.mp_get_viewport(room_id, user_id=user_id)


@mcp.tool()
def fichero_mp_save_viewport(
    room_id: str,
    camera_x: float = 0.0,
    camera_y: float = 0.0,
    camera_z: float = 10.0,
    focus_node_id: Optional[str] = None,
    zoom_level: float = 1.0,
    bookmark_name: Optional[str] = None,
    user_id: str = "user",
) -> Any:
    """Save the camera viewport for a room, optionally as a named bookmark."""
    with _client() as client:
        return client.mp_save_viewport(
            room_id,
            user_id=user_id,
            camera_x=camera_x,
            camera_y=camera_y,
            camera_z=camera_z,
            focus_node_id=focus_node_id,
            zoom_level=zoom_level,
            bookmark_name=bookmark_name,
        )


@mcp.tool()
def fichero_mp_focus(room_id: str, node_id: str, user_id: str = "user") -> Any:
    """Focus the room's viewport on a specific node."""
    with _client() as client:
        return client.mp_focus(room_id, node_id, user_id=user_id)


@mcp.tool()
def fichero_mp_suggest_arrangement(
    room_id: str,
    node_ids: list[str],
    arrangement_type: str = "semantic",
) -> Any:
    """Ask the backend to propose positions for nodes.

    arrangement_type: semantic / chronological / thematic. Returns the updated
    nodes with their suggested positions.
    """
    with _client() as client:
        return client.mp_suggest_arrangement(
            room_id, node_ids, arrangement_type=arrangement_type
        )


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
