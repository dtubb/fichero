"""Full-featured MCP surface."""

from __future__ import annotations

import argparse
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from fichero_cli import FicheroClient
from fichero_server.models.knowledge import NoteKind

mcp = FastMCP("fichero-full")

_CONFIG: dict[str, Optional[str]] = {"base_url": None, "library_path": None}


def _client() -> FicheroClient:
    return FicheroClient(
        base_url=_CONFIG["base_url"],
        library_path=_CONFIG["library_path"],
    )


class DocumentInput(BaseModel):
    doc_id: str


class DocumentListInput(BaseModel):
    parent_id: str | None = None
    doc_type: str | None = None
    file_type: str | None = None
    status: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class WorkflowRunInput(BaseModel):
    workflow_id: str
    doc_id: str
    force_new: bool = False
    skip_cache: bool = False


class WorkflowRunOutput(BaseModel):
    thread_id: str
    workflow_id: str
    status: str


class SearchInput(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=200)
    search_type: str = "hybrid"
    min_score: float = Field(default=0.3, ge=0.0, le=1.0)


class WorkflowStatusInput(BaseModel):
    thread_id: str


class ArtifactsInput(BaseModel):
    doc_id: str
    artifact_type: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    include_descendants: bool = True


class KGEntitiesInput(BaseModel):
    query: str | None = None
    entity_type: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class KGClaimsInput(BaseModel):
    query: str | None = None
    source_document_id: str | None = None
    entity_id: str | None = None
    claim_type: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class CreateClaimInput(BaseModel):
    text: str
    source_document_id: str | None = None
    entity_ids: list[str] = Field(default_factory=list)
    predicate_verb: str | None = None
    subject_canonical: str | None = None
    object_phrase: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class UpdateClaimInput(BaseModel):
    claim_id: str
    text: str | None = None
    curation_state: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class KGNeighborhoodInput(BaseModel):
    entity_id: str
    hops: int = Field(default=1, ge=1, le=5)
    limit: int = Field(default=50, ge=1, le=500)
    rank: str = "edge_weight"


class KGSparqlInput(BaseModel):
    query: str


class CitationsInput(BaseModel):
    doc_id: str


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
    linked_entity_id: str | None = None
    linked_claim_id: str | None = None
    linked_document_id: str | None = None
    query: str | None = None


class ArtifactInput(BaseModel):
    artifact_id: str


class ImportDocumentInput(BaseModel):
    path: str
    parent_id: str | None = None


@mcp.tool()
def health() -> Any:
    with _client() as client:
        return client.health()


@mcp.tool()
def import_document(input: ImportDocumentInput) -> Any:
    with _client() as client:
        return client.import_file(input.path, parent_id=input.parent_id)


@mcp.tool()
def list_documents(input: DocumentListInput) -> Any:
    with _client() as client:
        return client.list_documents(
            parent_id=input.parent_id,
            doc_type=input.doc_type,
            file_type=input.file_type,
            status=input.status,
            limit=input.limit,
            offset=input.offset,
        )


@mcp.tool()
def get_document(input: DocumentInput) -> Any:
    with _client() as client:
        return client.get_document(input.doc_id)


@mcp.tool()
def document_inspector(input: DocumentInput) -> Any:
    with _client() as client:
        return client.document_inspector(input.doc_id)


@mcp.tool()
def document_knowledge_graph(input: DocumentInput, include_children: bool = False) -> Any:
    with _client() as client:
        return client.document_knowledge_graph(
            input.doc_id, include_children=include_children
        )


@mcp.tool()
def list_workflows() -> Any:
    """List workflows with the engine's run eligibility (#3804).

    ``direct_runnable`` false = internal component, refused by ``run_workflow``;
    ``requires_vision`` true = the run needs a vision-capable model.
    """
    with _client() as client:
        return client.list_workflows()


@mcp.tool()
def run_workflow(input: WorkflowRunInput) -> WorkflowRunOutput:
    with _client() as client:
        out = client.run_workflow(
            input.workflow_id,
            # `selected_doc_ids` is the key the RECEIVER reads — the Files
            # source node, the CLI and SwiftUI all read it. `files` is read by
            # nothing, so #4467 made the engine reject it rather than complete
            # green over zero documents. This tool was never updated to match,
            # so every run_workflow call 422s today (#4465/#4480).
            {"selected_doc_ids": [input.doc_id]},
            force_new=input.force_new,
            skip_cache=input.skip_cache,
        )
    return WorkflowRunOutput(thread_id=out.thread_id, workflow_id=out.workflow_id, status=out.status)


@mcp.tool()
def workflow_status(input: WorkflowStatusInput) -> Any:
    with _client() as client:
        return client.execution_status(input.thread_id)


@mcp.tool()
def workflow_pause(thread_id: str) -> Any:
    with _client() as client:
        return client.request(
            "POST",
            f"/api/workflow-execution/threads/{thread_id}/pause",
        )


@mcp.tool()
def workflow_resume(thread_id: str) -> Any:
    with _client() as client:
        return client.request(
            "POST",
            f"/api/workflow-execution/threads/{thread_id}/resume",
            json={},
        )


@mcp.tool()
def list_artifacts(input: ArtifactsInput) -> Any:
    with _client() as client:
        return client.list_artifacts(
            input.doc_id,
            artifact_type=input.artifact_type,
            limit=input.limit,
            offset=input.offset,
            include_descendants=input.include_descendants,
        )


@mcp.tool()
def get_artifact(input: ArtifactInput) -> Any:
    with _client() as client:
        return client.get_artifact(input.artifact_id)


@mcp.tool()
def query_kg_entities(input: KGEntitiesInput) -> Any:
    with _client() as client:
        return client.list_entities(
            query=input.query,
            entity_type=input.entity_type,
            limit=input.limit,
        )


@mcp.tool()
def query_kg_claims(input: KGClaimsInput) -> Any:
    with _client() as client:
        return client.list_claims(
            query=input.query,
            source_document_id=input.source_document_id,
            entity_id=input.entity_id,
            claim_type=input.claim_type,
            limit=input.limit,
        )


@mcp.tool()
def create_claim(input: CreateClaimInput) -> Any:
    with _client() as client:
        return client.create_claim(
            text=input.text,
            source_document_id=input.source_document_id,
            entity_ids=input.entity_ids,
            predicate_verb=input.predicate_verb,
            subject_canonical=input.subject_canonical,
            object_phrase=input.object_phrase,
            confidence=input.confidence,
        )


@mcp.tool()
def update_claim(input: UpdateClaimInput) -> Any:
    body = input.model_dump(exclude_none=True)
    claim_id = str(body.pop("claim_id"))
    with _client() as client:
        return client.update_claim(claim_id, **body)


@mcp.tool()
def delete_claim(claim_id: str) -> None:
    with _client() as client:
        client.delete_claim(claim_id)
    return None


@mcp.tool()
def kg_search(input: SearchInput) -> Any:
    with _client() as client:
        return client.kg_search(input.query, limit=input.limit)


@mcp.tool()
def kg_neighborhood(input: KGNeighborhoodInput) -> Any:
    with _client() as client:
        return client.entity_neighborhood(
            input.entity_id,
            hops=input.hops,
            limit=input.limit,
            rank=input.rank,
        )


@mcp.tool()
def kg_sparql(input: KGSparqlInput) -> Any:
    with _client() as client:
        return client.request(
            "POST",
            "/api/kg/sparql",
            json=input.model_dump(mode="json"),
        )


@mcp.tool()
def citations_at_document(input: CitationsInput) -> Any:
    with _client() as client:
        return client.citations_at_doc(input.doc_id)


@mcp.tool()
def create_note(input: CreateNoteInput) -> Any:
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
    with _client() as client:
        return client.list_notes(
            kind=input.kind,
            tag=input.tag,
            linked_entity_id=input.linked_entity_id,
            linked_claim_id=input.linked_claim_id,
            linked_document_id=input.linked_document_id,
            query=input.query,
        )


@mcp.tool()
def get_note(note_id: str) -> Any:
    with _client() as client:
        return client.get_note(note_id)


@mcp.tool()
def search(input: SearchInput) -> Any:
    with _client() as client:
        return client.search(
            query=input.query,
            limit=input.limit,
            search_type=input.search_type,
            min_score=input.min_score,
        )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run full Fichero MCP server.")
    parser.add_argument("--api-url", dest="api_url", default=None)
    parser.add_argument("--library-path", dest="library_path", default=None)
    args = parser.parse_args(argv)

    _CONFIG["base_url"] = args.api_url
    _CONFIG["library_path"] = args.library_path
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
