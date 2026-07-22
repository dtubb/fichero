"""Simplified MCP surface for external agents (#1327).

This exposes a small, stable tool contract (9 tools) focused on:
- reading the library
- running workflows
- querying KG
- saving/listing notes
"""

from __future__ import annotations

import argparse
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from fichero.cli import FicheroClient
from fichero.models.knowledge import NoteKind

mcp = FastMCP("fichero-simple")

_CONFIG: dict[str, Optional[str]] = {"base_url": None, "library_path": None}


def _client() -> FicheroClient:
    return FicheroClient(
        base_url=_CONFIG["base_url"],
        library_path=_CONFIG["library_path"],
    )


class ListDocumentsInput(BaseModel):
    parent_id: str | None = None
    doc_type: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class DocumentIdInput(BaseModel):
    doc_id: str


class RunWorkflowInput(BaseModel):
    workflow_id: str
    doc_id: str
    force_new: bool = False
    skip_cache: bool = False


class WorkflowStatusInput(BaseModel):
    thread_id: str


class ArtifactsInput(BaseModel):
    doc_id: str
    artifact_type: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    include_descendants: bool = True


class KGSearchInput(BaseModel):
    query: str
    limit: int = Field(default=20, ge=1, le=200)


class KGClaimsInput(BaseModel):
    query: str | None = None
    source_document_id: str | None = None
    entity_id: str | None = None
    claim_type: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class CreateNoteInput(BaseModel):
    body: str
    title: str | None = None
    kind: NoteKind = NoteKind.zettel
    linked_document_ids: list[str] = Field(default_factory=list)
    linked_entity_ids: list[str] = Field(default_factory=list)
    linked_claim_ids: list[str] = Field(default_factory=list)


class ListNotesInput(BaseModel):
    kind: NoteKind | None = None
    tag: str | None = None
    linked_document_id: str | None = None
    linked_entity_id: str | None = None
    linked_claim_id: str | None = None
    query: str | None = None


@mcp.tool()
def health() -> Any:
    """Check that the Fichero backend is reachable."""
    with _client() as client:
        return client.health()


@mcp.tool()
def list_documents(input: ListDocumentsInput) -> Any:
    """List documents with light filtering."""
    with _client() as client:
        return client.list_documents(
            parent_id=input.parent_id,
            doc_type=input.doc_type,
            limit=input.limit,
            offset=input.offset,
        )


@mcp.tool()
def get_document(input: DocumentIdInput) -> Any:
    """Fetch one document by ID."""
    with _client() as client:
        return client.get_document(input.doc_id)


@mcp.tool()
def run_workflow(input: RunWorkflowInput) -> Any:
    """Run a workflow on one document."""
    with _client() as client:
        return client.run_workflow(
            input.workflow_id,
            {"files": [input.doc_id]},
            force_new=input.force_new,
            skip_cache=input.skip_cache,
        )


@mcp.tool()
def workflow_status(input: WorkflowStatusInput) -> Any:
    """Get workflow execution status by thread ID."""
    with _client() as client:
        return client.execution_status(input.thread_id)


@mcp.tool()
def list_artifacts(input: ArtifactsInput) -> Any:
    """List artifacts for a document (optionally including descendants)."""
    with _client() as client:
        return client.list_artifacts(
            input.doc_id,
            artifact_type=input.artifact_type,
            limit=input.limit,
            include_descendants=input.include_descendants,
        )


@mcp.tool()
def kg_search(input: KGSearchInput) -> Any:
    """Search KG entities + claims by query text."""
    with _client() as client:
        return client.search_knowledge(input.query, limit=input.limit)


@mcp.tool()
def kg_claims(input: KGClaimsInput) -> Any:
    """List KG claims with optional document/entity filters."""
    with _client() as client:
        return client.list_claims(
            query=input.query,
            source_document_id=input.source_document_id,
            entity_id=input.entity_id,
            claim_type=input.claim_type,
            limit=input.limit,
        )


@mcp.tool()
def create_note(input: CreateNoteInput) -> Any:
    """Create a note linked to docs/entities/claims."""
    with _client() as client:
        return client.create_note(
            body=input.body,
            title=input.title,
            kind=input.kind,
            linked_document_ids=input.linked_document_ids,
            linked_entity_ids=input.linked_entity_ids,
            linked_claim_ids=input.linked_claim_ids,
        )


@mcp.tool()
def list_notes(input: ListNotesInput) -> Any:
    """List notes, optionally filtered by kind/tag/link/query."""
    with _client() as client:
        return client.list_notes(
            kind=input.kind,
            tag=input.tag,
            linked_document_id=input.linked_document_id,
            linked_entity_id=input.linked_entity_id,
            linked_claim_id=input.linked_claim_id,
            query=input.query,
        )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run simplified Fichero MCP server for external agents."
    )
    parser.add_argument("--api-url", dest="api_url", default=None)
    parser.add_argument("--library-path", dest="library_path", default=None)
    args = parser.parse_args(argv)

    _CONFIG["base_url"] = args.api_url
    _CONFIG["library_path"] = args.library_path
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
