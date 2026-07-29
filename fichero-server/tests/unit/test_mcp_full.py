from __future__ import annotations

import asyncio

from fichero_server.mcp import full as mcp_full


def _tool_names() -> set[str]:
    return {tool.name for tool in asyncio.run(mcp_full.mcp.list_tools())}


EXPECTED_FULL_TOOLS = {
    "health",
    "import_document",
    "list_documents",
    "get_document",
    "document_inspector",
    "document_knowledge_graph",
    "list_workflows",
    "run_workflow",
    "workflow_status",
    "workflow_pause",
    "workflow_resume",
    "list_artifacts",
    "get_artifact",
    "query_kg_entities",
    "query_kg_claims",
    "create_claim",
    "update_claim",
    "delete_claim",
    "kg_search",
    "kg_neighborhood",
    "kg_sparql",
    "citations_at_document",
    "create_note",
    "list_notes",
    "get_note",
    "search",
}


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def request(self, method: str, path: str, json=None):
        if method == "POST" and path.endswith("/pause"):
            return {
                "thread_id": path.split("/")[-2],
                "status": "pause_requested",
                "message": "Pause requested.",
            }
        if method == "POST" and path.endswith("/resume"):
            return {
                "thread_id": path.split("/")[-2],
                "workflow_id": "wf-1",
                "workflow_name": "Test",
                "status": "running",
            }
        raise AssertionError(f"unexpected request: {method} {path}")

    def create_claim(self, text: str, **kwargs):
        self.calls.append(("create_claim", {"text": text, **kwargs}))
        return {"id": "claim-1", "text": text}

    def update_claim(self, claim_id: str, **fields):
        self.calls.append(("update_claim", {"claim_id": claim_id, **fields}))
        return {"id": claim_id, **fields}

    def delete_claim(self, claim_id: str):
        self.calls.append(("delete_claim", {"claim_id": claim_id}))
        return None

def test_full_tools_include_scene_render():
    names = _tool_names()
    assert names == EXPECTED_FULL_TOOLS


def test_claim_mutation_tools_passthrough(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(mcp_full, "_client", lambda: fake)

    created = mcp_full.create_claim(
        mcp_full.CreateClaimInput(
            text="A links to B",
            source_document_id="doc-1",
            entity_ids=["e1", "e2"],
        )
    )
    updated = mcp_full.update_claim(
        mcp_full.UpdateClaimInput(
            claim_id="claim-1",
            text="A strongly links to B",
            confidence=0.9,
        )
    )
    deleted = mcp_full.delete_claim("claim-1")

    assert created["id"] == "claim-1"
    assert updated["id"] == "claim-1"
    assert deleted is None
    assert fake.calls[0][0] == "create_claim"
    assert fake.calls[1][0] == "update_claim"
    assert fake.calls[2][0] == "delete_claim"


def test_workflow_pause_resume_tools(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(mcp_full, "_client", lambda: fake)

    paused = mcp_full.workflow_pause("thread-123")
    resumed = mcp_full.workflow_resume("thread-123")

    assert paused["status"] == "pause_requested"
    assert paused["thread_id"] == "thread-123"
    assert resumed["status"] == "running"
    assert resumed["thread_id"] == "thread-123"
