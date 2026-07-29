"""
MCP Tool definitions for Research Agents.

Covers: research projects, plans, tasks, steps, notes, sources,
and sandboxed web/browser/document search tools.
"""

from __future__ import annotations

import mcp.types as types

TOOLS: list[types.Tool] = [
    # Research Agent tools
    types.Tool(
        name="fichero_research_create_project",
        description="Create a new research project for systematic investigation",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Project name",
                    "required": True,
                },
                "description": {"type": "string", "description": "Project description"},
                "created_by": {
                    "type": "string",
                    "description": "Creator: 'human' or agent ID",
                    "default": "human",
                },
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="fichero_research_list_projects",
        description="List research projects with optional status filter",
        inputSchema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status: active, paused, completed, archived",
                },
            },
        },
    ),
    types.Tool(
        name="fichero_research_get_project",
        description="Get a research project by ID",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID",
                    "required": True,
                },
            },
            "required": ["project_id"],
        },
    ),
    types.Tool(
        name="fichero_research_create_plan",
        description="Create a research plan within a project",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Parent project ID",
                    "required": True,
                },
                "name": {
                    "type": "string",
                    "description": "Plan name",
                    "required": True,
                },
                "description": {"type": "string", "description": "Plan description"},
                "order_index": {
                    "type": "integer",
                    "description": "Display order",
                    "default": 0,
                },
            },
            "required": ["project_id", "name"],
        },
    ),
    types.Tool(
        name="fichero_research_list_plans",
        description="List research plans for a project",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID",
                    "required": True,
                },
            },
            "required": ["project_id"],
        },
    ),
    types.Tool(
        name="fichero_research_create_task",
        description="Create a research task within a plan",
        inputSchema={
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "Parent plan ID",
                    "required": True,
                },
                "name": {
                    "type": "string",
                    "description": "Task name",
                    "required": True,
                },
                "description": {"type": "string", "description": "Task description"},
                "priority": {
                    "type": "integer",
                    "description": "Priority (higher = more important)",
                    "default": 0,
                },
                "assigned_to": {"type": "string", "description": "Agent ID to assign"},
            },
            "required": ["plan_id", "name"],
        },
    ),
    types.Tool(
        name="fichero_research_list_tasks",
        description="List research tasks for a plan",
        inputSchema={
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "description": "Plan ID",
                    "required": True,
                },
            },
            "required": ["plan_id"],
        },
    ),
    types.Tool(
        name="fichero_research_create_step",
        description="Create a research step (search action) within a task",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Parent task ID",
                    "required": True,
                },
                "tool": {
                    "type": "string",
                    "description": "Tool: web_search, browser_navigate, document_fetch, local_search",
                    "required": True,
                },
                "label": {
                    "type": "string",
                    "description": "Step label",
                    "required": True,
                },
                "description": {"type": "string", "description": "Step description"},
                "config": {
                    "type": "object",
                    "description": "Tool-specific config (e.g., {query: '...'})",
                },
                "order_index": {
                    "type": "integer",
                    "description": "Display order",
                    "default": 0,
                },
            },
            "required": ["task_id", "tool", "label"],
        },
    ),
    types.Tool(
        name="fichero_research_update_step",
        description="Update a research step with result or status",
        inputSchema={
            "type": "object",
            "properties": {
                "step_id": {
                    "type": "string",
                    "description": "Step ID",
                    "required": True,
                },
                "status": {
                    "type": "string",
                    "description": "Status: pending, completed, failed, skipped",
                },
                "result": {"type": "object", "description": "Step execution result"},
                "error": {"type": "string", "description": "Error message if failed"},
            },
            "required": ["step_id"],
        },
    ),
    types.Tool(
        name="fichero_research_web_search",
        description="Execute a sandboxed web search (DuckDuckGo HTML)",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                    "required": True,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return",
                    "default": 10,
                },
                "language": {
                    "type": "string",
                    "description": "Language code (e.g., 'en-us')",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Timeout in seconds",
                    "default": 30,
                },
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="fichero_research_browser_navigate",
        description="Navigate to a URL and extract content (sandboxed HTTP, no filesystem)",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to navigate to",
                    "required": True,
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Timeout in seconds",
                    "default": 30,
                },
            },
            "required": ["url"],
        },
    ),
    types.Tool(
        name="fichero_research_document_fetch",
        description="Fetch a document URL and optionally save as a Layer 1 Source",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Document URL",
                    "required": True,
                },
                "project_id": {
                    "type": "string",
                    "description": "Project ID for source attribution",
                },
                "create_as_source": {
                    "type": "boolean",
                    "description": "Save as Layer 1 Source",
                    "default": False,
                },
                "metadata": {"type": "object", "description": "Additional metadata"},
            },
            "required": ["url"],
        },
    ),
    types.Tool(
        name="fichero_research_create_note",
        description="Create a research observation note linked to project/task/step",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID",
                    "required": True,
                },
                "task_id": {"type": "string", "description": "Optional task ID"},
                "step_id": {"type": "string", "description": "Optional step ID"},
                "note_type": {
                    "type": "string",
                    "description": "Type: observation, finding, question, hypothesis, synthesis",
                    "default": "observation",
                },
                "content": {
                    "type": "string",
                    "description": "Note content",
                    "required": True,
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags",
                },
                "linked_source_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Linked source IDs",
                },
                "linked_claim_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Linked claim IDs",
                },
            },
            "required": ["project_id", "content"],
        },
    ),
    types.Tool(
        name="fichero_research_list_notes",
        description="List research notes for a project",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID",
                    "required": True,
                },
                "task_id": {"type": "string", "description": "Optional task ID filter"},
            },
            "required": ["project_id"],
        },
    ),
    types.Tool(
        name="fichero_research_add_source",
        description="Add a curated search source (URL, folder, database, API) to a project",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID",
                    "required": True,
                },
                "source_type": {
                    "type": "string",
                    "description": "Type: url, folder, database, api",
                    "required": True,
                },
                "label": {
                    "type": "string",
                    "description": "Source label",
                    "required": True,
                },
                "url": {"type": "string", "description": "URL (for url type)"},
                "path": {"type": "string", "description": "Path (for folder type)"},
                "description": {"type": "string", "description": "Source description"},
                "reliability": {
                    "type": "number",
                    "description": "Reliability 0.0-1.0",
                    "default": 0.5,
                },
            },
            "required": ["project_id", "source_type", "label"],
        },
    ),
]
