"""Tests for workflow execution routes.

Workflow execution uses LangGraph checkpointing for durable pause/resume.
These tests verify route contract (status codes, request schema) and use
mocking for LangGraph-dependent paths.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from datetime import datetime

from langgraph.types import Send

from fichero_server.api.routes.workflow_execution.core import get_thread_status
from fichero_server.api.routes.workflow_execution.schemas import SSEEvent, format_sse
from fichero_server.api.routes.workflow_execution.runner import _missing_exit_nodes
from fichero_server.models import Artifact, Document, DocType, FileType, Status, Workflow
from fichero_server.workflows.activity import get_activity_tracker
from fichero_server.workflows.activity_types import WorkflowRun


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workflow(db, name: str = "Test Workflow") -> Workflow:
    wf = Workflow(
        name=name,
        description="A test workflow",
        format="nodes",
        nodes=[{"id": "source", "tool": "files"}],
        edges=[],
        steps=[],
    )
    db.save(wf)
    return wf


def _make_doc(db, name: str, *, doc_type: DocType = DocType.file) -> Document:
    doc = Document(
        name=name,
        doc_type=doc_type,
        file_type=FileType.pdf if name.endswith(".pdf") else FileType.image,
        path=f"/tmp/{name}",
        status=Status.completed,
    )
    db.save(doc)
    return doc


def _make_mock_checkpointer(thread_ids: list[str] | None = None):
    """Mock the AsyncDuckDBCheckpointer for thread operations."""
    cp = MagicMock()
    # Sync conn.execute result (returns empty result set by default)
    result_mock = MagicMock()
    result_mock.fetchall.return_value = [(tid,) for tid in (thread_ids or [])]
    cp.conn = MagicMock()
    cp.conn.execute.return_value = result_mock
    # Async methods
    cp.aget_tuple = AsyncMock(return_value=None)
    cp.alist = AsyncMock(return_value=iter([]))
    cp.adelete_thread = AsyncMock()
    cp.alist_threads = AsyncMock(return_value=[tid for tid in (thread_ids or [])])
    return cp


# ---------------------------------------------------------------------------
# GET /api/workflow-execution/threads — list threads
# ---------------------------------------------------------------------------


class TestWorkflowCompletionGuards:
    def test_missing_exit_nodes_returns_unfinished_exits(self):
        missing = _missing_exit_nodes(
            {"kg_writer", "catalogue"},
            {"catalogue"},
        )
        assert missing == {"kg_writer"}

    def test_missing_exit_nodes_allows_completed_exits(self):
        missing = _missing_exit_nodes(
            {"kg_writer", "catalogue"},
            {"kg_writer", "catalogue"},
        )
        assert missing == set()

    def test_missing_exit_nodes_allows_graphs_without_exit_detection(self):
        assert _missing_exit_nodes(set(), set()) == set()


class TestListThreads:
    def test_returns_empty_when_no_threads(self, client):
        mock_cp = _make_mock_checkpointer()
        with patch(
            "fichero_server.api.routes.workflow_execution.threads.AsyncDuckDBCheckpointer.from_db_path",
            return_value=mock_cp,
        ):
            r = client.get("/api/workflow-execution/threads")
        assert r.status_code == 200
        data = r.json()
        assert "threads" in data
        assert data["threads"] == []


# ---------------------------------------------------------------------------
# GET /api/workflow-execution/threads/{thread_id}/status
# ---------------------------------------------------------------------------


class TestGetThreadStatus:
    def test_returns_404_for_unknown_thread(self, client):
        mock_cp = _make_mock_checkpointer()
        mock_cp.aget_tuple = AsyncMock(return_value=None)
        with patch(
            "fichero_server.api.routes.workflow_execution.core.AsyncDuckDBCheckpointer.from_db_path",
            return_value=mock_cp,
        ):
            r = client.get("/api/workflow-execution/threads/nonexistent/status")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_sanitizes_langgraph_send_objects(self):
        """#1166: status polling must not 500 on pending LangGraph Send values."""
        checkpoint_tuple = MagicMock()
        checkpoint_tuple.checkpoint = {
            "id": "checkpoint-1",
            "channel_values": {
                "workflow_id": "unknown",
                "__pregel_tasks": [
                    Send("Transcribe each file_process", {"file": "/tmp/page.jpg"})
                ],
            },
        }
        checkpoint_tuple.metadata = {}
        checkpoint_tuple.pending_writes = []

        mock_cp = _make_mock_checkpointer()
        mock_cp.aget_tuple = AsyncMock(return_value=checkpoint_tuple)
        db = MagicMock()
        db.path = "/tmp/test.fichero/fichero.duckdb"

        with patch(
            "fichero_server.api.routes.workflow_execution.core.AsyncDuckDBCheckpointer.from_db_path",
            return_value=mock_cp,
        ):
            response = await get_thread_status("thread-1", db=db)

        # Pydantic JSON serialization is the failure mode from the live CLI.
        payload = response.model_dump_json()
        assert "Transcribe each file_process" in payload

    @pytest.mark.asyncio
    async def test_prefers_persisted_failed_run_over_clean_checkpoint(self):
        """A checkpoint without pending writes is not proof the run succeeded."""
        checkpoint_tuple = MagicMock()
        checkpoint_tuple.checkpoint = {
            "id": "checkpoint-1",
            "channel_values": {"workflow_id": "workflow-1"},
        }
        checkpoint_tuple.metadata = {}
        checkpoint_tuple.pending_writes = []

        mock_cp = _make_mock_checkpointer()
        mock_cp.aget_tuple = AsyncMock(return_value=checkpoint_tuple)
        db = MagicMock()
        db.path = "/tmp/test.fichero/fichero.duckdb"

        run = WorkflowRun(
            thread_id="thread-1",
            workflow_id="workflow-1",
            workflow_name="Stage 2",
            python_code="",
            execution_log="ERROR",
            status="failed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            duration_ms=1,
            error="not enough values to unpack",
            workflow_snapshot=None,
            node_name_map=None,
            progress_timeline=None,
            diagram_mermaid=None,
        )
        tracker = MagicMock()
        tracker.store.get_workflow_run = AsyncMock(return_value=run)

        with (
            patch(
                "fichero_server.api.routes.workflow_execution.core.AsyncDuckDBCheckpointer.from_db_path",
                return_value=mock_cp,
            ),
            patch(
                "fichero_server.api.routes.workflow_execution.core.get_activity_tracker",
                return_value=tracker,
            ),
        ):
            response = await get_thread_status("thread-1", db=db)

        assert response.status == "failed"
        assert response.error == "not enough values to unpack"


# ---------------------------------------------------------------------------
# DELETE /api/workflow-execution/threads/{thread_id}
# ---------------------------------------------------------------------------


class TestDeleteThread:
    def test_delete_missing_thread_returns_404(self, client):
        mock_cp = _make_mock_checkpointer()
        mock_cp.aget_tuple = AsyncMock(return_value=None)
        with patch(
            "fichero_server.api.routes.workflow_execution.threads.AsyncDuckDBCheckpointer.from_db_path",
            return_value=mock_cp,
        ):
            r = client.delete("/api/workflow-execution/threads/nonexistent")
        assert r.status_code == 404

    def test_delete_running_thread_returns_409(self, client):
        mock_cp = _make_mock_checkpointer()
        mock_cp.aget_tuple = AsyncMock(return_value=None)
        mock_store = MagicMock()
        mock_store.get_workflow_run = AsyncMock(
            return_value=WorkflowRun(
                thread_id="thread-accepted",
                workflow_id="wf-1",
                workflow_name="Accepted",
                python_code=None,
                execution_log=None,
                status="running",
                started_at=datetime.now(),
                completed_at=None,
                duration_ms=None,
                error=None,
                workflow_snapshot=None,
                node_name_map=None,
                progress_timeline=None,
                diagram_mermaid=None,
            )
        )
        tracker = MagicMock()
        tracker.store = mock_store

        with (
            patch(
                "fichero_server.api.routes.workflow_execution.threads.AsyncDuckDBCheckpointer.from_db_path",
                return_value=mock_cp,
            ),
            patch(
                "fichero_server.api.routes.workflow_execution.threads.get_activity_tracker",
                return_value=tracker,
            ),
        ):
            r = client.delete("/api/workflow-execution/threads/thread-accepted")

        assert r.status_code == 409
        mock_cp.adelete_thread.assert_not_called()

    def test_delete_terminal_thread_marks_deleted_without_checkpoint(self, client):
        mock_cp = _make_mock_checkpointer()
        mock_cp.aget_tuple = AsyncMock(return_value=None)
        mock_store = MagicMock()
        mock_store.get_workflow_run = AsyncMock(
            return_value=WorkflowRun(
                thread_id="thread-done",
                workflow_id="wf-1",
                workflow_name="Done",
                python_code=None,
                execution_log=None,
                status="completed",
                started_at=datetime.now(),
                completed_at=datetime.now(),
                duration_ms=1,
                error=None,
                workflow_snapshot=None,
                node_name_map=None,
                progress_timeline=None,
                diagram_mermaid=None,
            )
        )
        mock_store.delete_workflow_run = AsyncMock(return_value=1)
        tracker = MagicMock()
        tracker.store = mock_store

        with (
            patch(
                "fichero_server.api.routes.workflow_execution.threads.AsyncDuckDBCheckpointer.from_db_path",
                return_value=mock_cp,
            ),
            patch(
                "fichero_server.api.routes.workflow_execution.threads.get_activity_tracker",
                return_value=tracker,
            ),
        ):
            r = client.delete("/api/workflow-execution/threads/thread-done")

        assert r.status_code == 200
        mock_cp.adelete_thread.assert_not_called()
        mock_store.delete_workflow_run.assert_awaited_once_with("thread-done")
        tracker.workflow_deleted.assert_called_once()


# ---------------------------------------------------------------------------
# GET /api/workflow-execution/workflows/{workflow_id}/cache/stats
# ---------------------------------------------------------------------------


class TestCacheStats:
    def test_cache_stats_returns_200(self, client, db):
        wf = _make_workflow(db)
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {
            "total_entries": 5,
            "nodes_cached": 3,
            "tools_cached": 2,
            "oldest_entry": None,
            "newest_entry": None,
        }
        with patch(
            "fichero_server.api.routes.workflow_execution.cache.get_node_cache",
            return_value=mock_cache,
        ):
            r = client.get(f"/api/workflow-execution/workflows/{wf.id}/cache/stats")
        assert r.status_code == 200
        assert r.json()["total_entries"] == 5

    def test_cache_stats_for_existing_workflow(self, client, db):
        wf = _make_workflow(db)
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {
            "total_entries": 0,
            "nodes_cached": 0,
            "tools_cached": 0,
            "oldest_entry": None,
            "newest_entry": None,
        }
        with patch(
            "fichero_server.api.routes.workflow_execution.cache.get_node_cache",
            return_value=mock_cache,
        ):
            r = client.get(f"/api/workflow-execution/workflows/{wf.id}/cache/stats")
        assert r.status_code == 200

    def test_cache_stats_hides_internal_exception_details(self, client, db):
        wf = _make_workflow(db)
        with patch(
            "fichero_server.api.routes.workflow_execution.cache.get_node_cache",
            side_effect=RuntimeError("cache exploded with secret details"),
        ):
            r = client.get(f"/api/workflow-execution/workflows/{wf.id}/cache/stats")
        assert r.status_code == 500
        assert r.json() == {"detail": "Failed to get workflow cache stats"}


# ---------------------------------------------------------------------------
# DELETE /api/workflow-execution/workflows/{workflow_id}/cache
# ---------------------------------------------------------------------------


class TestClearWorkflowCache:
    def test_clear_cache_for_workflow(self, client, db):
        wf = _make_workflow(db)
        mock_cache = MagicMock()
        mock_cache.clear_workflow.return_value = 3
        with patch(
            "fichero_server.api.routes.workflow_execution.cache.get_node_cache",
            return_value=mock_cache,
        ):
            r = client.delete(f"/api/workflow-execution/workflows/{wf.id}/cache")
        assert r.status_code == 200
        assert r.json()["entries_deleted"] == 3


# ---------------------------------------------------------------------------
# DELETE /api/workflow-execution/cache (global)
# ---------------------------------------------------------------------------


class TestClearGlobalCache:
    def test_clear_global_cache(self, client):
        mock_cache = MagicMock()
        mock_cache.clear_all.return_value = 0
        with patch(
            "fichero_server.api.routes.workflow_execution.cache.get_node_cache",
            return_value=mock_cache,
        ):
            r = client.delete("/api/workflow-execution/cache")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/workflow-execution/cache/stats (global)
# ---------------------------------------------------------------------------


class TestGlobalCacheStats:
    def test_global_cache_stats(self, client):
        mock_cache = MagicMock()
        mock_cache.get_stats.return_value = {
            "total_entries": 0,
            "workflows_cached": 0,
            "tools_cached": 0,
            "oldest_entry": None,
            "newest_entry": None,
        }
        with patch(
            "fichero_server.api.routes.workflow_execution.cache.get_node_cache",
            return_value=mock_cache,
        ):
            r = client.get("/api/workflow-execution/cache/stats")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/workflow-execution/execute — request validation
# ---------------------------------------------------------------------------


class TestExecuteWorkflow:
    @pytest.mark.parametrize("selected_doc_id", ["folder-id", "image-id"])
    def test_execute_returns_accepted_with_thread_and_stream_url(
        self, client, db, selected_doc_id
    ):
        wf = _make_workflow(db, "Gate Workflow")
        payload = {
            "workflow_id": wf.id,
            "inputs": {"selected_doc_ids": [selected_doc_id]},
        }

        # Keep the route hermetic WITHOUT breaking the event loop. The earlier
        # version patched ``core.threading.Thread`` to a MagicMock — but
        # ``core`` does ``import threading``, so that replaced the *global*
        # ``threading.Thread``. The route ``await``s ``save_workflow_run`` (which
        # uses ``asyncio.to_thread`` → a ThreadPoolExecutor worker spawned via
        # ``threading.Thread``) BEFORE it starts its own worker thread, so the
        # broad mock starved the executor and the request deadlocked (#2650).
        #
        # Fix: spy on ``threading.Thread`` while still constructing REAL threads
        # (so ``to_thread`` keeps working), and stub the background coroutine so
        # the spawned worker exits immediately instead of running the workflow.
        import threading as _threading

        created_threads: list = []
        real_thread_cls = _threading.Thread

        def _spy_thread(*args, **kwargs):
            thread = real_thread_cls(*args, **kwargs)
            created_threads.append(thread)
            return thread

        with patch(
            "fichero_server.api.routes.workflow_execution.core.threading.Thread",
            side_effect=_spy_thread,
        ), patch(
            "fichero_server.api.routes.workflow_execution.core._run_workflow_in_background",
            new=AsyncMock(return_value=None),
        ):
            r = client.post("/api/workflow-execution/execute", json=payload)

        assert r.status_code == 202
        data = r.json()
        assert data["workflow_id"] == wf.id
        assert data["workflow_name"] == "Gate Workflow"
        assert data["status"] == "accepted"
        assert data["thread_id"].startswith("thread-")
        # The live SSE handler is stream_workflow_events on the workflow-execution
        # router; the old /api/workflows/stream/ path had no handler (#2546).
        assert data["stream_url"].endswith(
            f"/api/workflow-execution/stream/{data['thread_id']}"
        )
        run = asyncio.run(
            get_activity_tracker(str(db.path)).store.get_workflow_run(data["thread_id"])
        )
        assert run is not None
        assert run.workflow_id == wf.id
        assert run.workflow_name == "Gate Workflow"
        assert run.status == "accepted"
        assert run.workflow_snapshot["inputs"]["selected_doc_ids"] == [selected_doc_id]
        # The route must have spawned a dedicated workflow worker thread (#1000).
        assert any(
            t.name.startswith("workflow-") for t in created_threads
        ), "execute route did not start a workflow worker thread"

    def test_execute_does_not_write_stdout_debug_logs(self, client, db):
        wf = _make_workflow(db, "Quiet Workflow")
        payload = {"workflow_id": wf.id, "inputs": {}}

        import threading as _threading

        real_thread_cls = _threading.Thread

        def _spy_thread(*args, **kwargs):
            return real_thread_cls(*args, **kwargs)

        with patch("builtins.print") as print_spy, patch(
            "fichero_server.api.routes.workflow_execution.core.threading.Thread",
            side_effect=_spy_thread,
        ), patch(
            "fichero_server.api.routes.workflow_execution.core._run_workflow_in_background",
            new=AsyncMock(return_value=None),
        ):
            r = client.post("/api/workflow-execution/execute", json=payload)

        assert r.status_code == 202
        print_spy.assert_not_called()

    def test_missing_workflow_returns_404(self, client):
        payload = {
            "workflow_id": "no-such-workflow",
            "inputs": {},
        }
        with patch(
            "fichero_server.api.routes.workflow_execution.core.AsyncDuckDBCheckpointer.from_db_path",
            return_value=_make_mock_checkpointer(),
        ):
            r = client.post("/api/workflow-execution/execute", json=payload)
        assert r.status_code == 404
        assert r.json() == {"detail": "Workflow not found in this library: no-such-workflow"}

    def test_execute_rejects_empty_workflow(self, client, db, caplog):
        wf = Workflow(
            name="Empty Workflow",
            description="No nodes",
            format="nodes",
            nodes=[],
            edges=[],
            steps=[],
        )
        db.save(wf)
        payload = {"workflow_id": wf.id, "inputs": {}}

        with caplog.at_level(
            logging.WARNING, logger="fichero_server.api.routes.workflow_execution.core"
        ):
            r = client.post("/api/workflow-execution/execute", json=payload)

        assert r.status_code == 400
        assert "Workflow validation failed" in r.json()["detail"]
        assert "Workflow has no nodes" in r.json()["detail"]
        assert "Workflow validation failed" in caplog.text

    def test_execute_rejects_unknown_tool(self, client, db):
        wf = _make_workflow(db, "Bad Tool Workflow")
        wf.nodes = [{"id": "node-1", "tool": "does_not_exist"}]
        db.save(wf)

        r = client.post("/api/workflow-execution/execute", json={"workflow_id": wf.id, "inputs": {}})

        assert r.status_code == 400
        assert "Unknown tool: does_not_exist" in r.json()["detail"]

    def test_execute_rejects_type_mismatch(self, client, db):
        wf = _make_workflow(db, "Type Mismatch Workflow")
        wf.nodes = [
            {"id": "source", "tool": "files"},
            {"id": "target", "tool": "summarize"},
        ]
        wf.edges = [
            {
                "source": "source",
                "target": "target",
                "source_port": "files",
                "target_port": "text",
            }
        ]
        db.save(wf)

        r = client.post("/api/workflow-execution/execute", json={"workflow_id": wf.id, "inputs": {}})

        assert r.status_code == 400
        assert "Invalid connection from source.files to target.text" in r.json()["detail"]

    def test_execute_rejects_edge_with_missing_target_node(self, client, db):
        wf = _make_workflow(db, "Dangling Edge Workflow")
        wf.nodes = [{"id": "source", "tool": "files"}]
        wf.edges = [
            {
                "source": "source",
                "target": "missing-node",
                "source_port": "files",
                "target_port": "files",
            }
        ]
        db.save(wf)

        r = client.post("/api/workflow-execution/execute", json={"workflow_id": wf.id, "inputs": {}})

        assert r.status_code == 400
        assert "Edge references unknown target node: missing-node" in r.json()["detail"]

    def test_execute_rejects_edge_with_missing_source_node(self, client, db):
        wf = _make_workflow(db, "Dangling Source Workflow")
        wf.nodes = [{"id": "target", "tool": "summarize"}]
        wf.edges = [
            {
                "source": "missing-source",
                "target": "target",
                "source_port": "files",
                "target_port": "files",
            }
        ]
        db.save(wf)

        r = client.post("/api/workflow-execution/execute", json={"workflow_id": wf.id, "inputs": {}})

        assert r.status_code == 400
        assert "Edge references unknown source node: missing-source" in r.json()["detail"]

    def test_execute_rejects_edge_with_unknown_source_port(self, client, db):
        wf = _make_workflow(db, "Bad Source Port Workflow")
        wf.nodes = [
            {"id": "source", "tool": "files"},
            {"id": "target", "tool": "summarize"},
        ]
        wf.edges = [
            {
                "source": "source",
                "target": "target",
                "source_port": "not-a-port",
                "target_port": "files",
            }
        ]
        db.save(wf)

        r = client.post("/api/workflow-execution/execute", json={"workflow_id": wf.id, "inputs": {}})

        assert r.status_code == 400
        assert "Edge references unknown source port 'not-a-port' on node 'source'" in r.json()["detail"]


class TestWorkflowExecutionSchemas:
    def test_format_sse_does_not_write_stdout_debug_logs(self):
        event = SSEEvent(
            event="node_end",
            thread_id="thread-1",
            workflow_id="wf-1",
            data={"result": "ok"},
        )

        with patch("builtins.print") as print_spy:
            payload = format_sse(event)

        assert payload.startswith("event: node_end\n")
        print_spy.assert_not_called()

    def test_execute_rejects_subworkflow_self_cycle(self, client, db):
        wf = Workflow(
            name="Self Cycle Workflow",
            description="sub_workflow points at itself",
            format="nodes",
            nodes=[
                {
                    "id": "sub",
                    "tool": "sub_workflow",
                    "config": {"workflow_ref": "wf-self-cycle"},
                }
            ],
            edges=[],
            steps=[],
        )
        wf.id = "wf-self-cycle"
        db.save(wf)

        r = client.post("/api/workflow-execution/execute", json={"workflow_id": wf.id, "inputs": {}})

        assert r.status_code == 400
        assert "workflow reference cycle detected: wf-self-cycle -> wf-self-cycle" in r.json()["detail"]

    def test_get_status_hides_internal_exception_details(self, client):
        with patch(
            "fichero_server.api.routes.workflow_execution.core.AsyncDuckDBCheckpointer.from_db_path",
            side_effect=RuntimeError("checkpoint secret details"),
        ):
            r = client.get("/api/workflow-execution/threads/thread-secret/status")
        assert r.status_code == 500
        assert r.json() == {"detail": "Failed to get workflow status"}


class TestGetWorkflowRun:
    def test_get_workflow_run_returns_saved_execution_data(self, client, db):
        source_doc = _make_doc(db, "source.pdf")
        output_doc = _make_doc(db, "page-1.png")
        db.save(
            Artifact(
                document_id=output_doc.id,
                source_document_id=source_doc.id,
                artifact_type="transcription",
                content="hola",
                run_id="thread-123",
                step_name="n1",
            )
        )
        run = MagicMock()
        run.thread_id = "thread-123"
        run.workflow_id = "wf-123"
        run.workflow_name = "Transcribe"
        run.python_code = "print('ok')"
        run.execution_log = "completed"
        run.status = "completed"
        run.started_at = None
        run.completed_at = None
        run.duration_ms = 42.0
        run.error = None
        run.workflow_snapshot = {
            "nodes": [
                {"id": "n1", "tool": "files", "label": "Files"},
                {"id": "n2", "tool": "transcribe", "label": "Transcribe"},
            ],
            "edges": [{"source": "n1", "target": "n2"}],
        }
        run.node_name_map = {"n1": "Files"}
        run.progress_timeline = {"steps": []}
        run.diagram_mermaid = "graph TD;"

        tracker = MagicMock()
        tracker.store.get_workflow_run = AsyncMock(return_value=run)

        with patch(
            "fichero_server.api.routes.workflow_execution.threads.get_activity_tracker",
            return_value=tracker,
        ):
            r = client.get("/api/workflow-execution/threads/thread-123/run")

        assert r.status_code == 200
        data = r.json()
        assert data["thread_id"] == "thread-123"
        assert data["workflow_id"] == "wf-123"
        assert data["status"] == "completed"
        assert data["execution_log"] == "completed"
        assert data["diagram_svg_url"].endswith("/api/workflow-execution/threads/thread-123/diagram.svg")
        assert data["planned_steps"] == [
            {
                "node_id": "n1",
                "node_name": "Files",
                "tool": "files",
                "upstream_ids": [],
                "downstream_ids": ["n2"],
            },
            {
                "node_id": "n2",
                "node_name": "Transcribe",
                "tool": "transcribe",
                "upstream_ids": ["n1"],
                "downstream_ids": [],
            },
        ]
        assert data["run_artifacts"][0]["artifact_type"] == "transcription"
        assert data["run_artifacts"][0]["document_id"] == output_doc.id
        assert data["run_artifacts"][0]["document_name"] == "page-1.png"
        assert data["run_artifacts"][0]["source_document_id"] == source_doc.id
        assert data["run_artifacts"][0]["source_document_name"] == "source.pdf"
        assert data["run_artifacts"][0]["step_name"] == "n1"
        assert data["run_artifacts"][0]["node_name"] == "Files"


class TestThreadDiagramSvg:
    def test_returns_svg_wrapper_for_run_diagram(self, client):
        run = WorkflowRun(
            thread_id="thread-svg",
            workflow_id="wf-svg",
            workflow_name="Transcribe",
            python_code="",
            execution_log="",
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            duration_ms=1,
            error=None,
            workflow_snapshot={
                "nodes": [{"id": "n1", "tool": "files", "label": "Files"}],
                "edges": [],
            },
            node_name_map={"n1": "Files"},
            progress_timeline=None,
            diagram_mermaid="graph TD;",
        )
        tracker = MagicMock()
        tracker.store.get_workflow_run = AsyncMock(return_value=run)

        with (
            patch(
                "fichero_server.api.routes.workflow_execution.threads.get_activity_tracker",
                return_value=tracker,
            ),
            patch(
                "fichero_server.api.routes.workflow_execution.threads._render_run_diagram_png",
                AsyncMock(return_value=b"png-bytes"),
            ),
        ):
            r = client.get("/api/workflow-execution/threads/thread-svg/diagram.svg")

        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/svg+xml")
        assert "data:image/png;base64," in r.text


class TestWorkflowVisualizationHardening:
    def test_visualization_hides_internal_exception_details(self, client, db):
        wf = _make_workflow(db, "Visualize Me")
        with patch(
            "fichero_server.api.routes.workflow_execution.visualization.to_workflow_def",
            side_effect=RuntimeError("mermaid secret details"),
        ):
            r = client.get(f"/api/workflow-execution/workflows/{wf.id}/visualization")
        assert r.status_code == 500
        assert r.json() == {"detail": "Failed to generate workflow visualization"}


# ---------------------------------------------------------------------------
# Internal LangChain node filter — #1002
# ---------------------------------------------------------------------------


class TestIsInternalLangchainNode:
    """``_is_internal_langchain_node`` drops LCEL framework-internal
    Runnables from the SSE stream so the frontend doesn't see them.
    (#1002)"""

    def test_runnable_variants_filtered(self):
        from fichero_server.api.routes.workflow_execution.runner import (
            _is_internal_langchain_node,
        )
        for name in (
            "RunnableSequence",
            "RunnableLambda",
            "RunnableParallel<parsed,parsing_error>",
            "RunnableAssign<parsed,parsing_error>",
            "RunnableWithFallbacks",
        ):
            assert _is_internal_langchain_node(name), name

    def test_user_node_names_kept(self):
        from fichero_server.api.routes.workflow_execution.runner import (
            _is_internal_langchain_node,
        )
        # Real user-authored node names (snake_case from catalogue.json)
        for name in (
            "extract_all",
            "extract_all_process",
            "extract_all_aggregate",
            "transcribe_each_file",
            "catalogue",
            "Catalogue",  # display name
            "__start__",  # handled separately by caller, not by this fn
            "LangGraph",  # handled separately by caller
        ):
            assert not _is_internal_langchain_node(name), name


class TestClassifyProviderError:
    def test_quota(self):
        from fichero_server.api.routes.workflow_execution.runner import _classify_provider_error
        out = _classify_provider_error("Error 429: insufficient_quota")
        assert out["category"] == "quota"

    def test_auth(self):
        from fichero_server.api.routes.workflow_execution.runner import _classify_provider_error
        out = _classify_provider_error("401 Unauthorized: invalid api key")
        assert out["category"] == "auth"

    def test_model_not_found(self):
        from fichero_server.api.routes.workflow_execution.runner import _classify_provider_error
        out = _classify_provider_error("404 model_not_found")
        assert out["category"] == "model_not_found"

    def test_network(self):
        from fichero_server.api.routes.workflow_execution.runner import _classify_provider_error
        out = _classify_provider_error("connection timed out while calling provider")
        assert out["category"] == "network"

    def test_server(self):
        from fichero_server.api.routes.workflow_execution.runner import _classify_provider_error
        out = _classify_provider_error("upstream returned 500 Internal Server Error")
        assert out["category"] == "server"

    def test_402_out_of_credits_is_quota(self):
        """#2612: 402 Payment Required must be classified as a quota error."""
        from fichero_server.api.routes.workflow_execution.runner import _classify_provider_error
        out = _classify_provider_error("Provider returned 402: out of credits")
        assert out["category"] == "quota"
        assert "credits" in out["action"].lower() or "account" in out["action"].lower()


class TestSystemicFailureMessage:
    """#2612: systemic failures must surface provider/auth/quota details."""

    def test_402_message_includes_provider_detail(self):
        from fichero_server.api.routes.workflow_execution.runner import (
            _systemic_failure_message,
        )
        from fichero_server.workflows.builder import SystemicErrorDetected

        raw = "Step 'Transcribe' failed: Provider returned 402: out of credits"
        e = SystemicErrorDetected(
            message=raw,
            error_count=1,
            total_count=1,
            errors=[{"node": "transcribe", "error": raw}],
        )
        message, cls = _systemic_failure_message(e)
        assert cls["category"] == "quota"
        assert "out of credits" in message
        assert "Top up account" in message

    def test_unknown_error_passes_through_raw_message(self):
        from fichero_server.api.routes.workflow_execution.runner import (
            _systemic_failure_message,
        )
        from fichero_server.workflows.builder import SystemicErrorDetected

        raw = "Step 'X' failed: something obscure"
        e = SystemicErrorDetected(message=raw)
        message, cls = _systemic_failure_message(e)
        assert cls["category"] == "unknown"
        assert message == raw


class TestDetectEmptyTextOutput:
    """#2244/#2245: _detect_empty_text_output flags runs that processed files but
    produced no text, without false-positives on no-input or rich-output workflows."""

    def _fn(self, state):
        from fichero_server.api.routes.workflow_execution.runner import _detect_empty_text_output
        return _detect_empty_text_output(state)

    def test_no_files_not_empty(self):
        """Workflow with no input files must never be flagged."""
        is_empty, _ = self._fn({"outputs": {"node": {"text": ""}}})
        assert not is_empty

    def test_text_output_not_empty(self):
        """Non-whitespace text in any node output → not empty."""
        state = {
            "files": ["/tmp/page-1.jpg"],
            "outputs": {"transcribe": {"text": "El alcalde firmó el acta."}},
        }
        is_empty, _ = self._fn(state)
        assert not is_empty

    def test_whitespace_only_text_is_empty(self):
        """Whitespace-only text must not count as output."""
        state = {
            "files": ["/tmp/page-1.jpg"],
            "outputs": {"transcribe": {"text": "   \n  "}},
        }
        is_empty, reason = self._fn(state)
        assert is_empty
        assert "page-1.jpg" not in reason  # reason contains file count, not paths
        assert "1 file" in reason

    def test_artifacts_count_as_output(self):
        """Non-empty artifacts list means the run produced output."""
        state = {
            "files": ["/tmp/scan.pdf"],
            "outputs": {"transcribe": {"text": "", "artifacts": ["artifact-1"]}},
        }
        is_empty, _ = self._fn(state)
        assert not is_empty

    def test_page_records_count_as_output(self):
        """Non-empty page_records list means the run produced output."""
        state = {
            "files": ["/tmp/page-1.jpg"],
            "outputs": {
                "transcribe": {
                    "text": "",
                    "page_records": [{"doc_id": "doc-1", "text": "Transcribed"}],
                }
            },
        }
        is_empty, _ = self._fn(state)
        assert not is_empty

    def test_all_empty_outputs_flagged(self):
        """Multiple nodes all with empty text/no artifacts → flagged as empty."""
        state = {
            "files": ["/tmp/a.jpg", "/tmp/b.jpg"],
            "outputs": {
                "transcribe-ts": {"text": ""},
                "transcribe-ms": {"text": None},
            },
        }
        is_empty, reason = self._fn(state)
        assert is_empty
        assert "2 file" in reason

    def test_non_dict_final_state_not_empty(self):
        """Non-dict final state (shouldn't happen) must not raise."""
        is_empty, _ = self._fn(None)
        assert not is_empty

    def test_empty_outputs_dict_with_files_flagged(self):
        """Files present but empty outputs dict → flagged."""
        state = {"files": ["/tmp/x.jpg"], "outputs": {}}
        is_empty, reason = self._fn(state)
        assert is_empty
        assert "1 file" in reason

    def test_results_count_as_output(self):
        """Non-empty results list counts as output (e.g. entity extraction)."""
        state = {
            "files": ["/tmp/doc.txt"],
            "outputs": {
                "extract_all": {"text": "", "results": [{"entity": "García"}]},
            },
        }
        is_empty, _ = self._fn(state)
        assert not is_empty
