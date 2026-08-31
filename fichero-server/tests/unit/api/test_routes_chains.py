"""Tests for workflow chain routes.

Chains compose multiple workflows into sequenced pipelines with output mapping
between steps. Uses an in-memory store. Dev-tier feature.
"""

import time

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from fichero_server.api.routes.workflow import chains as chain_routes

from fichero_server.execution.chaining import (
    chain_store,
    ChainExecutionResult,
    ChainStepResult,
    ChainStepStatus,
)


@pytest.fixture(autouse=True)
def clear_chain_store():
    """Reset the in-memory chain store between tests."""
    chain_store._chains.clear()
    chain_routes._running_executions.clear()
    chain_routes._running_executors.clear()
    chain_routes._execution_events.clear()
    yield
    chain_store._chains.clear()
    chain_routes._running_executions.clear()
    chain_routes._running_executors.clear()
    chain_routes._execution_events.clear()


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
            "fichero_server.api.routes.workflow.chains.ChainExecutor.execute",
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
            "fichero_server.api.routes.workflow.chains.ChainExecutor.execute",
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

    def test_cancel_execution_signals_running_executor(self, client):
        executor = MagicMock()
        chain_routes._running_executions["exec-running"] = ChainExecutionResult(
            chain_id="chain-1",
            execution_id="exec-running",
            status=ChainStepStatus.PENDING,
        )
        chain_routes._running_executors["exec-running"] = executor

        cancel = client.delete("/api/chains/executions/exec-running")

        assert cancel.status_code == 200
        assert cancel.json()["cancelled"] is True
        executor.cancel.assert_called_once_with()


LIB_HEADER = {"X-Fichero-Library-Path": "/tmp/test.fichero"}


def _steps_payload(name: str = "Bar Chain", steps: list[dict] | None = None) -> dict:
    """A chain payload for the step-wise runner (workflow bar shape)."""
    return {
        "name": name,
        "description": "",
        "steps": steps
        or [
            {
                "id": "s1",
                "workflow_id": "wf-1",
                "name": "Transcribe",
                "static_inputs": {"stage": "A"},
                "provider_override": "anthropic",
                "model_override": "claude-opus-4-7",
            },
            {
                "id": "s2",
                "workflow_id": "wf-2",
                "name": "Entities",
                "provider_override": "apple",
                "model_override": "afm-on-device",
            },
        ],
        "entry_step": None,
        "initial_inputs": {},
    }


def _wait_terminal(client, execution_id: str, timeout: float = 5.0) -> dict:
    """Poll the status endpoint until the runner thread settles the chain."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/chains/executions/{execution_id}")
        assert r.status_code == 200
        body = r.json()
        if body["status"] in ("completed", "failed", "cancelled"):
            return body
        time.sleep(0.02)
    raise AssertionError("chain step execution did not reach a terminal status")


def _fake_workflow(name: str = "WF"):
    wf = MagicMock()
    wf.name = name
    wf.nodes = []
    wf.edges = []
    return wf


def _steps_seams(outcomes: list[tuple[str, str | None]]):
    """Patch every engine seam the step runner crosses; returns the patchers.

    `outcomes` are consumed in run order — one per step that actually RUNS.
    """
    run_mock = AsyncMock()
    return {
        "db": patch.object(chain_routes, "_acquire_chain_db", return_value=MagicMock()),
        "load": patch.object(
            chain_routes, "_load_step_workflow", side_effect=lambda db, wid: _fake_workflow(wid)
        ),
        "validate": patch.object(chain_routes, "_validate_step_workflow"),
        "record": patch.object(
            chain_routes, "_record_step_run_accepted", new_callable=AsyncMock
        ),
        "run": patch.object(chain_routes, "_run_step_workflow", run_mock),
        "outcome": patch.object(
            chain_routes, "_step_run_outcome", side_effect=list(outcomes)
        ),
    }


class TestExecuteChainSteps:
    """POST /chains/{id}/execute-steps — the workflow bar's engine-side chain.

    Every step is a real workflow run (thread id assigned up front), run in
    LIST order, sequentially, with per-step provider/model overrides and
    engine-owned stop-on-failure (2026-08-30 ruling).
    """

    def _create(self, client, payload=None):
        r = client.post("/api/chains", json=payload or _steps_payload())
        assert r.status_code == 200
        return r.json()

    def test_accepts_with_preassigned_thread_ids(self, client):
        created = self._create(client)
        seams = _steps_seams([("completed", None), ("completed", None)])
        with seams["db"], seams["load"], seams["validate"], seams["record"], \
                seams["run"], seams["outcome"]:
            r = client.post(
                f"/api/chains/{created['id']}/execute-steps",
                json={"inputs": {"selected_doc_ids": ["d1"]}},
                headers=LIB_HEADER,
            )
            assert r.status_code == 202
            body = r.json()
            assert body["chain_id"] == created["id"]
            assert body["status"] == "running"
            steps = body["steps"]
            assert [s["step_id"] for s in steps] == ["s1", "s2"]
            # Thread ids are distinct, assigned NOW (a client can watch a
            # step's run the moment it starts), and the stream URL points at
            # the real SSE handler.
            assert len({s["thread_id"] for s in steps}) == 2
            for s in steps:
                assert s["thread_id"].startswith("thread-")
                assert s["stream_url"].endswith(
                    f"/api/workflow-execution/stream/{s['thread_id']}"
                )
            final = _wait_terminal(client, body["execution_id"])
        assert final["status"] == "completed"
        assert [sr["status"] for sr in final["step_results"]] == [
            "completed",
            "completed",
        ]

    def test_steps_run_in_order_with_per_step_overrides(self, client):
        created = self._create(client)
        seams = _steps_seams([("completed", None), ("completed", None)])
        with seams["db"], seams["load"], seams["validate"], seams["record"], \
                seams["run"] as run_mock, seams["outcome"]:
            r = client.post(
                f"/api/chains/{created['id']}/execute-steps",
                json={"inputs": {"selected_doc_ids": ["d1", "d2"], "user_context": "17th c."}},
                headers=LIB_HEADER,
            )
            assert r.status_code == 202
            _wait_terminal(client, r.json()["execution_id"])

        requests = [call.kwargs["request"] for call in run_mock.await_args_list]
        # Sequential, in list order — step two must not start before step one.
        assert [req.workflow_id for req in requests] == ["wf-1", "wf-2"]
        # Each step carries ITS OWN pin, not a chain-wide one.
        assert requests[0].provider_override == "anthropic"
        assert requests[0].model_override == "claude-opus-4-7"
        assert requests[1].provider_override == "apple"
        assert requests[1].model_override == "afm-on-device"
        # The frozen chain inputs ride every step; static_inputs win on top.
        assert requests[0].inputs["selected_doc_ids"] == ["d1", "d2"]
        assert requests[0].inputs["user_context"] == "17th c."
        assert requests[0].inputs["stage"] == "A"
        assert requests[1].inputs["selected_doc_ids"] == ["d1", "d2"]
        # Pre-assigned thread id is the one the run actually used.
        assert [call.kwargs["thread_id"] for call in run_mock.await_args_list] == [
            req.thread_id for req in requests
        ]

    def test_stop_on_failure_skips_later_steps(self, client):
        payload = _steps_payload(
            steps=[
                {"id": "s1", "workflow_id": "wf-1", "name": "A"},
                {"id": "s2", "workflow_id": "wf-2", "name": "B"},
                {"id": "s3", "workflow_id": "wf-3", "name": "C"},
            ]
        )
        created = self._create(client, payload)
        seams = _steps_seams([("failed", "boom")])
        with seams["db"], seams["load"], seams["validate"], seams["record"], \
                seams["run"] as run_mock, seams["outcome"]:
            r = client.post(
                f"/api/chains/{created['id']}/execute-steps",
                json={"inputs": {}},
                headers=LIB_HEADER,
            )
            assert r.status_code == 202
            final = _wait_terminal(client, r.json()["execution_id"])

        # The engine owns stop-on-failure: step B never spends money on the
        # transcription step A did not produce.
        assert run_mock.await_count == 1
        assert final["status"] == "failed"
        statuses = {sr["step_id"]: sr["status"] for sr in final["step_results"]}
        assert statuses == {"s1": "failed", "s2": "skipped", "s3": "skipped"}
        failed = next(sr for sr in final["step_results"] if sr["step_id"] == "s1")
        assert failed["error"] == "boom"

    def test_continue_on_error_runs_next_step(self, client):
        payload = _steps_payload(
            steps=[
                {"id": "s1", "workflow_id": "wf-1", "continue_on_error": True},
                {"id": "s2", "workflow_id": "wf-2"},
            ]
        )
        created = self._create(client, payload)
        seams = _steps_seams([("failed", "boom"), ("completed", None)])
        with seams["db"], seams["load"], seams["validate"], seams["record"], \
                seams["run"] as run_mock, seams["outcome"]:
            r = client.post(
                f"/api/chains/{created['id']}/execute-steps",
                json={"inputs": {}},
                headers=LIB_HEADER,
            )
            assert r.status_code == 202
            final = _wait_terminal(client, r.json()["execution_id"])

        assert run_mock.await_count == 2
        statuses = {sr["step_id"]: sr["status"] for sr in final["step_results"]}
        assert statuses == {"s1": "failed", "s2": "completed"}
        # A tolerated failure does not fail the chain.
        assert final["status"] == "completed"

    def test_missing_workflow_fails_step_and_stops(self, client):
        created = self._create(client)
        seams = _steps_seams([])
        with seams["db"], seams["validate"], seams["record"], seams["run"] as run_mock, \
                patch.object(chain_routes, "_load_step_workflow", return_value=None):
            r = client.post(
                f"/api/chains/{created['id']}/execute-steps",
                json={"inputs": {}},
                headers=LIB_HEADER,
            )
            assert r.status_code == 202
            final = _wait_terminal(client, r.json()["execution_id"])

        # An unrealisable step STOPS the chain, exactly as a failed run does.
        assert run_mock.await_count == 0
        assert final["status"] == "failed"
        statuses = [sr["status"] for sr in final["step_results"]]
        assert statuses == ["failed", "skipped"]

    def test_missing_chain_returns_404(self, client):
        r = client.post(
            "/api/chains/no-such-id/execute-steps",
            json={"inputs": {}},
            headers=LIB_HEADER,
        )
        assert r.status_code == 404

    def test_empty_chain_returns_400(self, client):
        created = self._create(client, {"name": "Empty", "steps": []})
        r = client.post(
            f"/api/chains/{created['id']}/execute-steps",
            json={"inputs": {}},
            headers=LIB_HEADER,
        )
        assert r.status_code == 400

    def test_overrides_round_trip_through_chain_crud(self, client):
        created = self._create(client)
        step = created["steps"][0]
        assert step["provider_override"] == "anthropic"
        assert step["model_override"] == "claude-opus-4-7"
        fetched = client.get(f"/api/chains/{created['id']}").json()
        assert fetched["steps"][1]["model_override"] == "afm-on-device"


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
