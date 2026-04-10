"""
Agent Tools

ReAct agent nodes that can use tools to accomplish tasks.
Uses LangGraph's create_react_agent for tool-calling agents.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from fichero.workflows.types import State, PortDef, DataType
from fichero.workflows.registry import register_tool, get_tool
from fichero.llm import get_langchain_model, LLMConfig

logger = logging.getLogger(__name__)


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
            "default": "You are a helpful AI assistant. Use the available tools to accomplish the task.",
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
        "You are a helpful AI assistant. Use the available tools to accomplish the task.",
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
                # Wrap workflow tool for LangChain compatibility
                wrapped_tool = _wrap_workflow_tool(tool_name, tool_fn, llm_config)
                agent_tools.append(wrapped_tool)
            else:
                logger.warning(f"Tool not found: {tool_name}")

        if not agent_tools:
            logger.warning("No tools available for agent, proceeding without tools")

        # Get LangChain model
        model = get_langchain_model(llm_config)

        # Build message list
        messages = []

        # Add context if provided
        if context:
            if isinstance(context, str):
                messages.append(SystemMessage(content=f"Context: {context}"))
            elif isinstance(context, dict):
                context_str = "\n".join(f"{k}: {v}" for k, v in context.items())
                messages.append(SystemMessage(content=f"Context:\n{context_str}"))

        # Add user task
        messages.append(HumanMessage(content=task))

        # Create ReAct agent
        # Note: create_react_agent doesn't support state_modifier in current version
        # System prompt needs to be added to messages instead
        if (
            system_prompt
            and system_prompt
            != "You are a helpful AI assistant. Use the available tools to accomplish the task."
        ):
            # Prepend custom system prompt to messages
            messages.insert(0, SystemMessage(content=system_prompt))

        agent_graph = create_react_agent(
            model=model,
            tools=agent_tools if agent_tools else [],
        )

        # Execute agent with iteration limit
        agent_state = {"messages": messages}

        # Track iterations to prevent infinite loops
        iteration = 0
        while iteration < max_iterations:
            result = await agent_graph.ainvoke(agent_state)

            # Check if agent is done (no more tool calls)
            last_message = result["messages"][-1] if result["messages"] else None
            if (
                not last_message
                or not hasattr(last_message, "tool_calls")
                or not last_message.tool_calls
            ):
                # Agent is done
                agent_state = result
                break

            # Continue with updated state
            agent_state = result
            iteration += 1

        if iteration >= max_iterations:
            logger.warning(f"Agent reached max iterations ({max_iterations})")

        # Extract result from messages
        final_messages = agent_state.get("messages", [])

        # Get the last AI message as the result
        result_text = ""
        for msg in reversed(final_messages):
            if isinstance(msg, AIMessage):
                result_text = msg.content
                break
            elif isinstance(msg, dict) and msg.get("type") == "ai":
                result_text = msg.get("content", "")
                break

        # Extract tool call history
        tool_calls = []
        for msg in final_messages:
            if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls"):
                for tc in msg.tool_calls:
                    tool_calls.append(
                        {
                            "tool": tc.get("name", "unknown"),
                            "args": tc.get("args", {}),
                        }
                    )
            elif isinstance(msg, dict) and "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    tool_calls.append(
                        {
                            "tool": tc.get("name", "unknown"),
                            "args": tc.get("args", {}),
                        }
                    )

        # Convert messages to serializable format
        serializable_messages = []
        for msg in final_messages:
            if isinstance(msg, (HumanMessage, AIMessage, SystemMessage)):
                serializable_messages.append(
                    {
                        "role": msg.type,
                        "content": msg.content,
                    }
                )
            elif isinstance(msg, dict):
                # Already in dict format (from tests or other sources)
                serializable_messages.append(msg)

        return {
            "result": result_text,
            "messages": serializable_messages,
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
    from fichero.workflows.registry import TOOL_DEFS

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
