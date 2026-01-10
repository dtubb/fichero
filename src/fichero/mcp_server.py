"""
Fichero MCP Server

Exposes Fichero API as MCP tools for use by Claude Code and other agents.
This allows external agents to:
- List and search documents
- Run and manage workflows
- Monitor activity
- Execute actions

Usage:
    python -m fichero.mcp_server [--api-url http://localhost:8765]

To add to Claude Code settings.json:
{
  "mcpServers": {
    "fichero": {
      "command": "python",
      "args": ["-m", "fichero.mcp_server"],
      "env": {
        "FICHERO_API_URL": "http://localhost:8765"
      }
    }
  }
}
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import json
import os
from typing import Any

import httpx
import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

logger = logging.getLogger(__name__)

# Default Fichero API URL
DEFAULT_API_URL = os.environ.get("FICHERO_API_URL", "http://localhost:8765")

# Create server instance
server = Server("fichero")


# =============================================================================
# API Client
# =============================================================================

class FicheroAPIClient:
    """HTTP client for Fichero API."""

    def __init__(self, api_url: str = DEFAULT_API_URL, library_path: str | None = None):
        self.api_url = api_url.rstrip("/")
        self.library_path = library_path or os.environ.get("FICHERO_LIBRARY_PATH")

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.library_path:
            headers["X-Fichero-Library-Path"] = self.library_path
        return headers

    async def request(
        self,
        method: str,
        endpoint: str,
        data: dict | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        url = f"{self.api_url}/api{endpoint}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                if method == "GET":
                    response = await client.get(url, params=params, headers=self._get_headers())
                elif method == "POST":
                    response = await client.post(url, json=data, headers=self._get_headers())
                elif method == "PUT":
                    response = await client.put(url, json=data, headers=self._get_headers())
                elif method == "DELETE":
                    response = await client.delete(url, headers=self._get_headers())
                else:
                    return {"error": f"Unknown method: {method}"}

                if response.status_code >= 400:
                    return {"error": f"API error {response.status_code}: {response.text}"}

                return response.json()
            except httpx.ConnectError:
                return {"error": f"Cannot connect to Fichero API at {self.api_url}. Is the server running?"}
            except Exception as e:
                return {"error": str(e)}


# Global API client
api_client = FicheroAPIClient()


# =============================================================================
# Tool Definitions
# =============================================================================

TOOLS = [
    # Document tools
    types.Tool(
        name="fichero_list_documents",
        description="List documents in the Fichero library with optional filtering by folder",
        inputSchema={
            "type": "object",
            "properties": {
                "folder_id": {"type": "string", "description": "Filter by folder ID"},
                "limit": {"type": "integer", "description": "Max results (default 50)", "default": 50},
                "offset": {"type": "integer", "description": "Pagination offset", "default": 0},
            },
        },
    ),
    types.Tool(
        name="fichero_search_documents",
        description="Search documents by text query using semantic search",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results (default 20)", "default": 20},
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="fichero_get_document",
        description="Get full document details including extracted text content",
        inputSchema={
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "Document UUID"},
            },
            "required": ["document_id"],
        },
    ),
    # Workflow tools
    types.Tool(
        name="fichero_list_workflows",
        description="List saved workflow definitions",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results", "default": 50},
            },
        },
    ),
    types.Tool(
        name="fichero_get_workflow",
        description="Get workflow definition by ID including nodes and edges",
        inputSchema={
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "Workflow ID"},
            },
            "required": ["workflow_id"],
        },
    ),
    types.Tool(
        name="fichero_create_workflow",
        description="Create a new workflow definition with nodes and edges",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Workflow name"},
                "description": {"type": "string", "description": "Workflow description"},
                "nodes": {
                    "type": "array",
                    "description": "Workflow nodes with id, tool, inputs, config",
                    "items": {"type": "object"},
                },
                "edges": {
                    "type": "array",
                    "description": "Workflow edges with source, target",
                    "items": {"type": "object"},
                },
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="fichero_run_workflow",
        description="Execute a workflow on files and return thread ID for tracking",
        inputSchema={
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "Workflow ID to run"},
                "input_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File paths to process",
                },
                "inputs": {
                    "type": "object",
                    "description": "Additional workflow inputs",
                },
            },
            "required": ["workflow_id"],
        },
    ),
    types.Tool(
        name="fichero_workflow_status",
        description="Get status and results of a running workflow execution",
        inputSchema={
            "type": "object",
            "properties": {
                "thread_id": {"type": "string", "description": "Workflow thread ID from run_workflow"},
            },
            "required": ["thread_id"],
        },
    ),
    # Batch tools
    types.Tool(
        name="fichero_create_batch",
        description="Create a batch job to process multiple files with a workflow",
        inputSchema={
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "Workflow to run"},
                "file_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files to process",
                },
                "concurrency": {"type": "integer", "description": "Parallel executions (default 4)", "default": 4},
            },
            "required": ["workflow_id", "file_paths"],
        },
    ),
    types.Tool(
        name="fichero_batch_status",
        description="Get batch job status including progress and results",
        inputSchema={
            "type": "object",
            "properties": {
                "batch_id": {"type": "string", "description": "Batch ID"},
            },
            "required": ["batch_id"],
        },
    ),
    # Activity tools
    types.Tool(
        name="fichero_list_activities",
        description="List recent workflow activities with optional status filter",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter: pending, running, completed, failed"},
                "limit": {"type": "integer", "description": "Max results", "default": 20},
            },
        },
    ),
    # Action tools
    types.Tool(
        name="fichero_list_actions",
        description="List available actions from the action library",
        inputSchema={
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Filter by category: ai, transform, extract, etc."},
            },
        },
    ),
    # Model comparison
    types.Tool(
        name="fichero_compare_models",
        description="Compare a prompt across multiple LLM models to find best/cheapest",
        inputSchema={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Prompt to send to all models"},
                "models": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "provider": {"type": "string"},
                            "model": {"type": "string"},
                        },
                    },
                    "description": "Models to compare (default: gpt-4o and claude-3-5-sonnet)",
                },
                "system_prompt": {"type": "string", "description": "Optional system prompt"},
            },
            "required": ["prompt"],
        },
    ),
    # Tool registry
    types.Tool(
        name="fichero_list_tools",
        description="List available workflow tools that can be used in nodes",
        inputSchema={
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Filter by category: llm, transform, agent, etc."},
            },
        },
    ),
    # Health check
    types.Tool(
        name="fichero_health",
        description="Check Fichero API health and connection status",
        inputSchema={"type": "object", "properties": {}},
    ),
    # Workflow chain tools
    types.Tool(
        name="fichero_list_chains",
        description="List saved workflow chains that connect multiple workflows together",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results (default 50)", "default": 50},
            },
        },
    ),
    types.Tool(
        name="fichero_get_chain",
        description="Get a workflow chain definition by ID including steps and mappings",
        inputSchema={
            "type": "object",
            "properties": {
                "chain_id": {"type": "string", "description": "Chain ID"},
            },
            "required": ["chain_id"],
        },
    ),
    types.Tool(
        name="fichero_create_chain",
        description="Create a new workflow chain to connect workflows together",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Chain name"},
                "description": {"type": "string", "description": "Chain description"},
                "steps": {
                    "type": "array",
                    "description": "Chain steps with workflow_id and input_mappings",
                    "items": {"type": "object"},
                },
                "initial_inputs": {"type": "object", "description": "Default initial inputs"},
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="fichero_run_chain",
        description="Execute a workflow chain and return execution ID for tracking",
        inputSchema={
            "type": "object",
            "properties": {
                "chain_id": {"type": "string", "description": "Chain ID to execute"},
                "inputs": {"type": "object", "description": "Initial inputs for the chain"},
                "input_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Initial input files",
                },
            },
            "required": ["chain_id"],
        },
    ),
    types.Tool(
        name="fichero_chain_status",
        description="Get status and results of a chain execution",
        inputSchema={
            "type": "object",
            "properties": {
                "execution_id": {"type": "string", "description": "Execution ID from run_chain"},
            },
            "required": ["execution_id"],
        },
    ),
]


# =============================================================================
# Tool Handlers
# =============================================================================

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available Fichero tools."""
    return TOOLS


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Handle tool calls."""
    try:
        result = await _route_tool(name, arguments)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except Exception as e:
        logger.exception(f"Tool {name} failed: {e}")
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def _route_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Route tool calls to appropriate handlers."""

    # Document tools
    if name == "fichero_list_documents":
        params = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("GET", "/documents", params=params)

    elif name == "fichero_search_documents":
        return await api_client.request("GET", "/search", params={
            "query": args["query"],
            "limit": args.get("limit", 20),
        })

    elif name == "fichero_get_document":
        return await api_client.request("GET", f"/documents/{args['document_id']}")

    # Workflow tools
    elif name == "fichero_list_workflows":
        return await api_client.request("GET", "/workflows", params={
            "limit": args.get("limit", 50),
        })

    elif name == "fichero_get_workflow":
        return await api_client.request("GET", f"/workflows/{args['workflow_id']}")

    elif name == "fichero_create_workflow":
        return await api_client.request("POST", "/workflows", data={
            "name": args["name"],
            "description": args.get("description", ""),
            "nodes": args.get("nodes", []),
            "edges": args.get("edges", []),
        })

    elif name == "fichero_run_workflow":
        return await api_client.request("POST", "/workflow-execution/execute", data={
            "workflow_id": args["workflow_id"],
            "input_files": args.get("input_files", []),
            "inputs": args.get("inputs", {}),
        })

    elif name == "fichero_workflow_status":
        return await api_client.request("GET", f"/workflow-execution/status/{args['thread_id']}")

    # Batch tools
    elif name == "fichero_create_batch":
        return await api_client.request("POST", "/batches", data={
            "workflow_id": args["workflow_id"],
            "file_paths": args["file_paths"],
            "concurrency": args.get("concurrency", 4),
        })

    elif name == "fichero_batch_status":
        return await api_client.request("GET", f"/batches/{args['batch_id']}")

    # Activity tools
    elif name == "fichero_list_activities":
        params = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("GET", "/activities", params=params)

    # Action tools
    elif name == "fichero_list_actions":
        params = {}
        if args.get("category"):
            params["category"] = args["category"]
        return await api_client.request("GET", "/actions", params=params)

    # Model comparison
    elif name == "fichero_compare_models":
        data = {
            "prompt": args["prompt"],
            "models": args.get("models", [
                {"provider": "openai", "model": "gpt-4o"},
                {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"},
            ]),
        }
        if args.get("system_prompt"):
            data["system_prompt"] = args["system_prompt"]
        return await api_client.request("POST", "/model-comparison/compare", data=data)

    # Tool registry
    elif name == "fichero_list_tools":
        result = await api_client.request("GET", "/workflows/tools")
        if args.get("category") and "tools" in result:
            result["tools"] = [t for t in result["tools"] if t.get("category") == args["category"]]
        return result

    # Health check
    elif name == "fichero_health":
        return await api_client.request("GET", "/health")

    # Workflow chain tools
    elif name == "fichero_list_chains":
        return await api_client.request("GET", "/chains", params={
            "limit": args.get("limit", 50),
        })

    elif name == "fichero_get_chain":
        return await api_client.request("GET", f"/chains/{args['chain_id']}")

    elif name == "fichero_create_chain":
        return await api_client.request("POST", "/chains", data={
            "name": args["name"],
            "description": args.get("description", ""),
            "steps": args.get("steps", []),
            "initial_inputs": args.get("initial_inputs", {}),
        })

    elif name == "fichero_run_chain":
        return await api_client.request("POST", f"/chains/{args['chain_id']}/execute", data={
            "inputs": args.get("inputs", {}),
            "input_files": args.get("input_files", []),
        })

    elif name == "fichero_chain_status":
        return await api_client.request("GET", f"/chains/executions/{args['execution_id']}")

    else:
        return {"error": f"Unknown tool: {name}"}


# =============================================================================
# Server Runner
# =============================================================================

async def run_server():
    """Run the MCP server using stdio transport."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="fichero",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fichero MCP Server")
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"Fichero API URL (default: {DEFAULT_API_URL})",
    )
    parser.add_argument(
        "--library-path",
        help="Library path for API requests",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Update global client with args
    global api_client
    api_client = FicheroAPIClient(
        api_url=args.api_url,
        library_path=args.library_path,
    )

    asyncio.run(run_server())


if __name__ == "__main__":
    main()
