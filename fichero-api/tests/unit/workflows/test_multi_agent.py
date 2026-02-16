"""Unit tests for multi-agent workflow tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage

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
        # Mock the LLM and agent execution
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(
            content="I will delegate to researcher. Task complete."
        ))

        with patch("fichero.workflows.tools.multi_agent.get_langchain_model", return_value=mock_model):
            with patch("fichero.workflows.tools.multi_agent.create_react_agent") as mock_create:
                # Mock worker agent
                mock_worker = MagicMock()
                mock_worker.ainvoke = AsyncMock(return_value={
                    "messages": [AIMessage(content="Worker result")]
                })
                mock_create.return_value = mock_worker

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

                # Should have execution log
                assert "execution_log" in result
                assert isinstance(result["execution_log"], list)


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
        mock_model = MagicMock()

        with patch("fichero.workflows.tools.multi_agent.get_langchain_model", return_value=mock_model):
            with patch("fichero.workflows.tools.multi_agent.create_react_agent") as mock_create:
                mock_agent = MagicMock()
                mock_agent.ainvoke = AsyncMock(return_value={
                    "messages": [AIMessage(content="Final answer without handoff")]
                })
                mock_create.return_value = mock_agent

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
        mock_model = MagicMock()
        call_count = 0

        async def mock_ainvoke(state):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"messages": [AIMessage(content="HANDOFF: agent2 Continue with this")]}
            else:
                return {"messages": [AIMessage(content="Final answer from agent2")]}

        with patch("fichero.workflows.tools.multi_agent.get_langchain_model", return_value=mock_model):
            with patch("fichero.workflows.tools.multi_agent.create_react_agent") as mock_create:
                mock_agent = MagicMock()
                mock_agent.ainvoke = mock_ainvoke
                mock_create.return_value = mock_agent

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
        mock_model = MagicMock()
        mock_model.ainvoke = AsyncMock(return_value=AIMessage(
            content="Synthesized response"
        ))

        with patch("fichero.workflows.tools.multi_agent.get_langchain_model", return_value=mock_model):
            with patch("fichero.workflows.tools.multi_agent.create_react_agent") as mock_create:
                # Create mock agents with different responses
                mock_agent = MagicMock()

                async def mock_ainvoke(state):
                    return {"messages": [AIMessage(content="Agent response")]}

                mock_agent.ainvoke = mock_ainvoke
                mock_create.return_value = mock_agent

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

                # Should have results from both agents
                assert "agent_results" in result
                assert "analyzer1" in result["agent_results"]
                assert "analyzer2" in result["agent_results"]
                assert "agreement_score" in result

    @pytest.mark.asyncio
    async def test_coordinator_voting_method(self, llm_config, mock_state):
        """Test coordinator with voting combination."""
        mock_model = MagicMock()

        with patch("fichero.workflows.tools.multi_agent.get_langchain_model", return_value=mock_model):
            with patch("fichero.workflows.tools.multi_agent.create_react_agent") as mock_create:
                mock_agent = MagicMock()
                mock_agent.ainvoke = AsyncMock(return_value={
                    "messages": [AIMessage(content="Same answer")]
                })
                mock_create.return_value = mock_agent

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
        mock_model = MagicMock()

        with patch("fichero.workflows.tools.multi_agent.get_langchain_model", return_value=mock_model):
            with patch("fichero.workflows.tools.multi_agent.create_react_agent") as mock_create:
                mock_agent = MagicMock()
                mock_agent.ainvoke = AsyncMock(return_value={
                    "messages": [AIMessage(content="Weighted response")]
                })
                mock_create.return_value = mock_agent

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

                # Should include weight percentages in output
                assert "expert" in result["combined_result"]
                assert "%" in result["combined_result"]
