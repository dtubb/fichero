"""Tests for the react_agent workflow tool."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

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

    with patch(
        "fichero.workflows.tools.agent.chat_workflow",
        new=AsyncMock(return_value="Hello! How can I help you today?"),
    ) as mock_chat:
        result = await react_agent(inputs, state, llm_config)

    assert "result" in result
    assert result["result"] == "Hello! How can I help you today?"
    assert "messages" in result
    assert len(result["messages"]) == 3
    assert result["messages"][0]["role"] == "system"
    assert result["messages"][-1]["role"] == "ai"
    assert "tool_calls" in result
    assert result["tool_calls"] == []
    assert mock_chat.await_count == 1
    assert "tools" not in mock_chat.await_args.kwargs


@pytest.mark.asyncio
async def test_react_agent_composes_integrity_system_prompt():
    inputs = {
        "task": "Inspect the records",
        "tools": [],
        "system_prompt": "Use the archive lookup tool before answering.",
    }
    state: State = {}
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")
    async def _capture_messages(messages, *_args, **_kwargs):
        return "Done."

    with patch(
        "fichero.workflows.tools.agent.chat_workflow",
        new=AsyncMock(side_effect=_capture_messages),
    ) as mock_chat:
        await react_agent(inputs, state, llm_config)

    messages = mock_chat.await_args.args[0]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert "transparent, local instrument" in messages[0]["content"]
    assert "Use the archive lookup tool before answering." in messages[0]["content"]


@pytest.mark.asyncio
async def test_react_agent_uses_central_chat_workflow_entry_point():
    inputs = {
        "task": "Say hello",
        "tools": [],
    }
    state: State = {}
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    with patch(
        "fichero.workflows.tools.agent.chat_workflow",
        new=AsyncMock(return_value="Hello from central path"),
    ) as mock_chat, patch(
        "fichero.llm.get_langchain_model",
        side_effect=AssertionError("react_agent should use chat_workflow"),
    ):
        result = await react_agent(inputs, state, llm_config)

    assert result["result"] == "Hello from central path"
    assert mock_chat.await_count == 1


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

    with patch("fichero.workflows.tools.agent.get_tool") as mock_get_tool:
        with patch("fichero.workflows.registry.TOOL_DEFS") as mock_tool_defs:
            async def multiply_tool(inputs, state, llm_config):
                a = inputs.get("a", 0)
                b = inputs.get("b", 0)
                return {"result": a * b}

            mock_get_tool.return_value = multiply_tool

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

            with patch(
                "fichero.workflows.tools.agent.chat_workflow",
                new=AsyncMock(
                    side_effect=[
                        {
                            "content": "",
                            "tool_calls": [{"id": "call-1", "name": "multiply", "args": {"a": 5, "b": 3}}],
                        },
                        {
                            "content": "The result is 15.",
                            "tool_calls": [],
                        },
                    ]
                ),
            ) as mock_chat:
                result = await react_agent(inputs, state, llm_config)

    assert "15" in result["result"]
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["tool"] == "multiply"
    assert mock_chat.await_count == 2
    assert "tools" in mock_chat.await_args_list[0].kwargs
    assert any(msg["role"] == "tool" for msg in mock_chat.await_args_list[1].args[0])


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

    with patch(
        "fichero.workflows.tools.agent.chat_workflow",
        new=AsyncMock(return_value="Summary of test data."),
    ) as mock_chat:
        result = await react_agent(inputs, state, llm_config)

    assert "result" in result
    assert len(result["messages"]) == 4
    prompt_messages = mock_chat.await_args.args[0]
    assert prompt_messages[1]["content"] == "Context:\ndata: Test data here\nformat: concise"


@pytest.mark.asyncio
async def test_react_agent_max_iterations():
    """Test agent with max iterations limit."""
    # Setup
    inputs = {
        "task": "Count to 100",
        "tools": ["count"],
        "max_iterations": 3,
    }
    state: State = {}
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    with patch(
        "fichero.workflows.tools.agent.chat_workflow",
        new=AsyncMock(
            side_effect=[
                {"content": "Iteration 1", "tool_calls": [{"id": "1", "name": "count", "args": {}}]},
                {"content": "Iteration 2", "tool_calls": [{"id": "2", "name": "count", "args": {}}]},
                {"content": "Iteration 3", "tool_calls": [{"id": "3", "name": "count", "args": {}}]},
            ]
        ),
    ):
        with patch("fichero.workflows.tools.agent.get_tool") as mock_get_tool:
            with patch("fichero.workflows.registry.TOOL_DEFS") as mock_tool_defs:
                async def count_tool(inputs, state, llm_config):
                    return {"ok": True}

                mock_get_tool.return_value = count_tool
                from fichero.workflows.types import ToolDef

                mock_tool_defs.get = Mock(
                    return_value=ToolDef(
                        name="count",
                        display_name="Count",
                        description="Count",
                        category="math",
                        icon="number",
                        color="blue",
                        input_ports=[],
                        output_ports=[],
                        config_schema={},
                    )
                )
                result = await react_agent(inputs, state, llm_config)

    assert "iterations" in result
    assert result["iterations"] == 3


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

    with patch(
        "fichero.workflows.tools.agent.chat_workflow",
        new=AsyncMock(side_effect=Exception("API Error")),
    ):
        result = await react_agent(inputs, state, llm_config)

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

    with patch("fichero.workflows.tools.agent.get_tool", return_value=None):
        with patch(
            "fichero.workflows.tools.agent.chat_workflow",
            new=AsyncMock(return_value="I can help with that."),
        ) as mock_chat:
            result = await react_agent(inputs, state, llm_config)

    assert "result" in result
    assert mock_chat.await_count == 1
    assert "tools" not in mock_chat.await_args.kwargs


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
