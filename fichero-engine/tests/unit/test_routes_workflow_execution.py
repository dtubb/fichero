"""Tests for workflow execution routes.

Workflow execution uses LangGraph checkpointing for durable pause/resume.
These tests verify route contract (status codes, request schema) and use
mocking for LangGraph-dependent paths.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langgraph.types import Send

from fichero.api.routes.workflow_execution.core import get_thread_status
from fichero.models import Workflow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workflow(db, name: str = "Test Workflow") -> Workflow:
    wf = Workflow(
        name=name,
        description="A test workflow",
        format="nodes",
        steps=[],
    )
    db.save(wf)
    return wf


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


class TestListThreads:
    def test_returns_empty_when_no_threads(self, client):
        mock_cp = _make_mock_checkpointer()
        with patch(
            "fichero.api.routes.workflow_execution.threads.AsyncDuckDBCheckpointer.from_db_path",
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
            "fichero.api.routes.workflow_execution.core.AsyncDuckDBCheckpointer.from_db_path",
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
            "fichero.api.routes.workflow_execution.core.AsyncDuckDBCheckpointer.from_db_path",
            return_value=mock_cp,
        ):
            response = await get_thread_status("thread-1", db=db)

        # Pydantic JSON serialization is the failure mode from the live CLI.
        payload = response.model_dump_json()
        assert "Transcribe each file_process" in payload


# ---------------------------------------------------------------------------
# DELETE /api/workflow-execution/threads/{thread_id}
# ---------------------------------------------------------------------------


class TestDeleteThread:
    def test_delete_missing_thread_returns_404(self, client):
        mock_cp = _make_mock_checkpointer()
        mock_cp.aget_tuple = AsyncMock(return_value=None)
        with patch(
            "fichero.api.routes.workflow_execution.threads.AsyncDuckDBCheckpointer.from_db_path",
            return_value=mock_cp,
        ):
            r = client.delete("/api/workflow-execution/threads/nonexistent")
        assert r.status_code == 404


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
            "fichero.api.routes.workflow_execution.cache.get_node_cache",
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
            "fichero.api.routes.workflow_execution.cache.get_node_cache",
            return_value=mock_cache,
        ):
            r = client.get(f"/api/workflow-execution/workflows/{wf.id}/cache/stats")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# DELETE /api/workflow-execution/workflows/{workflow_id}/cache
# ---------------------------------------------------------------------------


class TestClearWorkflowCache:
    def test_clear_cache_for_workflow(self, client, db):
        wf = _make_workflow(db)
        mock_cache = MagicMock()
        mock_cache.clear_workflow.return_value = 3
        with patch(
            "fichero.api.routes.workflow_execution.cache.get_node_cache",
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
            "fichero.api.routes.workflow_execution.cache.get_node_cache",
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
            "fichero.api.routes.workflow_execution.cache.get_node_cache",
            return_value=mock_cache,
        ):
            r = client.get("/api/workflow-execution/cache/stats")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/workflow-execution/execute — request validation
# ---------------------------------------------------------------------------


class TestExecuteWorkflow:
    def test_missing_workflow_returns_404(self, client):
        payload = {
            "workflow_id": "no-such-workflow",
            "inputs": {},
        }
        with patch(
            "fichero.api.routes.workflow_execution.core.AsyncDuckDBCheckpointer.from_db_path",
            return_value=_make_mock_checkpointer(),
        ):
            r = client.post("/api/workflow-execution/execute", json=payload)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Internal LangChain node filter — #1002
# ---------------------------------------------------------------------------


class TestIsInternalLangchainNode:
    """``_is_internal_langchain_node`` drops LCEL framework-internal
    Runnables from the SSE stream so the frontend doesn't see them.
    (#1002)"""

    def test_runnable_variants_filtered(self):
        from fichero.api.routes.workflow_execution.runner import (
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
        from fichero.api.routes.workflow_execution.runner import (
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
