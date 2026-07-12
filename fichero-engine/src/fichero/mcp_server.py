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
from fichero.knowledge_models import Note, NoteKind

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


def _agent_client() -> FicheroClient:
    """Build the dedicated agent-account client for audited MCP mutations."""
    client = FicheroClient(
        base_url=_CONFIG["base_url"],
        library_path=_CONFIG["library_path"],
        as_user="agent",
    )
    if not client.token:
        client.close()
        raise RuntimeError("No stored session for agent; run `fichero auth login agent`.")
    return client


def _workspace_action(name: str, params: dict[str, str]) -> Any:
    """Invoke a workspace action through the one audited write endpoint."""
    with _agent_client() as client:
        return client.request("POST", "/api/actions/invoke", json={"name": name, "params": params})


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


# -- agent workspace actions ----------------------------------------------
@mcp.tool()
def fichero_workspace_add_source(workspace_id: str, document_id: str) -> Any:
    """Add a source document to an agent workspace."""
    return _workspace_action("workspace.add_source", {"workspace_id": workspace_id, "document_id": document_id})


@mcp.tool()
def fichero_workspace_remove_source(workspace_id: str, document_id: str) -> Any:
    """Remove a source document from an agent workspace."""
    return _workspace_action("workspace.remove_source", {"workspace_id": workspace_id, "document_id": document_id})


@mcp.tool()
def fichero_workspace_surface_claim(workspace_id: str, claim_id: str) -> Any:
    """Surface a knowledge claim in an agent workspace."""
    return _workspace_action("workspace.surface_claim", {"workspace_id": workspace_id, "claim_id": claim_id})


@mcp.tool()
def fichero_workspace_add_note(workspace_id: str, text: str) -> Any:
    """Add an agent note to an agent workspace."""
    return _workspace_action("workspace.add_note", {"workspace_id": workspace_id, "text": text})


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
