"""Tests for POST /threads/{thread_id}/pause endpoint."""

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_pause_not_running():
    from fichero_server.api.routes.workflow_execution.threads import pause_workflow

    with patch(
        "fichero_server.api.routes.workflow_execution.runner._get_workflow_state",
        return_value=None,
    ):
        result = await pause_workflow("thread-not-there")

    assert result.status == "not_running"
    assert result.thread_id == "thread-not-there"


@pytest.mark.asyncio
async def test_pause_already_terminal():
    from fichero_server.api.routes.workflow_execution.threads import pause_workflow

    state = {"status": "completed"}
    with patch(
        "fichero_server.api.routes.workflow_execution.runner._get_workflow_state",
        return_value=state,
    ):
        result = await pause_workflow("thread-done")

    assert result.status == "already_terminal"
    assert "completed" in result.message


@pytest.mark.asyncio
async def test_pause_running_sets_flag():
    from fichero_server.api.routes.workflow_execution.threads import pause_workflow

    state = {"status": "running"}
    with patch(
        "fichero_server.api.routes.workflow_execution.runner._get_workflow_state",
        return_value=state,
    ):
        result = await pause_workflow("thread-running")

    assert result.status == "pause_requested"
    assert state["pause_requested"] is True
