"""Tests for POST /threads/{thread_id}/cancel endpoint (#1127)."""

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Unit tests for the cancel endpoint logic (no HTTP layer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_not_running():
    """Returns not_running when thread_id has no entry in the registry."""
    from fichero_server.api.routes.workflow_execution.threads import cancel_workflow

    with patch(
        "fichero_server.api.routes.workflow_execution.threads.cancel_workflow.__wrapped__"
        if hasattr(cancel_workflow, "__wrapped__")
        else "fichero_server.api.routes.workflow_execution.runner._get_workflow_state",
        return_value=None,
    ):
        with patch(
            "fichero_server.api.routes.workflow_execution.runner._get_workflow_state",
            return_value=None,
        ):
            result = await cancel_workflow("thread-not-there")

    assert result.status == "not_running"
    assert result.thread_id == "thread-not-there"
    assert result.partial_results_preserved is True


@pytest.mark.asyncio
async def test_cancel_already_completed():
    """Returns already_terminal when workflow is done."""
    from fichero_server.api.routes.workflow_execution.threads import cancel_workflow

    state = {"status": "completed"}
    with patch(
        "fichero_server.api.routes.workflow_execution.runner._get_workflow_state",
        return_value=state,
    ):
        result = await cancel_workflow("thread-done")

    assert result.status == "already_terminal"
    assert "completed" in result.message


@pytest.mark.asyncio
async def test_cancel_already_failed():
    """Returns already_terminal when workflow failed."""
    from fichero_server.api.routes.workflow_execution.threads import cancel_workflow

    state = {"status": "failed"}
    with patch(
        "fichero_server.api.routes.workflow_execution.runner._get_workflow_state",
        return_value=state,
    ):
        result = await cancel_workflow("thread-failed")

    assert result.status == "already_terminal"
    assert "failed" in result.message


@pytest.mark.asyncio
async def test_cancel_already_cancelled():
    """Returns already_terminal when workflow was previously cancelled."""
    from fichero_server.api.routes.workflow_execution.threads import cancel_workflow

    state = {"status": "cancelled"}
    with patch(
        "fichero_server.api.routes.workflow_execution.runner._get_workflow_state",
        return_value=state,
    ):
        result = await cancel_workflow("thread-cancelled")

    assert result.status == "already_terminal"


@pytest.mark.asyncio
async def test_cancel_running_sets_flag():
    """Sets cancel_requested=True on running workflow state dict."""
    from fichero_server.api.routes.workflow_execution.threads import cancel_workflow

    state = {"status": "running"}
    with patch(
        "fichero_server.api.routes.workflow_execution.runner._get_workflow_state",
        return_value=state,
    ):
        result = await cancel_workflow("thread-running")

    assert result.status == "cancel_requested"
    assert state["cancel_requested"] is True
    assert result.thread_id == "thread-running"
    assert result.partial_results_preserved is True


@pytest.mark.asyncio
async def test_cancel_idempotent_second_call():
    """Calling cancel twice on a still-running thread is safe."""
    from fichero_server.api.routes.workflow_execution.threads import cancel_workflow

    state = {"status": "running", "cancel_requested": True}
    with patch(
        "fichero_server.api.routes.workflow_execution.runner._get_workflow_state",
        return_value=state,
    ):
        result = await cancel_workflow("thread-running")

    # Still cancel_requested — flag was already set, no error
    assert result.status == "cancel_requested"
    assert state["cancel_requested"] is True


# ---------------------------------------------------------------------------
# Sanity check: CancelResponse model
# ---------------------------------------------------------------------------


def test_cancel_response_defaults():
    from fichero_server.api.routes.workflow_execution.threads import CancelResponse

    r = CancelResponse(thread_id="t", status="cancel_requested")
    assert r.partial_results_preserved is True
    assert r.message == ""
