"""
Integration Tests for Agent Workflows

Tests the complete agent workflow system end-to-end:
- Agent nodes in workflows
- Error handling
- Workflow persistence

These tests use real workflow execution with mocked LLM calls.
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


from fichero.db import Database
from fichero.workflows.workflow_store import WorkflowStore
from fichero.workflows.checkpointer import AsyncDuckDBCheckpointer
from fichero.workflows.builder import SystemicErrorDetected, build_graph
from fichero.llm import LLMConfig
from fichero.models import Workflow
from fichero.workflows.types import WorkflowDef, NodeDef


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


@pytest.fixture
def llm_config():
    """Create LLM config for testing."""
    return LLMConfig(
        provider="openai",
        model="gpt-4o-mini",
        temperature=0.7,
        max_tokens=1000,
    )


# =============================================================================
# Integration Tests
# =============================================================================

class TestAgentWorkflowExecution:
    """Test agent node execution within workflows."""

    @pytest.mark.asyncio
    async def test_basic_agent_workflow(self, checkpointer, llm_config):
        """Test workflow with a single agent node - uses mocked LLM."""
        # Define workflow with agent node
        workflow_def = WorkflowDef(
            id="test_agent_workflow",
            name="Test Agent Workflow",
            description="Simple workflow with agent",
            nodes=[
                NodeDef(
                    id="agent1",
                    tool="react_agent",
                    inputs={
                        "task": "Say hello",
                        "tools": [],
                        "system_prompt": "You are helpful.",
                        "max_iterations": 5,
                    },
                ),
            ],
            edges=[],
            provider=llm_config.provider,
            model=llm_config.model,
        )

        with patch(
            "fichero.workflows.tools.agent.chat_workflow",
            AsyncMock(return_value="Hello! I'm an AI assistant here to help you."),
        ):
            # Build and compile workflow graph
            app = build_graph(workflow_def)

            # Execute with checkpointer
            thread_id = "test_thread_1"
            config = {"configurable": {"thread_id": thread_id, "checkpointer": checkpointer}}
            initial_state = {"messages": []}

            final_state = await app.ainvoke(initial_state, config=config)

            # Verify agent executed
            assert "outputs" in final_state
            assert "agent1" in final_state["outputs"]
            assert "result" in final_state["outputs"]["agent1"]
            assert len(final_state["outputs"]["agent1"]["result"]) > 0


    @pytest.mark.asyncio
    async def test_agent_workflow_error_handling(self, checkpointer, llm_config):
        """Test agent workflow error handling with empty task."""
        # Define workflow with agent
        workflow_def = WorkflowDef(
            id="test_agent_error",
            name="Agent Error Test",
            description="Test agent error handling",
            nodes=[
                NodeDef(
                    id="agent1",
                    tool="react_agent",
                    inputs={
                        "task": "",  # Empty task should cause error
                        "tools": [],
                        "system_prompt": "You are a helper.",
                        "max_iterations": 5,
                    },
                ),
            ],
            edges=[],
            provider=llm_config.provider,
            model=llm_config.model,
        )

        # Build and compile workflow graph
        app = build_graph(workflow_def)

        # Execute
        thread_id = "test_thread_error"
        config = {"configurable": {"thread_id": thread_id, "checkpointer": checkpointer}}
        initial_state = {"messages": []}

        with pytest.raises(SystemicErrorDetected, match="No task provided to agent"):
            await app.ainvoke(initial_state, config=config)


    @pytest.mark.asyncio
    async def test_agent_workflow_persistence(self, store):
        """Test saving and loading workflow with agent nodes."""
        # Define workflow
        workflow_def = Workflow(
            name="Agent Persistence Test",
            description="Test workflow persistence",
            format="nodes",
            nodes=[
                {
                    "id": "agent1",
                    "tool": "react_agent",
                    "label": "Test Agent",
                    "inputs": {
                        "task": "Test task",
                        "tools": ["transcribe"],
                        "system_prompt": "You are a tester.",
                        "max_iterations": 10,
                    },
                    "config": {},
                },
            ],
            edges=[
                {"source": "__start__", "target": "agent1"},
                {"source": "agent1", "target": "__end__"},
            ],
            provider="openai",
            model="gpt-4o-mini",
        )

        # Save workflow
        store.save(workflow_def)

        # Load workflow
        loaded = store.get(workflow_def.id)

        # Verify workflow was preserved correctly
        assert loaded is not None
        assert loaded.id == workflow_def.id
        assert loaded.name == workflow_def.name
        assert len(loaded.nodes) == 1
        assert loaded.nodes[0]["tool"] == "react_agent"
        assert loaded.nodes[0]["inputs"]["task"] == "Test task"
        assert loaded.nodes[0]["inputs"]["tools"] == ["transcribe"]
        assert loaded.nodes[0]["inputs"]["max_iterations"] == 10
