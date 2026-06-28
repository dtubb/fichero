"""Unit tests for multi-agent workflow tools."""

import pytest
from unittest.mock import AsyncMock, patch

from fichero.workflows.tools.multi_agent import (
    supervisor_agent,
    swarm_agent,
    agent_coordinator,
    MultiAgentState,
)
from fichero.llm import LLMConfig


class TestMultiAgentState:
    """Tests for MultiAgentState helper."""

    def test_create_default_state(self):
        """Test creating default multi-agent state."""
        state = MultiAgentState.create(task="Test task")
        assert state["task"] == "Test task"
        assert state["context"] == {}
        assert state["agent_outputs"] == {}
        assert state["current_agent"] == ""
        assert state["agent_history"] == []
        assert state["iteration"] == 0

    def test_create_state_with_context(self):
        """Test creating state with context."""
        state = MultiAgentState.create(
            task="Test task",
            context={"key": "value"},
            current_agent="agent1",
        )
        assert state["context"]["key"] == "value"
        assert state["current_agent"] == "agent1"


class TestSupervisorAgent:
    """Tests for supervisor_agent tool."""

    @pytest.fixture
    def llm_config(self):
        return LLMConfig(provider="openai", model="gpt-4o")

    @pytest.fixture
    def mock_state(self):
        return {
            "task_id": "test-123",
            "workflow_id": "wf-1",
            "inputs": {},
            "outputs": {},
            "current_node": "",
            "completed_nodes": [],
            "error": None,
            "input_files": [],
            "output_files": [],
        }

    @pytest.mark.asyncio
    async def test_supervisor_no_task(self, llm_config, mock_state):
        """Test supervisor with no task."""
        result = await supervisor_agent(
            inputs={},
            state=mock_state,
            llm_config=llm_config,
        )
        assert result["error"] == "No task provided"
        assert result["result"] == ""

    @pytest.mark.asyncio
    async def test_supervisor_no_workers(self, llm_config, mock_state):
        """Test supervisor with no workers configured."""
        result = await supervisor_agent(
            inputs={"task": "Test task", "workers": []},
            state=mock_state,
            llm_config=llm_config,
        )
        assert result["error"] == "No workers configured"

    @pytest.mark.asyncio
    async def test_supervisor_with_workers(self, llm_config, mock_state):
        """Test supervisor with workers (mocked)."""
        with patch(
            "fichero.workflows.tools.multi_agent.chat_workflow",
            new=AsyncMock(
                side_effect=[
                    "I will delegate to researcher.",
                    "Task complete.",
                    "Final synthesized result.",
                ]
            ),
        ) as mock_chat:
            with patch(
                "fichero.workflows.tools.multi_agent._run_agent_loop",
                new=AsyncMock(return_value=("Worker result", [{"role": "ai", "content": "Worker result"}], [], 0)),
            ):
                result = await supervisor_agent(
                    inputs={
                        "task": "Research AI trends",
                        "workers": [
                            {"name": "researcher", "description": "Research agent", "tools": []},
                            {"name": "writer", "description": "Writing agent", "tools": []},
                        ],
                        "max_iterations": 2,
                    },
                    state=mock_state,
                    llm_config=llm_config,
                )

        assert "execution_log" in result
        assert isinstance(result["execution_log"], list)
        assert result["result"] == "Final synthesized result."
        assert mock_chat.await_count == 3


class TestSwarmAgent:
    """Tests for swarm_agent tool."""

    @pytest.fixture
    def llm_config(self):
        return LLMConfig(provider="openai", model="gpt-4o")

    @pytest.fixture
    def mock_state(self):
        return {
            "task_id": "test-123",
            "workflow_id": "wf-1",
            "inputs": {},
            "outputs": {},
            "current_node": "",
            "completed_nodes": [],
            "error": None,
            "input_files": [],
            "output_files": [],
        }

    @pytest.mark.asyncio
    async def test_swarm_no_task(self, llm_config, mock_state):
        """Test swarm with no task."""
        result = await swarm_agent(
            inputs={},
            state=mock_state,
            llm_config=llm_config,
        )
        assert result["error"] == "No task provided"

    @pytest.mark.asyncio
    async def test_swarm_no_agents(self, llm_config, mock_state):
        """Test swarm with no agents."""
        result = await swarm_agent(
            inputs={"task": "Test", "agents": []},
            state=mock_state,
            llm_config=llm_config,
        )
        assert result["error"] == "No agents configured"

    @pytest.mark.asyncio
    async def test_swarm_single_agent_no_handoff(self, llm_config, mock_state):
        """Test swarm with single agent that doesn't hand off."""
        with patch(
            "fichero.workflows.tools.multi_agent._run_agent_loop",
            new=AsyncMock(return_value=("Final answer without handoff", [], [], 0)),
        ):
            result = await swarm_agent(
                inputs={
                    "task": "Simple task",
                    "agents": [
                        {"name": "agent1", "description": "First agent"},
                    ],
                },
                state=mock_state,
                llm_config=llm_config,
            )

        assert result["result"] == "Final answer without handoff"
        assert len(result["handoff_chain"]) == 1
        assert result["handoff_chain"][0]["agent"] == "agent1"

    @pytest.mark.asyncio
    async def test_swarm_with_handoff(self, llm_config, mock_state):
        """Test swarm with handoff between agents."""
        with patch(
            "fichero.workflows.tools.multi_agent._run_agent_loop",
            new=AsyncMock(
                side_effect=[
                    ("HANDOFF: agent2 Continue with this", [], [], 0),
                    ("Final answer from agent2", [], [], 0),
                ]
            ),
        ):
            result = await swarm_agent(
                inputs={
                    "task": "Complex task",
                    "agents": [
                        {"name": "agent1", "description": "First agent", "can_handoff_to": ["agent2"]},
                        {"name": "agent2", "description": "Second agent"},
                    ],
                    "entry_agent": "agent1",
                },
                state=mock_state,
                llm_config=llm_config,
            )

        assert result["result"] == "Final answer from agent2"
        assert len(result["handoff_chain"]) == 2


class TestAgentCoordinator:
    """Tests for agent_coordinator tool."""

    @pytest.fixture
    def llm_config(self):
        return LLMConfig(provider="openai", model="gpt-4o")

    @pytest.fixture
    def mock_state(self):
        return {
            "task_id": "test-123",
            "workflow_id": "wf-1",
            "inputs": {},
            "outputs": {},
            "current_node": "",
            "completed_nodes": [],
            "error": None,
            "input_files": [],
            "output_files": [],
        }

    @pytest.mark.asyncio
    async def test_coordinator_no_task(self, llm_config, mock_state):
        """Test coordinator with no task."""
        result = await agent_coordinator(
            inputs={},
            state=mock_state,
            llm_config=llm_config,
        )
        assert result["error"] == "No task provided"

    @pytest.mark.asyncio
    async def test_coordinator_no_agents(self, llm_config, mock_state):
        """Test coordinator with no agents."""
        result = await agent_coordinator(
            inputs={"task": "Test", "agents": []},
            state=mock_state,
            llm_config=llm_config,
        )
        assert result["error"] == "No agents configured"

    @pytest.mark.asyncio
    async def test_coordinator_parallel_execution(self, llm_config, mock_state):
        """Test coordinator runs agents in parallel."""
        with patch(
            "fichero.workflows.tools.multi_agent._run_agent_loop",
            new=AsyncMock(return_value=("Agent response", [], [], 0)),
        ):
            with patch(
                "fichero.workflows.tools.multi_agent.chat_workflow",
                new=AsyncMock(return_value="Synthesized response"),
            ):
                result = await agent_coordinator(
                    inputs={
                        "task": "Analyze document",
                        "agents": [
                            {"name": "analyzer1", "system_prompt": "You are analyzer 1"},
                            {"name": "analyzer2", "system_prompt": "You are analyzer 2"},
                        ],
                        "combination_method": "synthesis",
                    },
                    state=mock_state,
                    llm_config=llm_config,
                )

        assert "agent_results" in result
        assert "analyzer1" in result["agent_results"]
        assert "analyzer2" in result["agent_results"]
        assert "agreement_score" in result

    @pytest.mark.asyncio
    async def test_coordinator_voting_method(self, llm_config, mock_state):
        """Test coordinator with voting combination."""
        with patch(
            "fichero.workflows.tools.multi_agent._run_agent_loop",
            new=AsyncMock(return_value=("Same answer", [], [], 0)),
        ):
            result = await agent_coordinator(
                inputs={
                    "task": "Simple question",
                    "agents": [
                        {"name": "voter1"},
                        {"name": "voter2"},
                    ],
                    "combination_method": "voting",
                },
                state=mock_state,
                llm_config=llm_config,
            )

        assert result["combined_result"] == "Same answer"

    @pytest.mark.asyncio
    async def test_coordinator_weighted_average(self, llm_config, mock_state):
        """Test coordinator with weighted average."""
        with patch(
            "fichero.workflows.tools.multi_agent._run_agent_loop",
            new=AsyncMock(return_value=("Weighted response", [], [], 0)),
        ):
            result = await agent_coordinator(
                inputs={
                    "task": "Expert question",
                    "agents": [
                        {"name": "expert", "weight": 3.0},
                        {"name": "novice", "weight": 1.0},
                    ],
                    "combination_method": "weighted_average",
                },
                state=mock_state,
                llm_config=llm_config,
            )

        assert "expert" in result["combined_result"]
        assert "%" in result["combined_result"]
