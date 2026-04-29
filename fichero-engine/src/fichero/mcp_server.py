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

from fichero.mcp_document_tools import TOOLS as DOCUMENT_TOOLS
from fichero.mcp_kg_tools import TOOLS as KG_TOOLS
from fichero.mcp_research_tools import TOOLS as RESEARCH_TOOLS

logger = logging.getLogger(__name__)

# Default Fichero API URL
DEFAULT_API_URL = os.environ.get("FICHERO_API_URL", "http://localhost:8765")

# Create server instance
server = Server("fichero")


# =============================================================================
# API Client
# =============================================================================


class FicheroAPIClient:
    """HTTP client for Fichero API with authentication."""

    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        library_path: str | None = None,
        api_key: str | None = None,
    ):
        self.api_url = api_url.rstrip("/")
        self.library_path = library_path or os.environ.get("FICHERO_LIBRARY_PATH")
        self.api_key = api_key or os.environ.get("FICHERO_API_KEY")

        # Security: Warn if no API key configured
        if not self.api_key:
            logger.warning(
                "FICHERO_API_KEY not set. API calls may be rejected in production."
            )

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.library_path:
            headers["X-Fichero-Library-Path"] = self.library_path
        # Add API key authentication
        if self.api_key:
            headers["X-API-Key"] = self.api_key
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
                    response = await client.get(
                        url, params=params, headers=self._get_headers()
                    )
                elif method == "POST":
                    response = await client.post(
                        url, json=data, headers=self._get_headers()
                    )
                elif method == "PUT":
                    response = await client.put(
                        url, json=data, headers=self._get_headers()
                    )
                elif method == "PATCH":
                    response = await client.patch(
                        url, json=data, headers=self._get_headers()
                    )
                elif method == "DELETE":
                    response = await client.delete(url, headers=self._get_headers())
                else:
                    return {"error": f"Unknown method: {method}"}

                if response.status_code >= 400:
                    return {
                        "error": f"API error {response.status_code}: {response.text}"
                    }

                return response.json()
            except httpx.ConnectError:
                return {
                    "error": f"Cannot connect to Fichero API at {self.api_url}. Is the server running?"
                }
            except Exception as e:
                return {"error": str(e)}


# Global API client
api_client = FicheroAPIClient()

# Combined tool list from all domain modules
TOOLS: list[types.Tool] = DOCUMENT_TOOLS + KG_TOOLS + RESEARCH_TOOLS


# =============================================================================
# Tool Handlers
# =============================================================================


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available Fichero tools."""
    return TOOLS


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any]
) -> list[types.TextContent]:
    """Handle tool calls."""
    try:
        result = await _route_tool(name, arguments)
        return [
            types.TextContent(
                type="text", text=json.dumps(result, indent=2, default=str)
            )
        ]
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
        return await api_client.request(
            "GET",
            "/search",
            params={
                "query": args["query"],
                "limit": args.get("limit", 20),
            },
        )

    elif name == "fichero_get_document":
        return await api_client.request("GET", f"/documents/{args['document_id']}")

    # Workflow tools
    elif name == "fichero_list_workflows":
        return await api_client.request(
            "GET",
            "/workflows",
            params={
                "limit": args.get("limit", 50),
            },
        )

    elif name == "fichero_get_workflow":
        return await api_client.request("GET", f"/workflows/{args['workflow_id']}")

    elif name == "fichero_create_workflow":
        return await api_client.request(
            "POST",
            "/workflows",
            data={
                "name": args["name"],
                "description": args.get("description", ""),
                "nodes": args.get("nodes", []),
                "edges": args.get("edges", []),
            },
        )

    elif name == "fichero_run_workflow":
        return await api_client.request(
            "POST",
            "/workflow-execution/execute",
            data={
                "workflow_id": args["workflow_id"],
                "input_files": args.get("input_files", []),
                "inputs": args.get("inputs", {}),
            },
        )

    elif name == "fichero_workflow_status":
        return await api_client.request(
            "GET", f"/workflow-execution/status/{args['thread_id']}"
        )

    # Batch tools
    elif name == "fichero_create_batch":
        return await api_client.request(
            "POST",
            "/batches",
            data={
                "workflow_id": args["workflow_id"],
                "file_paths": args["file_paths"],
                "concurrency": args.get("concurrency", 4),
            },
        )

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
            "models": args.get(
                "models",
                [
                    {"provider": "openai", "model": "gpt-4o"},
                    {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"},
                ],
            ),
        }
        if args.get("system_prompt"):
            data["system_prompt"] = args["system_prompt"]
        return await api_client.request("POST", "/model-comparison/compare", data=data)

    # Tool registry
    elif name == "fichero_list_tools":
        result = await api_client.request("GET", "/workflows/tools")
        if args.get("category") and "tools" in result:
            result["tools"] = [
                t for t in result["tools"] if t.get("category") == args["category"]
            ]
        return result

    # Health check
    elif name == "fichero_health":
        return await api_client.request("GET", "/health")

    # Workflow chain tools
    elif name == "fichero_list_chains":
        return await api_client.request(
            "GET",
            "/chains",
            params={
                "limit": args.get("limit", 50),
            },
        )

    elif name == "fichero_get_chain":
        return await api_client.request("GET", f"/chains/{args['chain_id']}")

    elif name == "fichero_create_chain":
        return await api_client.request(
            "POST",
            "/chains",
            data={
                "name": args["name"],
                "description": args.get("description", ""),
                "steps": args.get("steps", []),
                "initial_inputs": args.get("initial_inputs", {}),
            },
        )

    elif name == "fichero_run_chain":
        return await api_client.request(
            "POST",
            f"/chains/{args['chain_id']}/execute",
            data={
                "inputs": args.get("inputs", {}),
                "input_files": args.get("input_files", []),
            },
        )

    elif name == "fichero_chain_status":
        return await api_client.request(
            "GET", f"/chains/executions/{args['execution_id']}"
        )

    # Knowledge Graph tools
    elif name == "fichero_kg_list_claims":
        params = {k: v for k, v in args.items() if v is not None and k != "claim_ids"}
        return await api_client.request("GET", "/knowledge-graph/claims", params=params)

    elif name == "fichero_kg_create_claim":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("POST", "/knowledge-graph/claims", data=data)

    elif name == "fichero_kg_patch_claim":
        claim_id = args["claim_id"]
        data = {k: v for k, v in args.items() if v is not None and k != "claim_id"}
        return await api_client.request(
            "PATCH", f"/knowledge-graph/claims/{claim_id}", data=data
        )

    elif name == "fichero_kg_list_entities":
        params = {k: v for k, v in args.items() if v is not None}
        return await api_client.request(
            "GET", "/knowledge-graph/entities", params=params
        )

    elif name == "fichero_kg_upsert_entity":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("POST", "/knowledge-graph/entities", data=data)

    elif name == "fichero_kg_embed_claims":
        data = {}
        if args.get("claim_ids"):
            data["claim_ids"] = args["claim_ids"]
        return await api_client.request(
            "POST", "/knowledge-graph/claims/semantic/embed", data=data
        )

    elif name == "fichero_kg_semantic_search":
        params = {
            "q": args["query"],
            "limit": args.get("limit", 20),
        }
        if args.get("claim_type"):
            params["claim_type"] = args["claim_type"]
        if args.get("curation_state"):
            params["curation_state"] = args["curation_state"]
        return await api_client.request(
            "GET", "/knowledge-graph/claims/semantic", params=params
        )

    elif name == "fichero_kg_embed_entities":
        data = {}
        if args.get("entity_ids"):
            data["entity_ids"] = args["entity_ids"]
        return await api_client.request(
            "POST", "/knowledge-graph/entities/semantic/embed", data=data
        )

    elif name == "fichero_kg_semantic_entity_search":
        params = {
            "q": args["query"],
            "limit": args.get("limit", 20),
        }
        if args.get("entity_type"):
            params["entity_type"] = args["entity_type"]
        return await api_client.request(
            "GET", "/knowledge-graph/entities/semantic", params=params
        )

    elif name == "fichero_kg_overview":
        params = {}
        if args.get("scope_type"):
            params["scope_type"] = args["scope_type"]
        if args.get("target_id"):
            params["target_id"] = args["target_id"]
        return await api_client.request(
            "GET", "/knowledge-graph/overview", params=params
        )

    # Knowledge Graph — Prediction tools
    elif name == "fichero_kg_generate_heuristic_predictions":
        data = {
            k: v
            for k, v in args.items()
            if v is not None and k != "top_k" and k != "entity_id"
        }
        params = {}
        if args.get("top_k"):
            params["top_k"] = args["top_k"]
        if args.get("entity_id"):
            params["entity_id"] = args["entity_id"]
        return await api_client.request(
            "POST",
            "/knowledge-graph/predictions/generate/heuristic",
            data=data,
            params=params,
        )

    elif name == "fichero_kg_apply_predictions":
        run_id = args["run_id"]
        return await api_client.request(
            "POST", f"/knowledge-graph/predictions/{run_id}/apply"
        )

    # Hermeneutics — Circle navigation tools
    elif name == "fichero_hm_create_circle_state":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("POST", "/hermeneutics/circle-state", data=data)

    elif name == "fichero_hm_navigate_circle":
        state_id = args["state_id"]
        data = {k: v for k, v in args.items() if v is not None and k != "state_id"}
        return await api_client.request(
            "POST", f"/hermeneutics/circle-state/{state_id}/navigate", data=data
        )

    # Hermeneutics tools
    elif name == "fichero_hm_list_frameworks":
        params = {k: v for k, v in args.items() if v is not None}
        return await api_client.request(
            "GET", "/hermeneutics/frameworks", params=params
        )

    elif name == "fichero_hm_apply_framework":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request(
            "POST", "/hermeneutics/interpretations", data=data
        )

    elif name == "fichero_hm_find_patterns":
        params = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("GET", "/hermeneutics/patterns", params=params)

    elif name == "fichero_hm_suggest_interpretations":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("POST", "/hermeneutics/suggestions", data=data)

    # Mind Palace tools
    elif name == "fichero_mp_create_room":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("POST", "/mind-palace/rooms", data=data)

    elif name == "fichero_mp_list_rooms":
        params = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("GET", "/mind-palace/rooms", params=params)

    elif name == "fichero_mp_place_node":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("POST", "/mind-palace/nodes", data=data)

    elif name == "fichero_mp_move_node":
        node_id = args["node_id"]
        data = {k: v for k, v in args.items() if v is not None and k != "node_id"}
        return await api_client.request(
            "PATCH", f"/mind-palace/nodes/{node_id}", data=data
        )

    elif name == "fichero_mp_create_connection":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("POST", "/mind-palace/connections", data=data)

    elif name == "fichero_mp_focus_node":
        room_id = args["room_id"]
        node_id = args.get("node_id")
        params = {"room_id": room_id}
        if node_id:
            params["node_id"] = node_id
        return await api_client.request(
            "POST", f"/mind-palace/rooms/{room_id}/focus", params=params
        )

    elif name == "fichero_mp_create_note":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("POST", "/mind-palace/notes", data=data)

    elif name == "fichero_mp_suggest_arrangement":
        room_id = args["room_id"]
        data = {k: v for k, v in args.items() if v is not None and k != "room_id"}
        return await api_client.request(
            "POST", f"/mind-palace/rooms/{room_id}/suggest-arrangement", data=data
        )

    elif name == "fichero_mp_get_scene":
        room_id = args["room_id"]
        return await api_client.request("GET", f"/mind-palace/rooms/{room_id}/scene")

    # Research Agent tools
    elif name == "fichero_research_create_project":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("POST", "/research/projects", data=data)

    elif name == "fichero_research_list_projects":
        params = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("GET", "/research/projects", params=params)

    elif name == "fichero_research_get_project":
        project_id = args["project_id"]
        return await api_client.request("GET", f"/research/projects/{project_id}")

    elif name == "fichero_research_create_plan":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("POST", "/research/plans", data=data)

    elif name == "fichero_research_list_plans":
        project_id = args["project_id"]
        return await api_client.request("GET", f"/research/projects/{project_id}/plans")

    elif name == "fichero_research_create_task":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("POST", "/research/tasks", data=data)

    elif name == "fichero_research_list_tasks":
        plan_id = args["plan_id"]
        return await api_client.request("GET", f"/research/plans/{plan_id}/tasks")

    elif name == "fichero_research_create_step":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("POST", "/research/steps", data=data)

    elif name == "fichero_research_update_step":
        step_id = args["step_id"]
        data = {k: v for k, v in args.items() if v is not None and k != "step_id"}
        return await api_client.request(
            "PATCH", f"/research/steps/{step_id}", data=data
        )

    elif name == "fichero_research_web_search":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("POST", "/research/tools/web-search", data=data)

    elif name == "fichero_research_browser_navigate":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request(
            "POST", "/research/tools/browser-navigate", data=data
        )

    elif name == "fichero_research_document_fetch":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request(
            "POST", "/research/tools/document-fetch", data=data
        )

    elif name == "fichero_research_create_note":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("POST", "/research/notes", data=data)

    elif name == "fichero_research_list_notes":
        project_id = args["project_id"]
        params = {k: v for k, v in args.items() if v is not None and k != "project_id"}
        params["project_id"] = project_id
        return await api_client.request(
            "GET", f"/research/projects/{project_id}/notes", params=params
        )

    elif name == "fichero_research_add_source":
        data = {k: v for k, v in args.items() if v is not None}
        return await api_client.request("POST", "/research/sources", data=data)

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
