"""
Tests for Agent Tool

Tests the react_agent tool that uses LangGraph's create_react_agent.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from langchain_core.messages import SystemMessage

from fichero.workflows.tools.agent import react_agent
from fichero.workflows.types import State
from fichero.llm import LLMConfig


@pytest.mark.asyncio
async def test_react_agent_basic():
    """Test basic agent execution without tools."""
    # Setup
    inputs = {
        "task": "Say hello"
,
        "tools": [],
        "system_prompt": "You are a helpful assistant.",
    }
    state: State = {}
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    # Mock the LangGraph agent
    with patch("fichero.workflows.tools.agent.create_react_agent") as mock_create:
        with patch("fichero.workflows.tools.agent.get_langchain_model") as mock_get_model:
            # Setup mocks
            mock_model = Mock()
            mock_get_model.return_value = mock_model

            mock_agent = Mock()
            mock_agent.ainvoke = AsyncMock(return_value={
                "messages": [
                    {"type": "human", "content": "Say hello"},
                    {"type": "ai", "content": "Hello! How can I help you today?"},
                ]
            })
            mock_create.return_value = mock_agent

            # Execute
            result = await react_agent(inputs, state, llm_config)

            # Verify
            assert "result" in result
            assert result["result"] == "Hello! How can I help you today?"
            assert "messages" in result
            assert len(result["messages"]) == 2
            assert "tool_calls" in result
            assert result["tool_calls"] == []


@pytest.mark.asyncio
async def test_react_agent_composes_integrity_system_prompt():
    inputs = {
        "task": "Inspect the records",
        "tools": [],
        "system_prompt": "Use the archive lookup tool before answering.",
    }
    state: State = {}
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")
    captured: dict[str, object] = {}

    with patch("fichero.workflows.tools.agent.create_react_agent") as mock_create:
        with patch("fichero.workflows.tools.agent.get_langchain_model") as mock_get_model:
            mock_get_model.return_value = Mock()

            mock_agent = Mock()

            async def _ainvoke(agent_state):
                captured["messages"] = agent_state["messages"]
                return {
                    "messages": [
                        {"type": "human", "content": "Inspect the records"},
                        {"type": "ai", "content": "Done."},
                    ]
                }

            mock_agent.ainvoke = _ainvoke
            mock_create.return_value = mock_agent

            await react_agent(inputs, state, llm_config)

    messages = captured["messages"]
    assert isinstance(messages, list)
    assert isinstance(messages[0], SystemMessage)
    assert "transparent, local instrument" in messages[0].content
    assert "Use the archive lookup tool before answering." in messages[0].content


@pytest.mark.asyncio
async def test_react_agent_with_tools():
    """Test agent execution with tools."""
    # Setup
    inputs = {
        "task": "Calculate 5 * 3",
        "tools": ["multiply"],
        "system_prompt": "You are a math assistant.",
    }
    state: State = {}
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    # Mock the LangGraph agent
    with patch("fichero.workflows.tools.agent.create_react_agent") as mock_create:
        with patch("fichero.workflows.tools.agent.get_langchain_model") as mock_get_model:
            with patch("fichero.workflows.tools.agent.get_tool") as mock_get_tool:
                with patch("fichero.workflows.registry.TOOL_DEFS") as mock_tool_defs:
                    # Setup mocks
                    mock_model = Mock()
                    mock_get_model.return_value = mock_model

                    # Mock tool
                    async def multiply_tool(inputs, state, llm_config):
                        a = inputs.get("a", 0)
                        b = inputs.get("b", 0)
                        return {"result": a * b}

                    mock_get_tool.return_value = multiply_tool

                    # Mock tool definition
                    from fichero.workflows.types import ToolDef, PortDef, DataType
                    mock_tool_def = ToolDef(
                        name="multiply",
                        display_name="Multiply",
                        description="Multiply two numbers",
                        category="math",
                        icon="number",
                        color="blue",
                        input_ports=[
                            PortDef(id="a", name="A", port_type="input", data_type=DataType.NUMBER, required=True),
                            PortDef(id="b", name="B", port_type="input", data_type=DataType.NUMBER, required=True),
                        ],
                        output_ports=[],
                        config_schema={},
                    )
                    mock_tool_defs.get = Mock(return_value=mock_tool_def)

                    # Mock agent with tool calls
                    mock_agent = Mock()
                    mock_agent.ainvoke = AsyncMock(return_value={
                        "messages": [
                            {"type": "human", "content": "Calculate 5 * 3"},
                            {
                                "type": "ai",
                                "content": "",
                                "tool_calls": [{"name": "multiply", "args": {"a": 5, "b": 3}}]
                            },
                            {"type": "tool", "content": "15"},
                            {"type": "ai", "content": "The result is 15."},
                        ]
                    })
                    mock_create.return_value = mock_agent

                    # Execute
                    result = await react_agent(inputs, state, llm_config)

                    # Verify
                    assert "result" in result
                    assert "15" in result["result"]
                    assert "tool_calls" in result
                    assert len(result["tool_calls"]) == 1
                    assert result["tool_calls"][0]["tool"] == "multiply"


@pytest.mark.asyncio
async def test_react_agent_no_task():
    """Test agent with no task provided."""
    # Setup
    inputs = {
        "tools": [],
    }
    state: State = {}
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    # Execute
    result = await react_agent(inputs, state, llm_config)

    # Verify
    assert "error" in result
    assert "No task provided" in result["error"]
    assert result["result"] == ""
    assert result["messages"] == []


@pytest.mark.asyncio
async def test_react_agent_with_context():
    """Test agent with additional context."""
    # Setup
    inputs = {
        "task": "Summarize the data",
        "context": {"data": "Test data here", "format": "concise"},
        "tools": [],
    }
    state: State = {}
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    with patch("fichero.workflows.tools.agent.create_react_agent") as mock_create:
        with patch("fichero.workflows.tools.agent.get_langchain_model") as mock_get_model:
            # Setup mocks
            mock_model = Mock()
            mock_get_model.return_value = mock_model

            mock_agent = Mock()
            mock_agent.ainvoke = AsyncMock(return_value={
                "messages": [
                    {"type": "system", "content": "Context: data: Test data here\nformat: concise"},
                    {"type": "human", "content": "Summarize the data"},
                    {"type": "ai", "content": "Summary of test data."},
                ]
            })
            mock_create.return_value = mock_agent

            # Execute
            result = await react_agent(inputs, state, llm_config)

            # Verify
            assert "result" in result
            assert len(result["messages"]) == 3
            # Context should be included as system message


@pytest.mark.asyncio
async def test_react_agent_max_iterations():
    """Test agent with max iterations limit."""
    # Setup
    inputs = {
        "task": "Count to 100",
        "tools": [],
        "max_iterations": 3,
    }
    state: State = {}
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    with patch("fichero.workflows.tools.agent.create_react_agent") as mock_create:
        with patch("fichero.workflows.tools.agent.get_langchain_model") as mock_get_model:
            # Setup mocks
            mock_model = Mock()
            mock_get_model.return_value = mock_model

            # Mock agent that keeps making tool calls
            call_count = 0

            async def mock_invoke(state):
                nonlocal call_count
                call_count += 1
                if call_count < 5:  # Simulate infinite loop
                    # Return message with tool calls
                    mock_msg = Mock()
                    mock_msg.content = f"Iteration {call_count}"
                    mock_msg.tool_calls = [{"name": "count", "args": {}}]
                    return {"messages": [mock_msg]}
                else:
                    # Eventually finish
                    mock_msg = Mock()
                    mock_msg.content = "Done counting"
                    mock_msg.tool_calls = []
                    return {"messages": [mock_msg]}

            mock_agent = Mock()
            mock_agent.ainvoke = mock_invoke
            mock_create.return_value = mock_agent

            # Execute
            result = await react_agent(inputs, state, llm_config)

            # Verify - should stop after max_iterations
            assert "iterations" in result
            assert result["iterations"] == 3  # Should stop at max


@pytest.mark.asyncio
async def test_react_agent_error_handling():
    """Test agent error handling."""
    # Setup
    inputs = {
        "task": "Test task",
        "tools": [],
    }
    state: State = {}
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    with patch("fichero.workflows.tools.agent.create_react_agent") as mock_create:
        with patch("fichero.workflows.tools.agent.get_langchain_model") as mock_get_model:
            # Setup mocks to raise error
            mock_model = Mock()
            mock_get_model.return_value = mock_model

            mock_agent = Mock()
            mock_agent.ainvoke = AsyncMock(side_effect=Exception("API Error"))
            mock_create.return_value = mock_agent

            # Execute
            result = await react_agent(inputs, state, llm_config)

            # Verify
            assert "error" in result
            assert "API Error" in result["error"]
            assert result["result"] == ""


@pytest.mark.asyncio
async def test_react_agent_tool_not_found():
    """Test agent with non-existent tool."""
    # Setup
    inputs = {
        "task": "Test task",
        "tools": ["non_existent_tool"],
    }
    state: State = {}
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    with patch("fichero.workflows.tools.agent.create_react_agent") as mock_create:
        with patch("fichero.workflows.tools.agent.get_langchain_model") as mock_get_model:
            with patch("fichero.workflows.tools.agent.get_tool") as mock_get_tool:
                # Setup mocks
                mock_model = Mock()
                mock_get_model.return_value = mock_model

                # Tool not found
                mock_get_tool.return_value = None

                mock_agent = Mock()
                mock_agent.ainvoke = AsyncMock(return_value={
                    "messages": [
                        {"type": "human", "content": "Test task"},
                        {"type": "ai", "content": "I can help with that."},
                    ]
                })
                mock_create.return_value = mock_agent

                # Execute - should work but without the tool
                result = await react_agent(inputs, state, llm_config)

                # Verify - should still work, just without tools
                assert "result" in result
                # Agent was created with empty tools list


def test_agent_tool_registration():
    """Test that react_agent is properly registered."""
    from fichero.workflows.registry import TOOLS, TOOL_DEFS

    assert "react_agent" in TOOLS
    assert "react_agent" in TOOL_DEFS

    tool_def = TOOL_DEFS["react_agent"]
    assert tool_def.name == "react_agent"
    assert tool_def.display_name == "ReAct Agent"
    assert tool_def.category == "agent"
    assert tool_def.uses_llm is True
    assert tool_def.supports_streaming is True

    # Check ports
    assert len(tool_def.input_ports) == 2
    assert tool_def.input_ports[0].id == "task"
    assert tool_def.input_ports[1].id == "context"

    assert len(tool_def.output_ports) == 3
    assert tool_def.output_ports[0].id == "result"
    assert tool_def.output_ports[1].id == "messages"
    assert tool_def.output_ports[2].id == "tool_calls"

    # Check config schema
    assert "tools" in tool_def.config_schema
    assert "system_prompt" in tool_def.config_schema
    assert "max_iterations" in tool_def.config_schema
