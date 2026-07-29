"""
Integration test for DuckDB Checkpointer with LangGraph.

Demonstrates pause/resume functionality with a real workflow.
"""

import shutil
import tempfile
from pathlib import Path
from typing import TypedDict

import pytest
from langgraph.graph import StateGraph, END

from fichero_server.workflows.checkpointer import AsyncDuckDBCheckpointer


class WorkflowState(TypedDict):
    """Simple workflow state for testing."""
    messages: list[str]
    step: int


async def step_1(state: WorkflowState) -> WorkflowState:
    """First step in workflow."""
    return {
        "messages": state["messages"] + ["Step 1 completed"],
        "step": 1,
    }


async def step_2(state: WorkflowState) -> WorkflowState:
    """Second step in workflow."""
    return {
        "messages": state["messages"] + ["Step 2 completed"],
        "step": 2,
    }


async def step_3(state: WorkflowState) -> WorkflowState:
    """Third step in workflow."""
    return {
        "messages": state["messages"] + ["Step 3 completed"],
        "step": 3,
    }


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / 'test.duckdb'
    yield db_path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def workflow_graph():
    """Create a simple 3-step workflow."""
    workflow = StateGraph(WorkflowState)

    # Add nodes
    workflow.add_node("step_1", step_1)
    workflow.add_node("step_2", step_2)
    workflow.add_node("step_3", step_3)

    # Add edges
    workflow.set_entry_point("step_1")
    workflow.add_edge("step_1", "step_2")
    workflow.add_edge("step_2", "step_3")
    workflow.add_edge("step_3", END)

    return workflow


@pytest.mark.asyncio
async def test_workflow_without_checkpointing(workflow_graph):
    """Test baseline: workflow runs without checkpointing."""
    app = workflow_graph.compile()

    initial_state = {"messages": ["Starting"], "step": 0}

    # Run workflow
    final_state = await app.ainvoke(initial_state)

    # Verify all steps completed
    assert final_state["step"] == 3
    assert len(final_state["messages"]) == 4
    assert "Step 1 completed" in final_state["messages"]
    assert "Step 2 completed" in final_state["messages"]
    assert "Step 3 completed" in final_state["messages"]


@pytest.mark.asyncio
async def test_workflow_with_checkpointing_full_run(temp_db, workflow_graph):
    """Test workflow runs successfully with checkpointing enabled."""
    checkpointer = AsyncDuckDBCheckpointer.from_db_path(temp_db)
    app = workflow_graph.compile(checkpointer=checkpointer)

    thread_id = "test-workflow-1"
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {"messages": ["Starting"], "step": 0}

    # Run workflow to completion
    final_state = await app.ainvoke(initial_state, config=config)

    # Verify all steps completed
    assert final_state["step"] == 3
    assert len(final_state["messages"]) == 4

    # Verify checkpoint was saved
    checkpoint = await checkpointer.aget_tuple(config)
    assert checkpoint is not None
    assert checkpoint.checkpoint["channel_values"]["step"] == 3


@pytest.mark.asyncio
async def test_workflow_pause_and_resume(temp_db, workflow_graph):
    """
    Test workflow can be paused mid-execution and resumed.

    This is the core value of checkpointing: durable execution.
    """
    checkpointer = AsyncDuckDBCheckpointer.from_db_path(temp_db)
    app = workflow_graph.compile(checkpointer=checkpointer, interrupt_before=["step_2"])

    thread_id = "test-workflow-2"
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {"messages": ["Starting"], "step": 0}

    # Run until interrupt point (before step_2)
    result = await app.ainvoke(initial_state, config=config)

    # Should have completed step_1 but stopped before step_2
    assert result["step"] == 1
    assert "Step 1 completed" in result["messages"]
    assert "Step 2 completed" not in result["messages"]

    # Verify checkpoint exists
    checkpoint = await checkpointer.aget_tuple(config)
    assert checkpoint is not None
    assert checkpoint.checkpoint["channel_values"]["step"] == 1

    # Resume workflow from checkpoint (pass None to continue)
    final_state = await app.ainvoke(None, config=config)

    # Should now complete all remaining steps
    assert final_state["step"] == 3
    assert "Step 1 completed" in final_state["messages"]
    assert "Step 2 completed" in final_state["messages"]
    assert "Step 3 completed" in final_state["messages"]

    # Verify final checkpoint
    final_checkpoint = await checkpointer.aget_tuple(config)
    assert final_checkpoint.checkpoint["channel_values"]["step"] == 3


@pytest.mark.asyncio
async def test_multiple_threads_isolated(temp_db, workflow_graph):
    """
    Test that multiple workflow executions are isolated by thread.

    This demonstrates parallel execution with separate state.
    """
    checkpointer = AsyncDuckDBCheckpointer.from_db_path(temp_db)
    app = workflow_graph.compile(checkpointer=checkpointer)

    # Start two workflows in parallel
    thread_1_config = {"configurable": {"thread_id": "workflow-1"}}
    thread_2_config = {"configurable": {"thread_id": "workflow-2"}}

    state_1 = {"messages": ["Workflow 1 starting"], "step": 0}
    state_2 = {"messages": ["Workflow 2 starting"], "step": 0}

    # Run both workflows
    result_1 = await app.ainvoke(state_1, config=thread_1_config)
    result_2 = await app.ainvoke(state_2, config=thread_2_config)

    # Both should complete independently
    assert result_1["step"] == 3
    assert result_2["step"] == 3

    # Verify separate checkpoints
    checkpoint_1 = await checkpointer.aget_tuple(thread_1_config)
    checkpoint_2 = await checkpointer.aget_tuple(thread_2_config)

    assert checkpoint_1.checkpoint["channel_values"]["messages"][0] == "Workflow 1 starting"
    assert checkpoint_2.checkpoint["channel_values"]["messages"][0] == "Workflow 2 starting"


@pytest.mark.asyncio
async def test_checkpoint_history(temp_db, workflow_graph):
    """
    Test that checkpoint history is preserved.

    Demonstrates time-travel debugging capability.
    """
    checkpointer = AsyncDuckDBCheckpointer.from_db_path(temp_db)
    app = workflow_graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["step_2", "step_3"]
    )

    thread_id = "test-workflow-3"
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {"messages": ["Starting"], "step": 0}

    # Run to first interrupt (before step_2)
    await app.ainvoke(initial_state, config=config)

    # Resume to second interrupt (before step_3)
    await app.ainvoke(None, config=config)

    # Resume to completion
    await app.ainvoke(None, config=config)

    # Get checkpoint history
    checkpoints = []
    async for checkpoint in checkpointer.alist(config):
        checkpoints.append(checkpoint)

    # Should have multiple checkpoints showing progression
    assert len(checkpoints) >= 3

    # Checkpoints should show increasing step numbers (in reverse order)
    # Note: Some checkpoints might not have 'step' in channel_values yet
    steps = [
        cp.checkpoint["channel_values"].get("step", 0)
        for cp in checkpoints
        if "step" in cp.checkpoint["channel_values"]
    ]
    # Latest checkpoint should be step 3
    assert len(steps) > 0
    assert steps[0] == 3


@pytest.mark.asyncio
async def test_workflow_recovery_after_failure(temp_db, workflow_graph):
    """
    Simulate recovery from failure using checkpoints.

    This is the killer feature: workflows survive crashes.
    """
    checkpointer = AsyncDuckDBCheckpointer.from_db_path(temp_db)

    # First execution: run until step_2
    app_1 = workflow_graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["step_2"]
    )

    thread_id = "test-recovery"
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {"messages": ["Starting"], "step": 0}

    # Run first part
    await app_1.ainvoke(initial_state, config=config)

    # Simulate crash/restart by creating new app instance
    # (In reality this could be after server restart, etc.)
    app_2 = workflow_graph.compile(checkpointer=checkpointer)

    # Resume from checkpoint without passing initial state
    final_state = await app_2.ainvoke(None, config=config)

    # Should complete successfully from checkpoint
    assert final_state["step"] == 3
    assert "Step 1 completed" in final_state["messages"]
    assert "Step 2 completed" in final_state["messages"]
    assert "Step 3 completed" in final_state["messages"]
