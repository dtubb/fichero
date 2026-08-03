"""
MCP Tool definitions for documents, workflows, batch jobs, and workflow chains.

Each tool maps 1:1 to a Fichero API endpoint.
"""

from __future__ import annotations

import mcp.types as types

TOOLS: list[types.Tool] = [
    # Document tools
    types.Tool(
        name="fichero_list_documents",
        description="List documents in the Fichero library with optional filtering by folder",
        inputSchema={
            "type": "object",
            "properties": {
                "folder_id": {"type": "string", "description": "Filter by folder ID"},
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 50)",
                    "default": 50,
                },
                "offset": {
                    "type": "integer",
                    "description": "Pagination offset",
                    "default": 0,
                },
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
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 20)",
                    "default": 20,
                },
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
        description=(
            "List saved workflow definitions, each with the engine's run "
            "eligibility: direct_runnable=false is an internal component that "
            "cannot be run on its own, requires_vision=true needs a "
            "vision-capable model."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 50,
                },
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
                "description": {
                    "type": "string",
                    "description": "Workflow description",
                },
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
                "thread_id": {
                    "type": "string",
                    "description": "Workflow thread ID from run_workflow",
                },
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
                "concurrency": {
                    "type": "integer",
                    "description": "Parallel executions (default 4)",
                    "default": 4,
                },
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
                "status": {
                    "type": "string",
                    "description": "Filter: pending, running, completed, failed",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 20,
                },
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
                "category": {
                    "type": "string",
                    "description": "Filter by category: ai, transform, extract, etc.",
                },
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
                "prompt": {
                    "type": "string",
                    "description": "Prompt to send to all models",
                },
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
                "system_prompt": {
                    "type": "string",
                    "description": "Optional system prompt",
                },
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
                "category": {
                    "type": "string",
                    "description": "Filter by category: llm, transform, agent, etc.",
                },
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
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 50)",
                    "default": 50,
                },
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
                "initial_inputs": {
                    "type": "object",
                    "description": "Default initial inputs",
                },
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
                "inputs": {
                    "type": "object",
                    "description": "Initial inputs for the chain",
                },
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
                "execution_id": {
                    "type": "string",
                    "description": "Execution ID from run_chain",
                },
            },
            "required": ["execution_id"],
        },
    ),
]
