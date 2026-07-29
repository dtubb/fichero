"""Tests for workflow route endpoints.

Workflows are LangGraph node-graphs persisted to the library database.
Routes handle CRUD plus tool/node discovery for the visual node editor.
Tests use real in-memory DB fixtures; no LLM or graph execution.
"""

import pytest
from unittest.mock import patch

from fichero_server.models import Workflow
from fichero_server.api.routes.workflows import create_workflow_impl
from fichero_server.workflows.types import EdgeDef, NodeDef, WorkflowDef


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


def _make_workflow(db, name: str = "Test Workflow", **kwargs) -> Workflow:
    wf = Workflow(
        name=name,
        description="A test workflow",
        format="nodes",
        steps=[],
        **kwargs,
    )
    db.save(wf)
    return wf


# ---------------------------------------------------------------------------
# GET /api/workflows — list
# ---------------------------------------------------------------------------


class TestListWorkflows:
    def test_route_map_edge_survives_database_round_trip(self, client, db):
        definition = WorkflowDef(
            name="Routed",
            nodes=[NodeDef(id="classify", tool="classify"), NodeDef(id="transcribe", tool="transcribe")],
            edges=[EdgeDef(
                id="edge-route", source="classify", target="",
                route_key="$.nodes.classify.script_type", route_map={"typescript": "transcribe"},
            )],
        )
        workflow = create_workflow_impl(db, definition)

        response = client.get("/api/workflows")

        assert response.status_code == 200
        routed = next(item for item in response.json()["items"] if item["id"] == workflow.id)
        assert routed["edges"][0]["route_key"] == "$.nodes.classify.script_type"
        assert routed["edges"][0]["route_map"] == {"typescript": "transcribe"}

    def test_empty_list(self, client):
        r = client.get("/api/workflows")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_returns_saved_workflows(self, client, db):
        _make_workflow(db, "Workflow A")
        _make_workflow(db, "Workflow B")
        r = client.get("/api/workflows")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2
        assert all("format" in item for item in r.json()["items"])

    def test_unfiltered_list_includes_non_root_folder_paths(self, client, db):
        # Regression for #723: list endpoint must return workflows in any
        # folder when caller omits folder_path. Pre-fix it filtered to "/"
        # by default, hiding default templates seeded under /Transcribe and
        # /Catalogue.
        root = Workflow(name="Root", format="nodes", steps=[], folder_path="/")
        catalogue = Workflow(
            name="Catalogue", format="nodes", steps=[], folder_path="/Catalogue"
        )
        db.save(root)
        db.save(catalogue)
        r = client.get("/api/workflows")
        assert r.status_code == 200
        names = {w["name"] for w in r.json()["items"]}
        assert {"Root", "Catalogue"} <= names

    def test_explicit_folder_path_still_filters(self, client, db):
        db.save(Workflow(name="Root", format="nodes", steps=[], folder_path="/"))
        db.save(
            Workflow(name="Cat", format="nodes", steps=[], folder_path="/Catalogue")
        )
        r = client.get("/api/workflows", params={"folder_path": "/Catalogue"})
        assert r.status_code == 200
        names = {w["name"] for w in r.json()["items"]}
        assert names == {"Cat"}

    def test_list_uses_database_workflow_reader_for_folder_filter(self, client, db, monkeypatch):
        db.save(Workflow(name="Root", format="nodes", steps=[], folder_path="/"))
        catalogue = Workflow(name="Cat", format="nodes", steps=[], folder_path="/Catalogue")
        db.save(catalogue)
        calls = []
        real_workflow_rows_for_list = db.workflow_rows_for_list

        def recording_workflow_rows_for_list(folder_path=None):
            calls.append(folder_path)
            return real_workflow_rows_for_list(folder_path)

        monkeypatch.setattr(db, "workflow_rows_for_list", recording_workflow_rows_for_list)

        response = client.get("/api/workflows", params={"folder_path": "/Catalogue"})

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["items"]] == [catalogue.id]
        assert calls == ["/Catalogue"]

    def test_list_marks_system_preset_untested_unless_config_opted_in(self, client, db):
        _make_workflow(
            db,
            "Shipped Preset",
            is_system=True,
            config={"preset_version": 2},
        )
        _make_workflow(
            db,
            "Trusted Preset",
            is_system=True,
            config={"tested": True},
        )
        _make_workflow(db, "User Workflow", is_system=False, config={"tested": True})

        response = client.get("/api/workflows")

        assert response.status_code == 200
        by_name = {item["name"]: item for item in response.json()["items"]}
        assert by_name["Shipped Preset"]["untested"] is True
        assert by_name["Trusted Preset"]["untested"] is False
        assert by_name["User Workflow"]["untested"] is False

    def test_list_marks_sub_workflow_components_not_directly_runnable(self, client, db):
        _make_workflow(
            db,
            "Internal Child",
            is_system=True,
            config={"input_contract": [{"id": "files", "required": True}]},
        )
        _make_workflow(db, "Direct Workflow", is_system=True, config={})

        response = client.get("/api/workflows")

        assert response.status_code == 200
        by_name = {item["name"]: item for item in response.json()["items"]}
        assert by_name["Internal Child"]["direct_runnable"] is False
        assert by_name["Direct Workflow"]["direct_runnable"] is True


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
        assert data["format"] == "nodes"

    def test_create_with_empty_nodes(self, client):
        r = client.post("/api/workflows", json=_workflow_payload())
        assert r.status_code == 200
        assert r.json()["nodes"] == []
        assert r.json()["edges"] == []

    def test_create_response_never_flags_user_workflow_untested(self, client):
        response = client.post("/api/workflows", json=_workflow_payload("User Flow"))

        assert response.status_code == 200
        assert response.json()["untested"] is False


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

    def test_updates_format(self, client, db):
        wf = _make_workflow(db)
        r = client.patch(f"/api/workflows/{wf.id}", json={"format": "table"})
        assert r.status_code == 200
        assert r.json()["format"] == "table"

    def test_patch_missing_returns_404(self, client):
        r = client.patch("/api/workflows/no-such-id", json={"name": "X"})
        assert r.status_code == 404


class TestUpdateWorkflow:
    def test_put_updates_without_stdout_debug_prints(self, client, db):
        wf = Workflow(
            name="Old Workflow",
            description="Before",
            format="nodes",
            nodes=[{"id": "source", "tool": "files"}],
            edges=[],
            steps=[],
        )
        db.save(wf)

        payload = {
            "id": wf.id,
            "name": "Updated Workflow",
            "description": "After",
            "format": "nodes",
            "nodes": [{"id": "source", "tool": "files"}],
            "edges": [],
        }

        with patch("builtins.print") as print_spy:
            r = client.put(f"/api/workflows/{wf.id}", json=payload)

        assert r.status_code == 200
        assert r.json()["name"] == "Updated Workflow"
        print_spy.assert_not_called()


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

    def test_duplicate_preserves_metadata_but_drops_is_system(self, client, db):
        """#11 Phase 1: a duplicate is always a personal, editable, writable
        copy — is_system (and therefore the folded-document mirror's
        read_only/scope=global) never carries over to a duplicate, even of a
        locked default preset. Everything else about the preset (template
        flag, tags, config) still copies across."""
        wf = _make_workflow(
            db,
            "Preset",
            is_system=True,
            is_template=True,
            tags=["preset"],
            config={"preset_version": 3},
        )

        response = client.post(f"/api/workflows/{wf.id}/duplicate")

        assert response.status_code == 200
        payload = response.json()
        # untested is `is_system and not config.tested` (_workflow_untested)
        # — since the duplicate drops is_system, it's no longer flagged as
        # an unreviewed shipped preset; it's the user's own copy now.
        assert payload["untested"] is False

        duplicate = db.get(Workflow, payload["id"])
        assert duplicate is not None
        assert duplicate.is_system is False
        assert duplicate.is_template is True
        assert duplicate.tags == ["preset"]
        assert duplicate.config == {"preset_version": 3}

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


class TestImportWorkflow:
    def test_import_workflow_success(self, client):
        r = client.post(
            "/api/workflows/import",
            params={
                "name": "Imported",
                "description": "Imported from JSON",
            },
            json={
                "name": "Original Name",
                "nodes": [],
                "edges": [],
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Imported"
        assert data["description"] == "Imported from JSON"
        assert data["format"] == "nodes"
        assert data["nodes"] == []
        assert data["edges"] == []

    def test_import_response_never_flags_user_workflow_untested(self, client):
        response = client.post(
            "/api/workflows/import",
            json={
                "name": "Imported Name",
                "nodes": [],
                "edges": [],
            },
        )

        assert response.status_code == 200
        assert response.json()["untested"] is False

    def test_import_missing_nodes_or_edges_returns_400(self, client):
        r = client.post(
            "/api/workflows/import",
            json={"name": "Bad Import", "nodes": []},
        )
        assert r.status_code == 400
        assert "missing nodes or edges" in r.json()["detail"]

    def test_import_rejects_malformed_node_payload(self, client):
        r = client.post(
            "/api/workflows/import",
            json={
                "name": "Bad Import",
                "nodes": [{"id": "n1", "tool": "files", "input_mappings": "nope"}],
                "edges": [],
            },
        )
        assert r.status_code == 400
        assert "node[0] failed validation" in r.json()["detail"]

    def test_list_skips_preexisting_poisoned_workflow_row(self, client, db, caplog):
        good = Workflow(
            name="Good Workflow",
            description="",
            format="nodes",
            nodes=[],
            edges=[],
            steps=[],
            sort_order=0,
        )
        bad = Workflow.model_construct(
            name="Poisoned Workflow",
            description="",
            format="nodes",
            nodes=[{"id": "n1", "tool": "files", "input_mappings": "nope"}],
            edges=[],
            steps=[],
            sort_order=1,
        )
        db.save(good)
        db.save(bad)

        with caplog.at_level("WARNING"):
            r = client.get("/api/workflows")

        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert [item["name"] for item in data["items"]] == ["Good Workflow"]
        assert "Skipping invalid workflow" in caplog.text


class TestEstimateWorkflowCost:
    def test_estimate_cost_uses_workflow_model_pricing(self, client, db, monkeypatch):
        wf = Workflow(
            name="Costed Workflow",
            description="",
            format="nodes",
            steps=[],
            provider="openai",
            model="gpt-4o-mini",
        )
        db.save(wf)

        def _fake_cost(model_name: str):
            if "gpt-4o-mini" in model_name:
                return {
                    "input_cost_per_token": 1e-6,
                    "output_cost_per_token": 2e-6,
                }
            return None

        monkeypatch.setattr("fichero_server.api.routes.workflows.get_model_cost", _fake_cost)

        r = client.post(
            f"/api/workflows/{wf.id}/estimate-cost",
            json={
                "file_count": 3,
                "estimated_input_tokens_per_file": 1000,
                "estimated_output_tokens_per_file": 200,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4o-mini"
        assert data["estimated_input_tokens"] == 3000
        assert data["estimated_output_tokens"] == 600
        assert data["pricing_available"] is True
        assert data["estimated_cost_usd"] == pytest.approx(0.0042, rel=1e-9)

    def test_estimate_cost_missing_workflow_returns_404(self, client):
        r = client.post(
            "/api/workflows/no-such-id/estimate-cost",
            json={"file_count": 2},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/workflows/tools
# ---------------------------------------------------------------------------


class TestListWorkflowTools:
    def test_returns_tools_list(self, client):
        r = client.get("/api/workflows/tools")
        assert r.status_code == 200
        assert isinstance(r.json()["items"], list)

    def test_tools_list_exposes_tested_flag(self, client):
        response = client.get("/api/workflows/tools")

        assert response.status_code == 200
        by_name = {item["name"]: item for item in response.json()["items"]}
        assert by_name["transcribe"]["tested"] is True
        assert by_name["describe"]["tested"] is False

    def test_tools_grouped(self, client):
        r = client.get("/api/workflows/tools/grouped")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_grouped_tools_preserve_tested_flag(self, client):
        response = client.get("/api/workflows/tools/grouped")

        assert response.status_code == 200
        grouped = {
            tool["name"]: tool
            for group in response.json()["items"]
            for tool in group["tools"]
        }
        assert grouped["transcribe"]["tested"] is True
        assert grouped["describe"]["tested"] is False

    def test_get_single_tool_exposes_tested_flag(self, client):
        response = client.get("/api/workflows/tools/transcribe")

        assert response.status_code == 200
        assert response.json()["name"] == "transcribe"
        assert response.json()["tested"] is True

    def test_get_single_tool_missing_returns_404(self, client):
        response = client.get("/api/workflows/tools/no-such-tool")

        assert response.status_code == 404
        assert "Tool not found" in response.json()["detail"]

    def test_create_node_from_tool(self, client, monkeypatch):
        calls: list[tuple] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.workflows.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )

        r = client.post(
            "/api/workflows/tools/transcribe/create-node",
            params={"position_x": 40, "position_y": 80},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["tool"] == "transcribe"
        assert data["position_x"] == 40
        assert data["position_y"] == 80
        assert isinstance(data["input_ports"], list)
        assert isinstance(data["output_ports"], list)
        assert calls == []

    def test_generate_tool_prompt(self, client):
        r = client.post(
            "/api/workflows/tools/rewrite/prompt",
            json={"config": {"style": "formal", "target_language": "French"}},
        )
        assert r.status_code == 200
        prompt = r.json()["prompt"]
        assert "formal, professional tone" in prompt
        assert "Write the output in French." in prompt


class TestWorkflowModes:
    def test_modes_endpoint_is_gone(self, client):
        # /modes served a hardcoded list of EDITOR display modes — a pure UI
        # concern; deleted in the 2026-07-27 endpoint cleanup.
        assert client.get("/api/workflows/modes").status_code == 404
