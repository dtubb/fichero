"""
MCP Servers Routes

API endpoints for managing MCP (Model Context Protocol) servers.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fichero.api.routes.auth_accounts import (
    _require_authenticated_or_bootstrap,
    _require_owner_or_bootstrap,
)
from fichero.app_db import get_app_db
from fichero.models import MCPServer
from fichero.mcp_manager import get_mcp_manager, MCPServerConfig
logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(_require_authenticated_or_bootstrap)])


# =============================================================================
# Request/Response Models
# =============================================================================


class CreateMCPServerRequest(BaseModel):
    """Request to create a new MCP server."""

    name: str
    description: str = ""
    transport: str  # "stdio", "sse", "http", or "websocket"
    command: str | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    url: str | None = None
    headers: dict[str, str] = {}
    tool_name_prefix: bool = True
    enabled: bool = True


class UpdateMCPServerRequest(BaseModel):
    """Request to update an existing MCP server."""

    name: str | None = None
    description: str | None = None
    transport: str | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    tool_name_prefix: bool | None = None
    enabled: bool | None = None


class MCPServerResponse(BaseModel):
    """Response containing MCP server details."""

    id: str
    name: str
    description: str
    transport: str
    command: str | None
    args: list[str]
    env: dict[str, str]
    url: str | None
    headers: dict[str, str]
    tool_name_prefix: bool
    enabled: bool
    created_at: str
    updated_at: str


class MCPToolInfo(BaseModel):
    """Information about a tool from an MCP server."""

    name: str
    description: str
    server_name: str


class MCPToolListResponse(BaseModel):
    """List of tools from one or all MCP servers."""

    items: list[MCPToolInfo]
    count: int


class MCPToolRegistryResponse(BaseModel):
    """Result of loading MCP tools into the workflow registry."""

    tool_count: int
    message: str


class MCPServerDeletedResponse(BaseModel):
    """Confirmation that an MCP server was deleted."""

    message: str


class MCPServerToolsResponse(BaseModel):
    """Tools loaded from a specific MCP server."""

    server_id: str
    server_name: str
    tool_count: int
    tools: list[MCPToolInfo]


class MCPServerResponseList(BaseModel):
    items: list[MCPServerResponse]
    count: int


# =============================================================================
# Helper Functions
# =============================================================================


def _server_to_response(server: MCPServer) -> MCPServerResponse:
    """Convert MCPServer model to API response."""
    return MCPServerResponse(
        id=server.id,
        name=server.name,
        description=server.description,
        transport=server.transport,
        command=server.command,
        args=server.args,
        env=server.env,
        url=server.url,
        headers=server.headers,
        tool_name_prefix=server.tool_name_prefix,
        enabled=server.enabled,
        created_at=server.created_at.isoformat(),
        updated_at=server.updated_at.isoformat(),
    )


def _server_to_config(server: MCPServer) -> MCPServerConfig:
    """Convert MCPServer model to MCPServerConfig."""
    return MCPServerConfig(
        name=server.name,
        transport=server.transport,
        command=server.command,
        args=server.args,
        env=server.env,
        url=server.url,
        headers=server.headers,
        tool_name_prefix=server.tool_name_prefix,
        enabled=server.enabled,
    )


# =============================================================================
# API Endpoints
# =============================================================================

# NOTE: Static routes (/tools/all, /tools/load-*, etc.) MUST come BEFORE
# parameterized routes (/{server_id}) to prevent FastAPI from matching
# "tools" as a server_id.


@router.get("/mcp-servers", response_model=MCPServerResponseList)
async def list_mcp_servers():
    """List all MCP servers."""
    try:
        app_db = get_app_db()
        servers = app_db.query_mcp_servers()
        return MCPServerResponseList(
            items=[_server_to_response(server) for server in servers],
            count=len(servers),
        )
    except Exception as e:
        logger.exception(f"Failed to list MCP servers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mcp-servers/tools/all")
async def get_all_mcp_tools() -> MCPToolListResponse:
    """Get all tools from all enabled MCP servers."""
    try:
        app_db = get_app_db()
        manager = get_mcp_manager()

        # Load servers from database into manager
        servers = app_db.query_mcp_servers(enabled=True)
        for server in servers:
            config = _server_to_config(server)
            manager.add_server(config)

        # Load all tools
        tools = await manager.load_all_tools()

        # Convert to response format
        tool_infos = []
        for tool in tools:
            # Extract server name from tool name if prefixed
            tool_name = tool.name
            server_name = "unknown"

            # Try to find which server this tool came from
            for srv_name in manager.servers:
                cached_tools = manager.get_tools_by_server(srv_name)
                if any(t.name == tool_name for t in cached_tools):
                    server_name = srv_name
                    break

            tool_infos.append(
                MCPToolInfo(
                    name=tool_name,
                    description=tool.description or "",
                    server_name=server_name,
                )
            )

        logger.info(f"Loaded {len(tools)} total tools from all servers")
        return MCPToolListResponse(items=tool_infos, count=len(tool_infos))

    except Exception as e:
        logger.exception(f"Failed to load all MCP tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp-servers/tools/load-into-workflow-registry")
async def load_mcp_tools_into_workflow_registry(
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> MCPToolRegistryResponse:
    """Load all MCP tools into the workflow registry.

    This makes MCP tools available in the workflow node editor.
    """
    try:
        app_db = get_app_db()
        manager = get_mcp_manager()

        # Load servers from database into manager
        servers = app_db.query_mcp_servers(enabled=True)
        for server in servers:
            config = _server_to_config(server)
            manager.add_server(config)

        # Load MCP tools into workflow registry
        from fichero.workflows.tools.mcp import load_mcp_tools_into_registry

        tool_count = await load_mcp_tools_into_registry()

        logger.info(f"Loaded {tool_count} MCP tools into workflow registry")
        return MCPToolRegistryResponse(
            tool_count=tool_count,
            message=f"Successfully loaded {tool_count} MCP tools into workflow registry",
        )

    except Exception as e:
        logger.exception(f"Failed to load MCP tools into workflow registry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp-servers/tools/reload-workflow-registry")
async def reload_mcp_tools_in_workflow_registry(
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> MCPToolRegistryResponse:
    """Reload MCP tools in the workflow registry.

    This clears existing MCP tools and reloads them from all enabled servers.
    """
    try:
        app_db = get_app_db()
        manager = get_mcp_manager()

        # Load servers from database into manager
        servers = app_db.query_mcp_servers(enabled=True)
        for server in servers:
            config = _server_to_config(server)
            manager.add_server(config)

        # Reload MCP tools
        from fichero.workflows.tools.mcp import reload_mcp_tools

        tool_count = await reload_mcp_tools()

        logger.info(f"Reloaded {tool_count} MCP tools in workflow registry")
        return MCPToolRegistryResponse(
            tool_count=tool_count,
            message=f"Successfully reloaded {tool_count} MCP tools in workflow registry",
        )

    except Exception as e:
        logger.exception(f"Failed to reload MCP tools in workflow registry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Parameterized routes MUST come AFTER static routes
@router.get("/mcp-servers/{server_id}", response_model=MCPServerResponse)
async def get_mcp_server(server_id: str):
    """Get a specific MCP server by ID."""
    try:
        app_db = get_app_db()
        server = app_db.get_mcp_server(server_id)
        if not server:
            raise HTTPException(
                status_code=404, detail=f"Server not found: {server_id}"
            )
        return _server_to_response(server)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get MCP server {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp-servers", response_model=MCPServerResponse)
async def create_mcp_server(
    request: CreateMCPServerRequest,
    _owner: None = Depends(_require_owner_or_bootstrap),
):
    """Create a new MCP server."""
    try:
        app_db = get_app_db()

        # Check if server with this name already exists
        existing = app_db.query_mcp_servers(name=request.name)
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Server with name '{request.name}' already exists",
            )

        # Create server model
        server = MCPServer(
            name=request.name,
            description=request.description,
            transport=request.transport,
            command=request.command,
            args=request.args,
            env=request.env,
            url=request.url,
            headers=request.headers,
            tool_name_prefix=request.tool_name_prefix,
            enabled=request.enabled,
        )

        # Save to database
        app_db.save_mcp_server(server)

        # Add to MCP manager
        manager = get_mcp_manager()
        config = _server_to_config(server)
        manager.add_server(config)

        logger.info(f"Created MCP server: {server.name}")
        return _server_to_response(server)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to create MCP server: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/mcp-servers/{server_id}", response_model=MCPServerResponse)
async def update_mcp_server(
    server_id: str,
    request: UpdateMCPServerRequest,
    _owner: None = Depends(_require_owner_or_bootstrap),
):
    """Update an existing MCP server."""
    try:
        app_db = get_app_db()

        # Get existing server
        server = app_db.get_mcp_server(server_id)
        if not server:
            raise HTTPException(
                status_code=404, detail=f"Server not found: {server_id}"
            )

        # Update fields
        if request.name is not None:
            server.name = request.name
        if request.description is not None:
            server.description = request.description
        if request.transport is not None:
            server.transport = request.transport
        if request.command is not None:
            server.command = request.command
        if request.args is not None:
            server.args = request.args
        if request.env is not None:
            server.env = request.env
        if request.url is not None:
            server.url = request.url
        if request.headers is not None:
            server.headers = request.headers
        if request.tool_name_prefix is not None:
            server.tool_name_prefix = request.tool_name_prefix
        if request.enabled is not None:
            server.enabled = request.enabled

        # Save to database
        app_db.save_mcp_server(server)

        # Update MCP manager
        manager = get_mcp_manager()
        config = _server_to_config(server)
        manager.add_server(config)

        logger.info(f"Updated MCP server: {server.name}")
        return _server_to_response(server)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update MCP server {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/mcp-servers/{server_id}")
async def delete_mcp_server(
    server_id: str,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> MCPServerDeletedResponse:
    """Delete an MCP server."""
    try:
        app_db = get_app_db()

        # Get existing server
        server = app_db.get_mcp_server(server_id)
        if not server:
            raise HTTPException(
                status_code=404, detail=f"Server not found: {server_id}"
            )

        server_name = server.name

        # Delete from database
        app_db.delete_mcp_server(server_id)

        # Remove from MCP manager
        manager = get_mcp_manager()
        manager.remove_server(server_name)

        logger.info(f"Deleted MCP server: {server_name}")
        return MCPServerDeletedResponse(message=f"Server '{server_name}' deleted successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete MCP server {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp-servers/{server_id}/load-tools")
async def load_server_tools(
    server_id: str,
    force_reload: bool = False,
    _owner: None = Depends(_require_owner_or_bootstrap),
) -> MCPServerToolsResponse:
    """Load tools from a specific MCP server.

    Args:
        server_id: Server ID
        force_reload: Force reload tools even if cached
    """
    try:
        app_db = get_app_db()

        # Get server from database
        server = app_db.get_mcp_server(server_id)
        if not server:
            raise HTTPException(
                status_code=404, detail=f"Server not found: {server_id}"
            )

        if not server.enabled:
            raise HTTPException(
                status_code=400, detail=f"Server '{server.name}' is disabled"
            )

        # Ensure server is in manager
        manager = get_mcp_manager()
        if server.name not in manager.servers:
            config = _server_to_config(server)
            manager.add_server(config)

        # Load tools
        tools = await manager.load_server_tools(server.name, force_reload=force_reload)

        # Convert to response format
        tool_infos = [
            MCPToolInfo(
                name=tool.name,
                description=tool.description or "",
                server_name=server.name,
            )
            for tool in tools
        ]

        logger.info(f"Loaded {len(tools)} tools from server: {server.name}")
        return MCPServerToolsResponse(
            server_id=server_id,
            server_name=server.name,
            tool_count=len(tools),
            tools=tool_infos,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to load tools from server {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
