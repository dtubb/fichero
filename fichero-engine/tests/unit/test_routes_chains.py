"""Tests for workflow chain routes.

Chains compose multiple workflows into sequenced pipelines with output mapping
between steps. Uses an in-memory store. Dev-tier feature.
"""

import pytest
from unittest.mock import patch, AsyncMock

from fichero.workflows.chaining import (
    chain_store,
    ChainExecutionResult,
    ChainStepResult,
    ChainStepStatus,
)


@pytest.fixture(autouse=True)
def clear_chain_store():
    """Reset the in-memory chain store between tests."""
    chain_store._chains.clear()
    yield
    chain_store._chains.clear()


def _chain_payload(name: str = "Test Chain") -> dict:
    return {
        "name": name,
        "description": "A test chain",
        "steps": [
            {
                "id": "step-1",
                "workflow_id": "wf-abc",
                "name": "First Step",
                "input_mappings": [],
                "static_inputs": {},
                "continue_on_error": False,
                "timeout_seconds": 300,
            }
        ],
        "entry_step": "step-1",
        "initial_inputs": {},
    }


class TestListChains:
    def test_empty_list(self, client):
        r = client.get("/api/chains")
        assert r.status_code == 200
        assert r.json()["chains"] == []

    def test_returns_created_chains(self, client):
        client.post("/api/chains", json=_chain_payload("Chain A"))
        client.post("/api/chains", json=_chain_payload("Chain B"))
        r = client.get("/api/chains")
        assert r.status_code == 200
        assert r.json()["total"] == 2


class TestCreateChain:
    def test_create_chain(self, client):
        r = client.post("/api/chains", json=_chain_payload("My Chain"))
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "My Chain"
        assert "id" in data
        assert data["folder_path"] == "/"
        assert data["sort_order"] == 0

    def test_missing_name_rejected(self, client):
        payload = _chain_payload()
        payload["name"] = ""
        r = client.post("/api/chains", json=payload)
        assert r.status_code == 422

    def test_create_chain_preserves_nested_dynamic_inputs(self, client):
        payload = _chain_payload("Nested Inputs")
        payload["initial_inputs"] = {
            "document_id": "doc-1",
            "options": {"mode": "full", "retries": 2},
            "labels": ["alpha", "beta"],
        }
        payload["steps"][0]["static_inputs"] = {
            "threshold": 0.85,
            "flags": {"strict": True},
        }
        r = client.post("/api/chains", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["initial_inputs"] == payload["initial_inputs"]
        assert data["steps"][0]["static_inputs"] == payload["steps"][0]["static_inputs"]


class TestGetChain:
    def test_get_existing_chain(self, client):
        created = client.post("/api/chains", json=_chain_payload()).json()
        r = client.get(f"/api/chains/{created['id']}")
        assert r.status_code == 200
        assert r.json()["id"] == created["id"]

    def test_get_missing_returns_404(self, client):
        r = client.get("/api/chains/nonexistent-id")
        assert r.status_code == 404


class TestUpdateChain:
    def test_update_name(self, client):
        created = client.post("/api/chains", json=_chain_payload("Old Name")).json()
        update = _chain_payload("New Name")
        r = client.put(f"/api/chains/{created['id']}", json=update)
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    def test_update_missing_returns_404(self, client):
        r = client.put("/api/chains/no-such-id", json=_chain_payload())
        assert r.status_code == 404


class TestDeleteChain:
    def test_delete_chain(self, client):
        created = client.post("/api/chains", json=_chain_payload()).json()
        r = client.delete(f"/api/chains/{created['id']}")
        assert r.status_code == 200
        r2 = client.get(f"/api/chains/{created['id']}")
        assert r2.status_code == 404

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/chains/no-such-id")
        assert r.status_code == 404


class TestExecuteChain:
    def test_execute_chain_returns_execution_id_and_status(self, client):
        created = client.post("/api/chains", json=_chain_payload("Runnable")).json()

        fake_result = ChainExecutionResult(
            chain_id=created["id"],
            execution_id="exec-fixed",
            status=ChainStepStatus.COMPLETED,
            step_results=[
                ChainStepResult(
                    step_id="step-1",
                    workflow_id="wf-abc",
                    status=ChainStepStatus.COMPLETED,
                    outputs={"text": "ok"},
                    output_files=["/tmp/out.txt"],
                )
            ],
            final_outputs={"text": "ok"},
            final_files=["/tmp/out.txt"],
        )

        with patch(
            "fichero.api.routes.chains.ChainExecutor.execute",
            new_callable=AsyncMock,
        ) as mock_execute:
            mock_execute.return_value = fake_result
            r = client.post(
                f"/api/chains/{created['id']}/execute",
                json={
                    "inputs": {
                        "k": "v",
                        "library_path": "/tmp/other-library.fichero",
                    },
                    "input_files": ["/tmp/in.txt"],
                },
                headers={"X-Fichero-Library-Path": "/tmp/test.fichero"},
            )

        assert r.status_code == 200
        payload = r.json()
        assert payload["chain_id"] == created["id"]
        assert payload["status"] == "running"
        assert payload["execution_id"]

        status = client.get(f"/api/chains/executions/{payload['execution_id']}")
        assert status.status_code == 200
        body = status.json()
        assert body["status"] == "completed"
        assert body["final_outputs"] == {"text": "ok"}
        assert body["final_files"] == ["/tmp/out.txt"]
        assert len(body["step_results"]) == 1
        assert body["step_results"][0]["step_id"] == "step-1"
        mock_execute.assert_awaited_once()
        initial_inputs = mock_execute.await_args.kwargs["initial_inputs"]
        assert initial_inputs["k"] == "v"
        assert initial_inputs["library_path"] == "/tmp/test.fichero"

    def test_execute_missing_chain_returns_404(self, client):
        r = client.post(
            "/api/chains/no-such-id/execute",
            json={"inputs": {}, "input_files": []},
            headers={"X-Fichero-Library-Path": "/tmp/test.fichero"},
        )
        assert r.status_code == 404

    def test_cancel_execution(self, client):
        created = client.post("/api/chains", json=_chain_payload("Runnable")).json()
        pending_result = ChainExecutionResult(
            chain_id=created["id"],
            execution_id="exec-pending",
            status=ChainStepStatus.PENDING,
        )

        with patch(
            "fichero.api.routes.chains.ChainExecutor.execute",
            new_callable=AsyncMock,
        ) as mock_execute:
            mock_execute.return_value = pending_result
            r = client.post(
                f"/api/chains/{created['id']}/execute",
                json={"inputs": {}, "input_files": []},
                headers={"X-Fichero-Library-Path": "/tmp/test.fichero"},
            )

        assert r.status_code == 200
        execution_id = r.json()["execution_id"]
        cancel = client.delete(f"/api/chains/executions/{execution_id}")
        assert cancel.status_code == 200
        assert cancel.json()["execution_id"] == execution_id


class TestChainOpenAPISchema:
    def test_chain_schema_uses_typed_steps_and_documented_dynamic_inputs(self, client):
        schema = client.app.openapi()
        create_request = schema["components"]["schemas"]["CreateChainRequest"]
        update_request = schema["components"]["schemas"]["UpdateChainRequest"]
        execute_request = schema["components"]["schemas"]["ExecuteChainRequest"]
        chain_response = schema["components"]["schemas"]["ChainResponse"]
        step_request = schema["components"]["schemas"]["ChainStepRequest"]
        step_response = schema["components"]["schemas"]["ChainStepResponse"]
        execution_status = schema["components"]["schemas"]["ChainExecutionStatusResponse"]

        assert create_request["properties"]["steps"]["items"]["$ref"].endswith("/ChainStepRequest")
        assert chain_response["properties"]["steps"]["items"]["$ref"].endswith("/ChainStepResponse")
        assert chain_response["properties"]["folder_path"]["type"] == "string"
        assert chain_response["properties"]["sort_order"]["type"] == "integer"
        assert (
            "Free-form JSON inputs for the chain entrypoint"
            in create_request["properties"]["initial_inputs"]["description"]
        )
        assert (
            "Free-form JSON inputs for the chain entrypoint"
            in update_request["properties"]["initial_inputs"]["description"]
        )
        assert (
            "workflow chain defines its own input contract"
            in execute_request["properties"]["inputs"]["description"]
        )
        assert (
            "Values stay workflow-defined and are not coerced."
            in step_request["properties"]["static_inputs"]["description"]
        )
        assert (
            "Values stay workflow-defined and are not coerced."
            in step_response["properties"]["static_inputs"]["description"]
        )
        assert (
            "Output shape remains workflow-defined."
            in execution_status["properties"]["final_outputs"]["description"]
        )
        assert execution_status["properties"]["final_files"]["items"]["type"] == "string"
