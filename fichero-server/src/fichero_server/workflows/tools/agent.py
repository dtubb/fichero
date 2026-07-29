"""
Agent Tools

ReAct agent nodes that can use tools to accomplish tasks.
Uses LangGraph's create_react_agent for tool-calling agents.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fichero_server.workflows.types import State, PortDef, DataType
from fichero_server.workflows.registry import register_tool, get_tool
from fichero_server.llm import LLMConfig, chat_workflow
from fichero_server.llm.prompts import compose_system_prompt

logger = logging.getLogger(__name__)

_DEFAULT_AGENT_SYSTEM_PROMPT = (
    "You are a helpful AI assistant. Use the available tools to accomplish the task."
)


def _build_agent_messages(
    task: str,
    context: Any,
    system_prompt: str,
) -> list[dict[str, Any]]:
    effective_system_prompt = compose_system_prompt(
        role="agent",
        extra=system_prompt,
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": effective_system_prompt}
    ]

    if context:
        if isinstance(context, str):
            messages.append({"role": "system", "content": f"Context: {context}"})
        elif isinstance(context, dict):
            context_str = "\n".join(f"{k}: {v}" for k, v in context.items())
            messages.append({"role": "system", "content": f"Context:\n{context_str}"})

    messages.append({"role": "user", "content": task})
    return messages


def _tool_result_to_message_content(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, default=str)


def _serialize_agent_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    role_map = {
        "assistant": "ai",
        "user": "human",
    }
    serialized = []
    for msg in messages:
        serialized_msg = {
            "role": role_map.get(msg.get("role", ""), msg.get("role", "")),
            "content": msg.get("content", ""),
        }
        if "tool_calls" in msg:
            serialized_msg["tool_calls"] = msg["tool_calls"]
        if msg.get("role") == "tool" and "name" in msg:
            serialized_msg["name"] = msg["name"]
        serialized.append(serialized_msg)
    return serialized


async def _run_agent_loop(
    task: str,
    context: Any,
    system_prompt: str,
    tool_specs: list[dict[str, Any]],
    llm_config: LLMConfig,
    max_iterations: int,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], int]:
    messages = _build_agent_messages(task, context, system_prompt)
    tool_history: list[dict[str, Any]] = []
    tool_map = {tool["name"]: tool for tool in tool_specs}
    iteration = 0

    if not tool_specs:
        response_text = await chat_workflow(messages, llm_config)
        messages.append({"role": "assistant", "content": response_text})
        return response_text, messages, tool_history, iteration

    while iteration < max_iterations:
        response = await chat_workflow(
            messages,
            llm_config,
            tools=[tool["wrapped"] for tool in tool_specs],
        )
        tool_calls = response.get("tool_calls", [])
        messages.append(
            {
                "role": "assistant",
                "content": response.get("content", ""),
                "tool_calls": tool_calls,
            }
        )

        if not tool_calls:
            return response.get("content", ""), messages, tool_history, iteration

        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            tool_spec = tool_map.get(tool_name)
            if tool_spec is None:
                raise ValueError(f"Tool not found: {tool_name}")

            tool_args = tool_call.get("args", {}) or {}
            tool_result = await tool_spec["tool_fn"](
                inputs=tool_args,
                state={},
                llm_config=llm_config,
            )
            tool_history.append({"tool": tool_name, "args": tool_args})
            messages.append(
                {
                    "role": "tool",
                    "name": tool_name,
                    "tool_call_id": tool_call.get("id", tool_name),
                    "content": _tool_result_to_message_content(tool_result),
                }
            )

        iteration += 1

    logger.warning(f"Agent reached max iterations ({max_iterations})")
    return "", messages, tool_history, iteration


@register_tool(
    name="react_agent",
    display_name="ReAct Agent",
    description="AI agent that uses tools to accomplish tasks",
    category="agent",
    icon="cpu",
    color="purple",
    uses_llm=True,
    supports_streaming=True,
    input_ports=[
        PortDef(
            id="task",
            name="Task",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Task description or user query",
        ),
        PortDef(
            id="context",
            name="Context",
            port_type="input",
            data_type=DataType.ANY,
            required=False,
            description="Additional context for the agent",
        ),
    ],
    output_ports=[
        PortDef(
            id="result",
            name="Result",
            port_type="output",
            data_type=DataType.TEXT,
            description="Agent's response",
        ),
        PortDef(
            id="messages",
            name="Messages",
            port_type="output",
            data_type=DataType.ARRAY,
            description="Full message history",
        ),
        PortDef(
            id="tool_calls",
            name="Tool Calls",
            port_type="output",
            data_type=DataType.ARRAY,
            description="List of tool calls made by the agent",
        ),
    ],
    config_schema={
        "tools": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
            "description": "List of tool names available to the agent",
        },
        "system_prompt": {
            "type": "string",
            "default": _DEFAULT_AGENT_SYSTEM_PROMPT,
            "description": "System prompt for the agent",
        },
        "max_iterations": {
            "type": "integer",
            "default": 10,
            "description": "Maximum number of tool-calling iterations",
        },
    },
)
async def react_agent(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Execute a ReAct agent with specified tools.

    The agent will use tools iteratively to accomplish the given task,
    following the ReAct pattern: Reasoning, Acting, Observing.

    Args:
        inputs: Resolved inputs from workflow
            - task: The task or query for the agent
            - context: Additional context (optional)
            - tools: List of tool names to make available
            - system_prompt: Custom system prompt
            - max_iterations: Max iterations for tool calls
        state: Current workflow state
        llm_config: LLM configuration

    Returns:
        Dict with agent response, messages, and tool call history
    """
    # Get inputs
    task = inputs.get("task", "")
    context = inputs.get("context")
    tool_names = inputs.get("tools", [])
    system_prompt = inputs.get(
        "system_prompt",
        _DEFAULT_AGENT_SYSTEM_PROMPT,
    )
    max_iterations = inputs.get("max_iterations", 10)

    if not task:
        return {
            "result": "",
            "messages": [],
            "tool_calls": [],
            "error": "No task provided to agent",
        }

    try:
        # Resolve tool references to actual tool functions
        agent_tools = []
        for tool_name in tool_names:
            tool_fn = get_tool(tool_name)
            if tool_fn:
                agent_tools.append(
                    {
                        "name": tool_name,
                        "tool_fn": tool_fn,
                        "wrapped": _wrap_workflow_tool(
                            tool_name, tool_fn, llm_config
                        ),
                    }
                )
            else:
                logger.warning(f"Tool not found: {tool_name}")

        if not agent_tools:
            logger.warning("No tools available for agent, proceeding without tools")

        result_text, final_messages, tool_calls, iteration = await _run_agent_loop(
            task=task,
            context=context,
            system_prompt=system_prompt,
            tool_specs=agent_tools,
            llm_config=llm_config,
            max_iterations=max_iterations,
        )

        return {
            "result": result_text,
            "messages": _serialize_agent_messages(final_messages),
            "tool_calls": tool_calls,
            "iterations": iteration,
        }

    except Exception as e:
        logger.exception(f"Agent execution failed: {e}")
        return {
            "result": "",
            "messages": [],
            "tool_calls": [],
            "error": str(e),
        }


def _wrap_workflow_tool(
    tool_name: str, tool_fn: callable, llm_config: LLMConfig
) -> callable:
    """Wrap a workflow tool for LangChain/LangGraph compatibility.

    LangChain tools expect a simple function signature with named parameters,
    while workflow tools expect (inputs, state, llm_config).

    This wrapper adapts between the two interfaces.
    """
    from langchain_core.tools import tool
    from fichero_server.workflows.registry import TOOL_DEFS

    # Get tool metadata
    tool_def = TOOL_DEFS.get(tool_name)
    if not tool_def:
        raise ValueError(f"Tool definition not found: {tool_name}")

    # Build docstring from tool metadata
    docstring = f"{tool_def.description}\n\n"

    # Add input port descriptions
    if tool_def.input_ports:
        docstring += "Args:\n"
        for port in tool_def.input_ports:
            required_str = " (required)" if port.required else " (optional)"
            docstring += f"    {port.id}: {port.description}{required_str}\n"

    # Create wrapper function
    @tool
    async def wrapped_tool(**kwargs) -> dict:
        """Wrapped workflow tool for LangChain."""
        # Call original tool with workflow interface
        empty_state = {}  # Agent tools don't need full workflow state
        result = await tool_fn(
            inputs=kwargs,
            state=empty_state,
            llm_config=llm_config,
        )
        return result

    # Set function name and docstring
    wrapped_tool.__name__ = tool_name
    wrapped_tool.__doc__ = docstring

    return wrapped_tool
