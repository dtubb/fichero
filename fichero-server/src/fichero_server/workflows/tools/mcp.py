"""
MCP Tools Integration

Dynamically loads tools from MCP servers and registers them in the workflow registry.
MCP tools are LangChain BaseTool instances that can be used in workflows.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

# `BaseTool` is used only in annotations (evaluated lazily via
# `from __future__ import annotations`). Importing langchain_core eagerly costs
# ~250ms of cold-import time and this module is reachable from the API bind
# path, so keep it behind TYPE_CHECKING (startup speedup, #4038).
if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

from fichero_server.workflows.types import State, PortDef, DataType, ToolDef
from fichero_server.workflows.registry import TOOL_DEFS, TOOLS
from fichero_server.mcp.manager import get_mcp_manager
from fichero_server.llm import LLMConfig

logger = logging.getLogger(__name__)


async def load_mcp_tools_into_registry() -> int:
    """Load all MCP tools from enabled servers into the workflow registry.

    Returns:
        Number of tools loaded
    """
    manager = get_mcp_manager()

    # Load tools from all enabled servers
    try:
        all_tools = await manager.load_all_tools()
        logger.info(f"Loaded {len(all_tools)} MCP tools from servers")
    except Exception as e:
        logger.error(f"Failed to load MCP tools: {e}")
        return 0

    # Register each tool
    registered_count = 0
    for tool in all_tools:
        try:
            _register_mcp_tool(tool)
            registered_count += 1
        except Exception as e:
            logger.error(f"Failed to register MCP tool {tool.name}: {e}")

    logger.info(f"Registered {registered_count} MCP tools in workflow registry")
    return registered_count


def _create_mcp_tool_wrapper(tool: BaseTool, tool_name: str):
    """Factory function to create an MCP tool wrapper.

    This uses a factory pattern to capture `tool` and `tool_name` by value,
    avoiding the closure capture bug where all wrappers would reference
    the last tool in a loop.

    Args:
        tool: LangChain BaseTool instance from MCP server
        tool_name: Name of the tool

    Returns:
        Async wrapper function for the tool
    """

    async def mcp_tool_wrapper(
        inputs: dict[str, Any],
        state: State,
        llm_config: LLMConfig | None = None,
    ) -> dict[str, Any]:
        """Execute an MCP tool.

        Args:
            inputs: Input parameters for the tool
            state: Workflow state
            llm_config: LLM configuration (unused for MCP tools)

        Returns:
            Dict with 'output' key containing tool result
        """
        try:
            # Get the input value
            tool_input = inputs.get("input")
            if tool_input is None:
                return {"error": "No input provided to MCP tool"}

            # Execute the MCP tool with timeout
            # MCP tools are async LangChain tools
            logger.debug(f"Executing MCP tool {tool_name} with input: {tool_input}")
            result = await asyncio.wait_for(
                tool.ainvoke(tool_input),
                timeout=30.0,  # 30 second timeout for MCP tools
            )

            logger.debug(f"MCP tool {tool_name} result: {result}")
            return {"output": result}

        except asyncio.TimeoutError:
            logger.error(f"MCP tool {tool_name} timed out after 30 seconds")
            return {"error": f"MCP tool {tool_name} timed out"}
        except Exception as e:
            logger.exception(f"Error executing MCP tool {tool_name}: {e}")
            return {"error": str(e)}

    return mcp_tool_wrapper


def _register_mcp_tool(tool: BaseTool) -> None:
    """Register a single MCP tool in the workflow registry.

    Args:
        tool: LangChain BaseTool instance from MCP server
    """
    tool_name = tool.name

    # Create input/output ports based on tool schema
    # MCP tools typically have a single input and output
    input_ports = [
        PortDef(
            id="input",
            name="Input",
            port_type="input",
            data_type=DataType.ANY,
            required=True,
            description="Tool input parameters (dict or single value)",
        ),
    ]

    output_ports = [
        PortDef(
            id="output",
            name="Output",
            port_type="output",
            data_type=DataType.ANY,
            description="Tool output result",
        ),
    ]

    # Extract server name from tool name if prefixed (e.g., "time__get_current_time" -> "time")
    server_name = "mcp"
    category = "mcp"
    if "__" in tool_name:
        server_name = tool_name.split("__")[0]
        category = f"mcp_{server_name}"

    # Create tool definition
    tool_def = ToolDef(
        name=tool_name,
        display_name=tool.name.replace("__", " ").replace("_", " ").title(),
        description=tool.description or f"MCP tool from {server_name}",
        category=category,
        icon="server.rack",  # SF Symbol for MCP tools
        color="teal",  # Distinct color for MCP tools
        input_ports=input_ports,
        output_ports=output_ports,
        config_schema={
            "type": "object",
            "properties": {
                "server_name": {
                    "type": "string",
                    "default": server_name,
                    "description": "MCP server name",
                    "readOnly": True,
                },
            },
        },
        uses_llm=False,  # MCP tools are external
        supports_batch=False,
        supports_streaming=False,
        supports_structured_output=False,
        sort_order=1000,  # Put MCP tools at the end
    )

    # Register in TOOL_DEFS
    TOOL_DEFS[tool_name] = tool_def

    # Create wrapper function using factory to capture tool by value (not reference)
    # This fixes the closure capture bug where all tools would use the last tool
    TOOLS[tool_name] = _create_mcp_tool_wrapper(tool, tool_name)

    logger.debug(f"Registered MCP tool: {tool_name} from {server_name}")


def get_mcp_tool_names() -> list[str]:
    """Get names of all registered MCP tools.

    Returns:
        List of MCP tool names
    """
    return [
        name for name in TOOL_DEFS.keys() if TOOL_DEFS[name].category.startswith("mcp")
    ]


def get_mcp_tools_by_server(server_name: str) -> list[str]:
    """Get MCP tools from a specific server.

    Args:
        server_name: MCP server name

    Returns:
        List of tool names from that server
    """
    category = f"mcp_{server_name}"
    return [name for name in TOOL_DEFS.keys() if TOOL_DEFS[name].category == category]


async def reload_mcp_tools() -> int:
    """Reload MCP tools from all servers.

    This clears the MCP manager cache and re-loads all tools.

    Returns:
        Number of tools loaded
    """
    # Clear existing MCP tools from registry
    mcp_tool_names = get_mcp_tool_names()
    for tool_name in mcp_tool_names:
        if tool_name in TOOL_DEFS:
            del TOOL_DEFS[tool_name]
        if tool_name in TOOLS:
            del TOOLS[tool_name]

    logger.info(f"Cleared {len(mcp_tool_names)} existing MCP tools")

    # Clear MCP manager cache
    manager = get_mcp_manager()
    manager.clear_cache()

    # Reload tools
    return await load_mcp_tools_into_registry()
