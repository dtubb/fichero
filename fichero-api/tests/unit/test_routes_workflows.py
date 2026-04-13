"""Tests for workflow route endpoints.

Workflows are LangGraph node-graphs persisted to the library database.
Routes handle CRUD plus tool/node discovery for the visual node editor.
Tests use real in-memory DB fixtures; no LLM or graph execution.
"""

import pytest
from fichero.models import Workflow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _workflow_payload(name: str = "Test Workflow") -> dict:
    """Minimal valid WorkflowDef payload."""
    return {
        "name": name,
        "description": "A test workflow",
        "nodes": [],
        "edges": [],
    }


def _make_workflow(db, name: str = "Test Workflow") -> Workflow:
    wf = Workflow(
        name=name,
        description="A test workflow",
        format="nodes",
        steps=[],
    )
    db.save(wf)
    return wf


# ---------------------------------------------------------------------------
# GET /api/workflows — list
# ---------------------------------------------------------------------------


class TestListWorkflows:
    def test_empty_list(self, client):
        r = client.get("/api/workflows")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_saved_workflows(self, client, db):
        _make_workflow(db, "Workflow A")
        _make_workflow(db, "Workflow B")
        r = client.get("/api/workflows")
        assert r.status_code == 200
        assert len(r.json()) == 2


# ---------------------------------------------------------------------------
# POST /api/workflows — create
# ---------------------------------------------------------------------------


class TestCreateWorkflow:
    def test_create_workflow(self, client):
        r = client.post("/api/workflows", json=_workflow_payload("My Workflow"))
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "My Workflow"
        assert "id" in data

    def test_create_with_empty_nodes(self, client):
        r = client.post("/api/workflows", json=_workflow_payload())
        assert r.status_code == 200
        assert r.json()["nodes"] == []
        assert r.json()["edges"] == []


# ---------------------------------------------------------------------------
# GET /api/workflows/{workflow_id}
# ---------------------------------------------------------------------------


class TestGetWorkflow:
    def test_get_existing(self, client, db):
        wf = _make_workflow(db)
        r = client.get(f"/api/workflows/{wf.id}")
        assert r.status_code == 200
        assert r.json()["id"] == wf.id

    def test_get_missing_returns_404(self, client):
        r = client.get("/api/workflows/no-such-workflow")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/workflows/{workflow_id}
# ---------------------------------------------------------------------------


class TestPatchWorkflow:
    def test_rename_workflow(self, client, db):
        wf = _make_workflow(db, "Old Name")
        r = client.patch(f"/api/workflows/{wf.id}", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    def test_move_to_folder(self, client, db):
        wf = _make_workflow(db)
        r = client.patch(f"/api/workflows/{wf.id}", json={"folder_path": "/my-folder"})
        assert r.status_code == 200
        assert r.json()["folder_path"] == "/my-folder"

    def test_patch_missing_returns_404(self, client):
        r = client.patch("/api/workflows/no-such-id", json={"name": "X"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/workflows/{workflow_id}
# ---------------------------------------------------------------------------


class TestDeleteWorkflow:
    def test_delete_removes_workflow(self, client, db):
        wf = _make_workflow(db)
        r = client.delete(f"/api/workflows/{wf.id}")
        assert r.status_code == 200
        r2 = client.get(f"/api/workflows/{wf.id}")
        assert r2.status_code == 404

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/workflows/no-such-id")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/workflows/{workflow_id}/duplicate
# ---------------------------------------------------------------------------


class TestDuplicateWorkflow:
    def test_duplicate_creates_copy(self, client, db):
        wf = _make_workflow(db, "Original")
        r = client.post(f"/api/workflows/{wf.id}/duplicate")
        assert r.status_code == 200
        copy = r.json()
        assert copy["id"] != wf.id
        assert "Copy" in copy["name"]

    def test_duplicate_missing_returns_404(self, client):
        r = client.post("/api/workflows/no-such-id/duplicate")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/workflows/{workflow_id}/export
# ---------------------------------------------------------------------------


class TestExportWorkflow:
    def test_export_returns_workflow_data(self, client, db):
        wf = _make_workflow(db, "Export Me")
        r = client.get(f"/api/workflows/{wf.id}/export")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Export Me"
        assert "nodes" in data
        assert "edges" in data

    def test_export_missing_returns_404(self, client):
        r = client.get("/api/workflows/no-such-id/export")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/workflows/tools
# ---------------------------------------------------------------------------


class TestListWorkflowTools:
    def test_returns_tools_list(self, client):
        r = client.get("/api/workflows/tools")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_tools_grouped(self, client):
        r = client.get("/api/workflows/tools/grouped")
        assert r.status_code == 200
        data = r.json()
        assert "categories" in data
        assert isinstance(data["categories"], list)
