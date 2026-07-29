"""
Integration Tests for Workflow System

Tests the complete workflow system end-to-end:
- WorkflowStore (save/load workflows)
- AsyncDuckDBCheckpointer (state persistence)
- Workflow execution with LangGraph

These tests validate that all components work together correctly.
"""

import shutil
import tempfile
from pathlib import Path
from typing import TypedDict

import pytest
from langgraph.graph import StateGraph, START, END

from fichero_server.db import Database
from fichero_server.models import Workflow
from fichero_server.workflows.workflow_store import WorkflowStore
from fichero_server.workflows.checkpointer import AsyncDuckDBCheckpointer


# =============================================================================
# Test State and Workflow Functions
# =============================================================================

class SimpleState(TypedDict):
    """Simple state for test workflows."""
    messages: list[str]
    step: int
    counter: int


async def increment_step(state: SimpleState) -> SimpleState:
    """Increment step counter."""
    return {
        "messages": state["messages"] + [f"Step {state['step'] + 1}"],
        "step": state["step"] + 1,
        "counter": state.get("counter", 0) + 1,
    }


async def double_counter(state: SimpleState) -> SimpleState:
    """Double the counter."""
    return {
        "messages": state["messages"] + ["Doubled counter"],
        "counter": state.get("counter", 0) * 2,
    }


async def add_message(state: SimpleState) -> SimpleState:
    """Add a final message."""
    return {
        "messages": state["messages"] + ["Complete"],
    }


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / 'test.duckdb'
    yield db_path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def db(temp_db):
    """Create database instance."""
    return Database(temp_db)


@pytest.fixture
def store(db):
    """Create workflow store instance."""
    return WorkflowStore(db)


@pytest.fixture
def checkpointer(temp_db):
    """Create checkpointer instance."""
    return AsyncDuckDBCheckpointer.from_db_path(temp_db)


# =============================================================================
# Integration Tests
# =============================================================================

class TestWorkflowLifecycle:
    """Test complete workflow lifecycle: create → save → load → execute."""

    @pytest.mark.asyncio
    async def test_save_load_execute_workflow(self, store, checkpointer):
        """Test saving, loading, and executing a workflow."""
        # 1. Create workflow definition
        workflow = Workflow(
            name="Simple Test Workflow",
            description="A test workflow with 3 steps",
            format="nodes",
            nodes=[
                {
                    "id": "step1",
                    "tool": "increment",
                    "label": "Increment Step",
                    "inputs": {},
                    "config": {},
                },
                {
                    "id": "step2",
                    "tool": "double",
                    "label": "Double Counter",
                    "inputs": {},
                    "config": {},
                },
                {
                    "id": "step3",
                    "tool": "finish",
                    "label": "Finish",
                    "inputs": {},
                    "config": {},
                },
            ],
            edges=[
                {"source": "step1", "target": "step2"},
                {"source": "step2", "target": "step3"},
            ],
            provider="test",
            model="test-model",
        )

        # 2. Save workflow
        store.save(workflow)
        assert workflow.id is not None

        # 3. Load workflow
        loaded = store.get(workflow.id)
        assert loaded is not None
        assert loaded.name == workflow.name
        assert len(loaded.nodes) == 3
        assert len(loaded.edges) == 2

        # 4. Build and execute workflow
        graph = StateGraph(SimpleState)

        # Add nodes
        graph.add_node("step1", increment_step)
        graph.add_node("step2", double_counter)
        graph.add_node("step3", add_message)

        # Add edges
        graph.add_edge(START, "step1")
        graph.add_edge("step1", "step2")
        graph.add_edge("step2", "step3")
        graph.add_edge("step3", END)

        # Compile with checkpointer
        app = graph.compile(checkpointer=checkpointer)

        # Execute
        thread_id = "test-lifecycle-1"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state = {"messages": ["Start"], "step": 0, "counter": 1}

        final_state = await app.ainvoke(initial_state, config=config)

        # Verify execution
        assert final_state["step"] == 1
        assert final_state["counter"] == 4  # (1 + 1) * 2 = 4
        assert "Complete" in final_state["messages"]

        # Verify checkpoint saved
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        assert checkpoint_tuple is not None
        assert checkpoint_tuple.checkpoint["channel_values"]["counter"] == 4


class TestPauseResume:
    """Test workflow pause and resume functionality."""

    @pytest.mark.asyncio
    async def test_pause_and_resume_workflow(self, store, checkpointer):
        """Test pausing workflow at interrupt point and resuming."""
        # 1. Create workflow
        workflow = Workflow(
            name="Pausable Workflow",
            format="nodes",
            nodes=[
                {"id": "step1", "tool": "increment", "label": "Step 1"},
                {"id": "step2", "tool": "double", "label": "Step 2"},
                {"id": "step3", "tool": "finish", "label": "Step 3"},
            ],
            edges=[
                {"source": "step1", "target": "step2"},
                {"source": "step2", "target": "step3"},
            ],
        )
        store.save(workflow)

        # 2. Build workflow with interrupt point
        graph = StateGraph(SimpleState)
        graph.add_node("step1", increment_step)
        graph.add_node("step2", double_counter)
        graph.add_node("step3", add_message)
        graph.add_edge(START, "step1")
        graph.add_edge("step1", "step2")
        graph.add_edge("step2", "step3")
        graph.add_edge("step3", END)

        # Compile with interrupt before step2
        app = graph.compile(
            checkpointer=checkpointer,
            interrupt_before=["step2"]
        )

        # 3. Execute until interrupt point
        thread_id = "test-pause-1"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state = {"messages": ["Start"], "step": 0, "counter": 1}

        result = await app.ainvoke(initial_state, config=config)

        # Should have completed step1 but paused before step2
        assert result["step"] == 1
        assert result["counter"] == 2  # incremented from 1 to 2
        assert "Doubled counter" not in result["messages"]

        # 4. Resume from checkpoint
        final_state = await app.ainvoke(None, config=config)

        # Should now complete all steps
        assert final_state["step"] == 1  # step doesn't change in step2/step3
        assert final_state["counter"] == 4  # 2 * 2 = 4
        assert "Doubled counter" in final_state["messages"]
        assert "Complete" in final_state["messages"]


class TestCrashRecovery:
    """Test workflow recovery after simulated crash."""

    @pytest.mark.asyncio
    async def test_workflow_survives_restart(self, store, checkpointer, temp_db):
        """Test that workflow can resume after 'crash' (new app instance)."""
        # 1. Create and save workflow
        workflow = Workflow(
            name="Crash Recovery Test",
            format="nodes",
            nodes=[
                {"id": "step1", "tool": "increment"},
                {"id": "step2", "tool": "double"},
                {"id": "step3", "tool": "finish"},
            ],
            edges=[
                {"source": "step1", "target": "step2"},
                {"source": "step2", "target": "step3"},
            ],
        )
        store.save(workflow)

        # 2. Build workflow with interrupt
        graph = StateGraph(SimpleState)
        graph.add_node("step1", increment_step)
        graph.add_node("step2", double_counter)
        graph.add_node("step3", add_message)
        graph.add_edge(START, "step1")
        graph.add_edge("step1", "step2")
        graph.add_edge("step2", "step3")
        graph.add_edge("step3", END)

        app_1 = graph.compile(
            checkpointer=checkpointer,
            interrupt_before=["step2"]
        )

        # 3. Execute and pause
        thread_id = "test-crash-1"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state = {"messages": ["Start"], "step": 0, "counter": 1}

        await app_1.ainvoke(initial_state, config=config)

        # 4. Simulate crash by creating NEW app instance
        # In reality, this would be after server restart
        app_2 = graph.compile(checkpointer=checkpointer)

        # 5. Resume from checkpoint without initial state
        final_state = await app_2.ainvoke(None, config=config)

        # Should complete from checkpoint
        assert final_state["counter"] == 4
        assert "Complete" in final_state["messages"]


class TestParallelExecution:
    """Test multiple workflows executing in parallel."""

    @pytest.mark.asyncio
    async def test_parallel_workflows_isolated(self, store, checkpointer):
        """Test that parallel workflows don't interfere with each other."""
        # 1. Create workflow
        workflow = Workflow(
            name="Parallel Test",
            format="nodes",
            nodes=[
                {"id": "step1", "tool": "increment"},
                {"id": "step2", "tool": "double"},
            ],
            edges=[{"source": "step1", "target": "step2"}],
        )
        store.save(workflow)

        # 2. Build workflow
        graph = StateGraph(SimpleState)
        graph.add_node("step1", increment_step)
        graph.add_node("step2", double_counter)
        graph.add_edge(START, "step1")
        graph.add_edge("step1", "step2")
        graph.add_edge("step2", END)

        app = graph.compile(checkpointer=checkpointer)

        # 3. Execute three workflows in parallel
        thread_1 = "parallel-1"
        thread_2 = "parallel-2"
        thread_3 = "parallel-3"

        config_1 = {"configurable": {"thread_id": thread_1}}
        config_2 = {"configurable": {"thread_id": thread_2}}
        config_3 = {"configurable": {"thread_id": thread_3}}

        state_1 = {"messages": ["Thread 1"], "step": 0, "counter": 1}
        state_2 = {"messages": ["Thread 2"], "step": 0, "counter": 10}
        state_3 = {"messages": ["Thread 3"], "step": 0, "counter": 100}

        # Execute all three
        result_1 = await app.ainvoke(state_1, config=config_1)
        result_2 = await app.ainvoke(state_2, config=config_2)
        result_3 = await app.ainvoke(state_3, config=config_3)

        # Verify isolation - each should have independent counters
        assert result_1["counter"] == 4    # (1 + 1) * 2 = 4
        assert result_2["counter"] == 22   # (10 + 1) * 2 = 22
        assert result_3["counter"] == 202  # (100 + 1) * 2 = 202

        assert "Thread 1" in result_1["messages"]
        assert "Thread 2" in result_2["messages"]
        assert "Thread 3" in result_3["messages"]


class TestWorkflowImportExport:
    """Test workflow import/export with execution."""

    @pytest.mark.asyncio
    async def test_export_import_execute(self, store, checkpointer, temp_db):
        """Test exporting, importing, and executing a workflow."""
        # 1. Create and save workflow
        workflow = Workflow(
            name="Export Test Workflow",
            description="Test import/export",
            format="nodes",
            nodes=[
                {"id": "step1", "tool": "increment"},
                {"id": "step2", "tool": "double"},
            ],
            edges=[{"source": "step1", "target": "step2"}],
            tags=["test", "export"],
        )
        store.save(workflow)

        # 2. Export to JSON
        json_str = store.export_workflow(workflow.id)
        assert "Export Test Workflow" in json_str
        assert "test" in json_str
        assert "export" in json_str

        # 3. Import with new ID
        imported = store.import_workflow(json_str, new_id=True)
        assert imported.id != workflow.id
        assert imported.name == workflow.name
        assert imported.nodes == workflow.nodes
        assert imported.edges == workflow.edges

        # 4. Execute imported workflow
        graph = StateGraph(SimpleState)
        graph.add_node("step1", increment_step)
        graph.add_node("step2", double_counter)
        graph.add_edge(START, "step1")
        graph.add_edge("step1", "step2")
        graph.add_edge("step2", END)

        app = graph.compile(checkpointer=checkpointer)

        thread_id = "test-import-1"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state = {"messages": ["Imported"], "step": 0, "counter": 5}

        result = await app.ainvoke(initial_state, config=config)

        # Verify execution
        assert result["counter"] == 12  # (5 + 1) * 2 = 12
        assert "Imported" in result["messages"]


class TestCheckpointHistory:
    """Test checkpoint history and time-travel debugging."""

    @pytest.mark.asyncio
    async def test_checkpoint_history(self, store, checkpointer):
        """Test that checkpoint history is preserved."""
        # Build workflow with multiple interrupt points
        graph = StateGraph(SimpleState)
        graph.add_node("step1", increment_step)
        graph.add_node("step2", double_counter)
        graph.add_node("step3", add_message)
        graph.add_edge(START, "step1")
        graph.add_edge("step1", "step2")
        graph.add_edge("step2", "step3")
        graph.add_edge("step3", END)

        app = graph.compile(
            checkpointer=checkpointer,
            interrupt_before=["step2", "step3"]
        )

        thread_id = "test-history-1"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state = {"messages": ["Start"], "step": 0, "counter": 1}

        # Execute to first interrupt
        await app.ainvoke(initial_state, config=config)

        # Resume to second interrupt
        await app.ainvoke(None, config=config)

        # Resume to completion
        await app.ainvoke(None, config=config)

        # Get checkpoint history
        checkpoints = []
        async for checkpoint in checkpointer.alist(config):
            checkpoints.append(checkpoint)

        # Should have multiple checkpoints
        assert len(checkpoints) >= 3

        # Latest checkpoint should show completed state
        latest = checkpoints[0]
        assert "Complete" in latest.checkpoint["channel_values"].get("messages", [])


class TestErrorHandling:
    """Test error handling in workflow execution."""

    @pytest.mark.asyncio
    async def test_workflow_with_error(self, store, checkpointer):
        """Test that workflow errors are captured in checkpoints."""

        async def failing_step(state: SimpleState) -> SimpleState:
            """A step that always fails."""
            raise ValueError("Intentional test error")

        # Build workflow
        graph = StateGraph(SimpleState)
        graph.add_node("step1", increment_step)
        graph.add_node("step2", failing_step)  # This will fail
        graph.add_edge(START, "step1")
        graph.add_edge("step1", "step2")
        graph.add_edge("step2", END)

        app = graph.compile(checkpointer=checkpointer)

        thread_id = "test-error-1"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state = {"messages": ["Start"], "step": 0, "counter": 1}

        # Execute - should fail at step2
        try:
            await app.ainvoke(initial_state, config=config)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Intentional test error" in str(e)

        # Checkpoint should still exist with partial state
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        assert checkpoint_tuple is not None
        # Should have state from step1 before error
        assert checkpoint_tuple.checkpoint["channel_values"]["counter"] == 2


class TestWorkflowStoreIntegration:
    """Test WorkflowStore operations with real database."""

    def test_store_multiple_workflows(self, store):
        """Test storing and retrieving multiple workflows."""
        # Create workflows in different folders
        w1 = Workflow(
            name="Archive Workflow",
            folder_path="/archive",
            format="nodes",
            nodes=[],
            edges=[],
        )
        w2 = Workflow(
            name="Letters Workflow",
            folder_path="/letters",
            format="nodes",
            nodes=[],
            edges=[],
        )
        w3 = Workflow(
            name="Another Archive",
            folder_path="/archive",
            format="nodes",
            nodes=[],
            edges=[],
        )

        # Save all
        store.save(w1)
        store.save(w2)
        store.save(w3)

        # List all
        all_workflows = store.list_all()
        assert len(all_workflows) == 3

        # List by folder
        archive_workflows = store.list_all(folder_path="/archive")
        assert len(archive_workflows) == 2

        letters_workflows = store.list_all(folder_path="/letters")
        assert len(letters_workflows) == 1

        # Search
        results = store.search(name="Archive")
        assert len(results) == 2
