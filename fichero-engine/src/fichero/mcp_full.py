"""Full-featured MCP surface, including vision scene rendering hook."""

from __future__ import annotations

import argparse
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from fichero.cli import FicheroClient

mcp = FastMCP("fichero-full")

_CONFIG: dict[str, Optional[str]] = {"base_url": None, "library_path": None}


def _client() -> FicheroClient:
    return FicheroClient(
        base_url=_CONFIG["base_url"],
        library_path=_CONFIG["library_path"],
    )


class DocumentInput(BaseModel):
    doc_id: str


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


class SceneRenderInput(BaseModel):
    room_id: str
    include_video: bool = True
    width: int = Field(default=1280, ge=320, le=4096)
    height: int = Field(default=720, ge=240, le=4096)
    duration_seconds: float = Field(default=2.0, ge=0.5, le=20.0)


class SceneRenderOutput(BaseModel):
    room_id: str
    rendered_at: str
    png_base64: str
    mp4_base64: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MoveNodeInput(BaseModel):
    node_id: str
    position_x: float
    position_y: float
    position_z: float


@mcp.tool()
def list_documents(parent_id: str | None = None, limit: int = 50) -> Any:
    with _client() as client:
        return client.list_documents(parent_id=parent_id, limit=limit)


@mcp.tool()
def get_document_content(input: DocumentInput) -> Any:
    with _client() as client:
        return client.get_document(input.doc_id)


@mcp.tool()
def run_workflow(input: WorkflowRunInput) -> WorkflowRunOutput:
    with _client() as client:
        out = client.run_workflow(
            input.workflow_id,
            {"files": [input.doc_id]},
            force_new=input.force_new,
            skip_cache=input.skip_cache,
        )
    return WorkflowRunOutput(thread_id=out.thread_id, workflow_id=out.workflow_id, status=out.status)


@mcp.tool()
def list_artifacts(doc_id: str, include_descendants: bool = True) -> Any:
    with _client() as client:
        return client.list_artifacts(doc_id, include_descendants=include_descendants)


@mcp.tool()
def query_kg_entities(query: str | None = None, entity_type: str | None = None, limit: int = 50) -> Any:
    with _client() as client:
        return client.list_entities(query=query, entity_type=entity_type, limit=limit)


@mcp.tool()
def query_kg_claims(
    query: str | None = None,
    source_document_id: str | None = None,
    entity_id: str | None = None,
    limit: int = 50,
) -> Any:
    with _client() as client:
        return client.list_claims(
            query=query,
            source_document_id=source_document_id,
            entity_id=entity_id,
            limit=limit,
        )


@mcp.tool()
def save_note(body: str, title: str | None = None, linked_document_ids: list[str] | None = None) -> Any:
    with _client() as client:
        return client.create_note(
            body=body,
            title=title,
            linked_document_ids=linked_document_ids or [],
        )


@mcp.tool()
def search(input: SearchInput) -> Any:
    with _client() as client:
        return client.search(
            query=input.query,
            limit=input.limit,
            search_type=input.search_type,
            min_score=input.min_score,
        )


@mcp.tool()
def mp_list_rooms(room_type: str | None = None) -> Any:
    with _client() as client:
        return client.mp_list_rooms(room_type=room_type)


@mcp.tool()
def mp_create_room(name: str, room_type: str = "research", description: str = "") -> Any:
    with _client() as client:
        return client.mp_create_room(name=name, room_type=room_type, description=description)


@mcp.tool()
def mp_place_node(room_id: str, node_type: str, source_id: str | None = None, label: str = "") -> Any:
    with _client() as client:
        return client.mp_place_node(
            room_id=room_id,
            node_type=node_type,
            source_id=source_id,
            label=label,
        )


@mcp.tool()
def mp_move_node(input: MoveNodeInput) -> Any:
    with _client() as client:
        return client.mp_move_node(
            input.node_id,
            position_x=input.position_x,
            position_y=input.position_y,
            position_z=input.position_z,
        )


@mcp.tool()
def scene_render(input: SceneRenderInput) -> SceneRenderOutput:
    """Render current Mind Palace state for vision/multimodal agent loops."""
    with _client() as client:
        raw = client.request(
            "POST",
            "/api/mindpalace/render",
            json=input.model_dump(mode="json"),
        )
    return SceneRenderOutput.model_validate(raw)


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
