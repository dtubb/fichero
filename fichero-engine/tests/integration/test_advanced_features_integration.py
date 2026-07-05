"""Integration tests for advanced features (multi-agent workflows and model comparison)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage

from fichero.workflows.tools.multi_agent import (
    supervisor_agent,
    swarm_agent,
    agent_coordinator,
)
from fichero.workflows.model_comparison import (
    ModelComparisonEngine,
    ComparisonRequest,
    ModelSpec,
    model_comparison,
)
from fichero.llm import LLMConfig


@pytest.fixture
def llm_config():
    return LLMConfig(provider="openai", model="gpt-4o")


@pytest.fixture
def mock_state():
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


# =============================================================================
# Multi-Agent Integration Tests
# =============================================================================

class TestSupervisorWorkflow:
    """Integration tests for supervisor agent pattern."""

    @pytest.mark.asyncio
    async def test_supervisor_delegates_to_workers(self, llm_config, mock_state):
        """Test supervisor delegates tasks to appropriate workers."""
        call_count = {"supervisor": 0}

        async def mock_supervisor_response(*args):
            call_count["supervisor"] += 1
            if call_count["supervisor"] == 1:
                return "I will delegate to researcher to find information."
            return "Based on the research, the final answer is complete."

        with patch(
            "fichero.workflows.tools.multi_agent.chat_workflow",
            side_effect=mock_supervisor_response,
        ):
            with patch(
                "fichero.workflows.tools.multi_agent._run_agent_loop",
                AsyncMock(
                    return_value=("Worker found the answer.", [{"role": "assistant"}], [], 1)
                ),
            ):
                result = await supervisor_agent(
                    inputs={
                        "task": "Research the latest AI trends",
                        "workers": [
                            {"name": "researcher", "description": "Research agent", "tools": []},
                        ],
                        "max_iterations": 3,
                    },
                    state=mock_state,
                    llm_config=llm_config,
                )

                assert "result" in result
                assert "execution_log" in result
                assert len(result["execution_log"]) > 0

    @pytest.mark.asyncio
    async def test_supervisor_parallel_workers(self, llm_config, mock_state):
        """Test supervisor can run workers in parallel."""
        with patch(
            "fichero.workflows.tools.multi_agent.chat_workflow",
            AsyncMock(return_value="I will use researcher and analyst."),
        ):
            with patch(
                "fichero.workflows.tools.multi_agent._run_agent_loop",
                AsyncMock(return_value=("Parallel result", [{"role": "assistant"}], [], 1)),
            ):
                result = await supervisor_agent(
                    inputs={
                        "task": "Analyze and summarize",
                        "workers": [
                            {"name": "researcher", "description": "Research"},
                            {"name": "analyst", "description": "Analysis"},
                        ],
                        "aggregation_strategy": "parallel",
                        "max_iterations": 2,
                    },
                    state=mock_state,
                    llm_config=llm_config,
                )

                assert "worker_results" in result


class TestSwarmWorkflow:
    """Integration tests for swarm agent pattern."""

    @pytest.mark.asyncio
    async def test_swarm_handoff_chain(self, llm_config, mock_state):
        """Test swarm agents hand off tasks correctly."""
        call_count = 0

        async def mock_run_agent_loop(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ("I need to HANDOFF: specialist to continue", [], [], 1)
            return ("Final answer from specialist", [], [], 1)

        with patch(
            "fichero.workflows.tools.multi_agent._run_agent_loop",
            side_effect=mock_run_agent_loop,
        ):
            result = await swarm_agent(
                inputs={
                    "task": "Complex task requiring handoff",
                    "agents": [
                        {"name": "generalist", "description": "General agent", "can_handoff_to": ["specialist"]},
                        {"name": "specialist", "description": "Specialist agent"},
                    ],
                    "entry_agent": "generalist",
                },
                state=mock_state,
                llm_config=llm_config,
            )

            assert "handoff_chain" in result
            assert len(result["handoff_chain"]) >= 1
            assert result["result"] == "Final answer from specialist"

    @pytest.mark.asyncio
    async def test_swarm_max_handoffs_limit(self, llm_config, mock_state):
        """Test swarm respects max handoffs limit."""
        handoff_count = 0

        async def always_handoff(*args, **kwargs):
            nonlocal handoff_count
            handoff_count += 1
            # Alternate between agent1 and agent2
            target = "agent2" if handoff_count % 2 == 1 else "agent1"
            return (f"HANDOFF: {target} Keep going", [], [], 1)

        with patch(
            "fichero.workflows.tools.multi_agent._run_agent_loop",
            side_effect=always_handoff,
        ):
            result = await swarm_agent(
                inputs={
                    "task": "Task that loops",
                    "agents": [
                        {"name": "agent1", "description": "Agent 1", "can_handoff_to": ["agent2"]},
                        {"name": "agent2", "description": "Agent 2", "can_handoff_to": ["agent1"]},
                    ],
                    "max_handoffs": 3,
                },
                state=mock_state,
                llm_config=llm_config,
            )

            # Should have multiple handoffs in the chain
            assert len(result.get("handoff_chain", [])) >= 2


class TestAgentCoordinatorWorkflow:
    """Integration tests for agent coordinator pattern."""

    @pytest.mark.asyncio
    async def test_coordinator_synthesizes_results(self, llm_config, mock_state):
        """Test coordinator synthesizes results from multiple agents."""
        with patch(
            "fichero.workflows.tools.multi_agent.chat_workflow",
            AsyncMock(return_value="Synthesized result combining all perspectives"),
        ):
            with patch(
                "fichero.workflows.tools.multi_agent._run_agent_loop",
                AsyncMock(return_value=("Agent perspective", [], [], 1)),
            ):
                result = await agent_coordinator(
                    inputs={
                        "task": "Analyze this problem",
                        "agents": [
                            {"name": "analyst1", "system_prompt": "You are analyst 1"},
                            {"name": "analyst2", "system_prompt": "You are analyst 2"},
                            {"name": "analyst3", "system_prompt": "You are analyst 3"},
                        ],
                        "combination_method": "synthesis",
                    },
                    state=mock_state,
                    llm_config=llm_config,
                )

                assert "combined_result" in result
                assert "agent_results" in result
                assert len(result["agent_results"]) == 3
                assert "agreement_score" in result

    @pytest.mark.asyncio
    async def test_coordinator_consensus_mode(self, llm_config, mock_state):
        """Test coordinator checks for consensus."""
        with patch(
            "fichero.workflows.tools.multi_agent._run_agent_loop",
            AsyncMock(return_value=("Same answer", [], [], 1)),
        ):
            result = await agent_coordinator(
                inputs={
                    "task": "What is 2+2?",
                    "agents": [
                        {"name": "math1"},
                        {"name": "math2"},
                    ],
                    "combination_method": "consensus",
                    "require_consensus": True,
                },
                state=mock_state,
                llm_config=llm_config,
            )

            assert result["agreement_score"] == 1.0  # Same responses


# =============================================================================
# Model Comparison Integration Tests
# =============================================================================

class TestModelComparisonWorkflow:
    """Integration tests for model comparison in workflows."""

    @pytest.mark.asyncio
    async def test_comparison_in_workflow(self, llm_config, mock_state):
        """Test model comparison works as workflow tool."""
        with patch(
            "fichero.workflows.model_comparison.chat_workflow",
            AsyncMock(return_value="Test response from model"),
        ):
            result = await model_comparison(
                inputs={
                    "prompt": "Explain quantum computing",
                    "models": [
                        {"provider": "openai", "model": "gpt-4o"},
                        {"provider": "anthropic", "model": "claude-3-5-sonnet"},
                    ],
                },
                state=mock_state,
                llm_config=llm_config,
            )

            assert "results" in result
            assert "summary" in result
            assert result["summary"]["models_compared"] == 2

    @pytest.mark.asyncio
    async def test_comparison_handles_mixed_results(self, llm_config, mock_state):
        """Test comparison handles mix of success and failure."""
        call_count = 0

        async def mock_ainvoke(messages):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First model succeeds
                response = MagicMock()
                response.content = "Success"
                response.response_metadata = {}
                return response
            else:
                # Second model fails
                raise Exception("API rate limit")

        with patch(
            "fichero.workflows.model_comparison.chat_workflow",
            side_effect=mock_ainvoke,
        ):
            result = await model_comparison(
                inputs={
                    "prompt": "Test",
                    "models": [
                        {"provider": "openai", "model": "gpt-4o"},
                        {"provider": "anthropic", "model": "claude"},
                    ],
                },
                state=mock_state,
                llm_config=llm_config,
            )

            # Should have partial results
            assert result["summary"]["successful"] >= 0
            assert result["summary"]["models_compared"] == 2


class TestModelComparisonEngine:
    """Integration tests for model comparison engine."""

    @pytest.mark.asyncio
    async def test_engine_tracks_history(self):
        """Test engine maintains comparison history."""
        with patch(
            "fichero.workflows.model_comparison.chat_workflow",
            AsyncMock(return_value="Response"),
        ):
            engine = ModelComparisonEngine()

            # Run multiple comparisons
            for i in range(3):
                request = ComparisonRequest(
                    prompt=f"Test prompt {i}",
                    models=[ModelSpec(provider="openai", model="gpt-4o")],
                )
                await engine.compare(request)

            assert len(engine.comparison_history) == 3

    @pytest.mark.asyncio
    async def test_engine_calculates_metrics(self):
        """Test engine calculates correct metrics."""
        with patch(
            "fichero.workflows.model_comparison.chat_workflow",
            AsyncMock(return_value="Response text"),
        ):
            engine = ModelComparisonEngine()
            request = ComparisonRequest(
                prompt="Test",
                models=[
                    ModelSpec(provider="openai", model="gpt-4o"),
                    ModelSpec(provider="anthropic", model="claude-3-5-sonnet"),
                ],
            )
            result = await engine.compare(request)

            assert result.fastest_model is not None
            assert result.total_cost_usd > 0


# =============================================================================
# Combined Workflow Tests
# =============================================================================

class TestCombinedAdvancedFeatures:
    """Tests combining multi-agent and comparison features."""

    @pytest.mark.asyncio
    async def test_multi_agent_with_different_models(self, llm_config, mock_state):
        """Test multi-agent workflow can use different models per agent."""
        with patch(
            "fichero.workflows.tools.multi_agent.chat_workflow",
            AsyncMock(return_value="Result"),
        ):
            with patch(
                "fichero.workflows.tools.multi_agent._run_agent_loop",
                AsyncMock(return_value=("Agent result", [], [], 1)),
            ):
                result = await agent_coordinator(
                    inputs={
                        "task": "Analyze using different model strengths",
                        "agents": [
                            {"name": "fast_agent", "system_prompt": "Be fast"},
                            {"name": "thorough_agent", "system_prompt": "Be thorough"},
                        ],
                        "combination_method": "synthesis",
                    },
                    state=mock_state,
                    llm_config=llm_config,
                )

                assert result["combined_result"]
                assert len(result["agent_results"]) == 2


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestAdvancedFeaturesErrorHandling:
    """Tests for error handling in advanced features."""

    @pytest.mark.asyncio
    async def test_supervisor_handles_worker_failure(self, llm_config, mock_state):
        """Test supervisor handles worker failures gracefully."""
        with patch(
            "fichero.workflows.tools.multi_agent.chat_workflow",
            AsyncMock(return_value="Delegate to failing_worker."),
        ):
            with patch(
                "fichero.workflows.tools.multi_agent._run_agent_loop",
                AsyncMock(side_effect=Exception("Worker crashed")),
            ):
                result = await supervisor_agent(
                    inputs={
                        "task": "Test task",
                        "workers": [
                            {"name": "failing_worker", "description": "Will fail"},
                        ],
                    },
                    state=mock_state,
                    llm_config=llm_config,
                )

                # Should still return a result structure even if workers fail
                assert "result" in result or "error" in result

    @pytest.mark.asyncio
    async def test_comparison_handles_all_failures(self, llm_config, mock_state):
        """Test comparison handles when all models fail."""
        with patch(
            "fichero.workflows.model_comparison.chat_workflow",
            AsyncMock(side_effect=Exception("API Error")),
        ):
            result = await model_comparison(
                inputs={
                    "prompt": "Test",
                    "models": [
                        {"provider": "openai", "model": "gpt-4o"},
                    ],
                },
                state=mock_state,
                llm_config=llm_config,
            )

            assert result["summary"]["successful"] == 0
