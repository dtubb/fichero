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
        description="List saved workflow definitions",
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
    # Knowledge Graph tools
    types.Tool(
        name="fichero_kg_list_claims",
        description="List knowledge claims with optional filters",
        inputSchema={
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Text search query"},
                "claim_type": {
                    "type": "string",
                    "description": "Filter by claim type: fact, analysis, interpretation, argument, historiography, theory",
                },
                "curation_state": {
                    "type": "string",
                    "description": "Filter by curation state: unreviewed, shortlisted, curated, rejected",
                },
                "epistemic_status": {
                    "type": "string",
                    "description": "Filter by epistemic status: tentative, confirmed, rejected",
                },
                "entity_id": {
                    "type": "string",
                    "description": "Filter by linked entity ID",
                },
                "source_language": {
                    "type": "string",
                    "description": "Filter by source language code (e.g., 'en', 'es')",
                },
                "source_type": {
                    "type": "string",
                    "description": "Filter by source type: document, claim, multiple, synthesis",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 200)",
                    "default": 200,
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
        name="fichero_kg_create_claim",
        description="Create a new knowledge claim",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Claim text (required)"},
                "source_document_id": {
                    "type": "string",
                    "description": "Primary source document ID",
                },
                "source_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional source document IDs for multi-source claims",
                },
                "source_page_labels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Page labels per source",
                },
                "source_languages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Languages per source (e.g., ['en', 'es'])",
                },
                "source_type": {
                    "type": "string",
                    "description": "Source type: document, claim, multiple, synthesis",
                    "default": "document",
                },
                "entity_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Linked entity IDs",
                },
                "claim_type": {
                    "type": "string",
                    "description": "Claim type: fact, analysis, interpretation, argument, historiography, theory",
                },
                "epistemic_status": {
                    "type": "string",
                    "description": "Epistemic status: tentative, confirmed, rejected",
                },
                "curation_state": {
                    "type": "string",
                    "description": "Curation state",
                    "default": "unreviewed",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence 0.0-1.0",
                    "default": 0.5,
                },
            },
            "required": ["text"],
        },
    ),
    types.Tool(
        name="fichero_kg_patch_claim",
        description="Update an existing knowledge claim",
        inputSchema={
            "type": "object",
            "properties": {
                "claim_id": {"type": "string", "description": "Claim ID to update"},
                "text": {"type": "string", "description": "New claim text"},
                "claim_type": {"type": "string", "description": "New claim type"},
                "epistemic_status": {
                    "type": "string",
                    "description": "New epistemic status",
                },
                "curation_state": {
                    "type": "string",
                    "description": "New curation state",
                },
                "confidence": {
                    "type": "number",
                    "description": "New confidence 0.0-1.0",
                },
                "entity_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New entity IDs",
                },
            },
            "required": ["claim_id"],
        },
    ),
    types.Tool(
        name="fichero_kg_list_entities",
        description="List knowledge graph entities with optional search",
        inputSchema={
            "type": "object",
            "properties": {
                "q": {
                    "type": "string",
                    "description": "Search query (matches canonical name or aliases)",
                },
                "entity_type": {
                    "type": "string",
                    "description": "Filter by type: person, location, organization, event, concept, other",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 50,
                },
            },
        },
    ),
    types.Tool(
        name="fichero_kg_upsert_entity",
        description="Create or update a knowledge graph entity",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Entity ID (omit to create new)",
                },
                "canonical_name": {
                    "type": "string",
                    "description": "Primary name for the entity",
                },
                "entity_type": {
                    "type": "string",
                    "description": "Entity type",
                    "default": "other",
                },
                "aliases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Alternative names",
                },
                "description": {"type": "string", "description": "Entity description"},
                "language": {"type": "string", "description": "Primary language code"},
            },
            "required": ["canonical_name"],
        },
    ),
    types.Tool(
        name="fichero_kg_embed_claims",
        description="Embed knowledge claims into LanceDB for semantic search. Run this before using semantic claim search.",
        inputSchema={
            "type": "object",
            "properties": {
                "claim_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific claim IDs to embed (omit to embed all)",
                },
            },
        },
    ),
    types.Tool(
        name="fichero_kg_semantic_search",
        description="Search knowledge claims semantically using vector similarity",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                    "required": True,
                },
                "claim_type": {"type": "string", "description": "Filter by claim type"},
                "curation_state": {
                    "type": "string",
                    "description": "Filter by curation state",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="fichero_kg_embed_entities",
        description="Embed knowledge graph entities into LanceDB for semantic search",
        inputSchema={
            "type": "object",
            "properties": {
                "entity_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific entity IDs to embed (omit to embed all)",
                },
            },
        },
    ),
    types.Tool(
        name="fichero_kg_semantic_entity_search",
        description="Search knowledge graph entities semantically",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query",
                    "required": True,
                },
                "entity_type": {
                    "type": "string",
                    "description": "Filter by entity type",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="fichero_kg_overview",
        description="Get knowledge graph overview statistics for claims, entities, and links",
        inputSchema={
            "type": "object",
            "properties": {
                "scope_type": {
                    "type": "string",
                    "description": "Scope filter: library, folder, document",
                },
                "target_id": {
                    "type": "string",
                    "description": "Target ID for scope filter",
                },
            },
        },
    ),
    # Knowledge Graph — Prediction tools
    types.Tool(
        name="fichero_kg_generate_heuristic_predictions",
        description="Generate heuristic link predictions for knowledge claims using embedding similarity",
        inputSchema={
            "type": "object",
            "properties": {
                "top_k": {
                    "type": "integer",
                    "description": "Number of top similar claims to consider per claim (default 10, max 100)",
                    "default": 10,
                },
                "entity_id": {
                    "type": "string",
                    "description": "Limit predictions to a specific entity ID",
                },
            },
        },
    ),
    types.Tool(
        name="fichero_kg_apply_predictions",
        description="Apply top-scoring predictions as knowledge claim links",
        inputSchema={
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "Prediction run ID to apply",
                    "required": True,
                },
            },
            "required": ["run_id"],
        },
    ),
    # Hermeneutics — Circle navigation tools
    types.Tool(
        name="fichero_hm_create_circle_state",
        description="Start a hermeneutic circle for navigating part-whole relationships in a claim",
        inputSchema={
            "type": "object",
            "properties": {
                "claim_id": {"type": "string", "description": "Claim ID to navigate"},
                "current_focus": {
                    "type": "string",
                    "description": "Initial focus: 'part' or 'whole'",
                    "required": True,
                },
                "focus_id": {
                    "type": "string",
                    "description": "ID of the initial focus element",
                },
                "focus_label": {
                    "type": "string",
                    "description": "Human-readable label for the focus",
                    "required": True,
                },
                "direction": {
                    "type": "string",
                    "description": "Navigation direction: whole_to_part or part_to_whole",
                    "required": True,
                },
                "metadata": {"type": "object", "description": "Additional metadata"},
            },
            "required": ["current_focus", "focus_label", "direction"],
        },
    ),
    types.Tool(
        name="fichero_hm_navigate_circle",
        description="Navigate one step in an active hermeneutic circle (part→whole or whole→part)",
        inputSchema={
            "type": "object",
            "properties": {
                "state_id": {
                    "type": "string",
                    "description": "Circle state ID to navigate",
                    "required": True,
                },
                "focus_id": {
                    "type": "string",
                    "description": "ID of the new focus element",
                    "required": True,
                },
                "focus_label": {
                    "type": "string",
                    "description": "Human-readable label for the new focus",
                    "required": True,
                },
                "direction": {
                    "type": "string",
                    "description": "Navigation direction: whole_to_part or part_to_whole",
                    "required": True,
                },
            },
            "required": ["state_id", "focus_id", "focus_label", "direction"],
        },
    ),
    # Hermeneutics tools
    types.Tool(
        name="fichero_hm_list_frameworks",
        description="List available interpretive frameworks for analyzing claims and documents",
        inputSchema={
            "type": "object",
            "properties": {
                "framework_type": {
                    "type": "string",
                    "description": "Filter by type: historical, disciplinary, thematic, methodological, theoretical, narrative",
                },
                "is_active": {
                    "type": "boolean",
                    "description": "Filter by active status",
                },
            },
        },
    ),
    types.Tool(
        name="fichero_hm_apply_framework",
        description="Apply an interpretive framework to a claim and record the interpretation",
        inputSchema={
            "type": "object",
            "properties": {
                "framework_id": {
                    "type": "string",
                    "description": "Framework ID to apply",
                    "required": True,
                },
                "claim_id": {"type": "string", "description": "Target claim ID"},
                "document_id": {
                    "type": "string",
                    "description": "Or target document ID",
                },
                "passage_text": {
                    "type": "string",
                    "description": "Or passage text directly",
                },
                "interpretation_text": {
                    "type": "string",
                    "description": "What the framework reveals about the target",
                    "required": True,
                },
                "act": {
                    "type": "string",
                    "description": "Interpretive act: reading, translating, contextualizing, synthesizing, critiquing, applying",
                    "default": "contextualizing",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence 0.0-1.0",
                    "default": 0.5,
                },
                "key_insights": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key insights from this interpretation",
                },
            },
            "required": ["framework_id", "interpretation_text"],
        },
    ),
    types.Tool(
        name="fichero_hm_find_patterns",
        description="Find recognized patterns across knowledge claims and entities",
        inputSchema={
            "type": "object",
            "properties": {
                "pattern_type": {
                    "type": "string",
                    "description": "Filter by pattern type: temporal, causal, structural, thematic",
                },
                "framework_id": {
                    "type": "string",
                    "description": "Filter by framework that recognized the pattern",
                },
                "status": {
                    "type": "string",
                    "description": "Filter by status: tentative, confirmed, superseded",
                },
                "entity_id": {
                    "type": "string",
                    "description": "Find patterns involving an entity",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 50,
                },
            },
        },
    ),
    types.Tool(
        name="fichero_hm_suggest_interpretations",
        description="Get AI-suggested interpretations for claims using available frameworks",
        inputSchema={
            "type": "object",
            "properties": {
                "claim_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Claim IDs to interpret",
                    "required": True,
                },
                "framework_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific frameworks to use (omit for all active)",
                },
                "num_suggestions": {
                    "type": "integer",
                    "description": "Number of suggestions (1-10)",
                    "default": 3,
                },
            },
            "required": ["claim_ids"],
        },
    ),
    # Mind Palace tools
    types.Tool(
        name="fichero_mp_create_room",
        description="Create a new Mind Palace workspace room",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Room name",
                    "required": True,
                },
                "description": {"type": "string", "description": "Room description"},
                "room_type": {
                    "type": "string",
                    "description": "Type: research, synthesis, presentation",
                    "default": "research",
                },
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="fichero_mp_list_rooms",
        description="List Mind Palace rooms",
        inputSchema={
            "type": "object",
            "properties": {
                "room_type": {"type": "string", "description": "Filter by room type"},
                "owner_id": {"type": "string", "description": "Filter by owner"},
            },
        },
    ),
    types.Tool(
        name="fichero_mp_place_node",
        description="Place a spatial node (source, claim, note, entity) in a room",
        inputSchema={
            "type": "object",
            "properties": {
                "room_id": {
                    "type": "string",
                    "description": "Target room ID",
                    "required": True,
                },
                "node_type": {
                    "type": "string",
                    "description": "Node type: source, claim, note, entity, transcription",
                    "required": True,
                },
                "source_id": {
                    "type": "string",
                    "description": "ID of the underlying item",
                },
                "label": {"type": "string", "description": "Display label"},
                "position_x": {
                    "type": "number",
                    "description": "X position",
                    "default": 0,
                },
                "position_y": {
                    "type": "number",
                    "description": "Y position",
                    "default": 0,
                },
                "position_z": {
                    "type": "number",
                    "description": "Z position",
                    "default": 0,
                },
            },
            "required": ["room_id", "node_type"],
        },
    ),
    types.Tool(
        name="fichero_mp_move_node",
        description="Move a spatial node to a new position in a room",
        inputSchema={
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "Node ID to move",
                    "required": True,
                },
                "position_x": {
                    "type": "number",
                    "description": "New X position",
                    "required": True,
                },
                "position_y": {
                    "type": "number",
                    "description": "New Y position",
                    "required": True,
                },
                "position_z": {
                    "type": "number",
                    "description": "New Z position",
                    "required": True,
                },
            },
            "required": ["node_id", "position_x", "position_y", "position_z"],
        },
    ),
    types.Tool(
        name="fichero_mp_create_connection",
        description="Create a visual connection between two nodes in a room",
        inputSchema={
            "type": "object",
            "properties": {
                "room_id": {
                    "type": "string",
                    "description": "Room ID",
                    "required": True,
                },
                "source_node_id": {
                    "type": "string",
                    "description": "Source node ID",
                    "required": True,
                },
                "target_node_id": {
                    "type": "string",
                    "description": "Target node ID",
                    "required": True,
                },
                "connection_type": {
                    "type": "string",
                    "description": "Connection type: evidentiary, semantic, ontological, hermeneutic, user_drawn",
                    "required": True,
                },
                "link_subtype": {
                    "type": "string",
                    "description": "Link subtype: supports, contradicts, interprets, etc.",
                },
            },
            "required": [
                "room_id",
                "source_node_id",
                "target_node_id",
                "connection_type",
            ],
        },
    ),
    types.Tool(
        name="fichero_mp_focus_node",
        description="Set or clear focus on a specific node in a room",
        inputSchema={
            "type": "object",
            "properties": {
                "room_id": {
                    "type": "string",
                    "description": "Room ID",
                    "required": True,
                },
                "node_id": {
                    "type": "string",
                    "description": "Node ID to focus on (omit to clear focus)",
                },
            },
            "required": ["room_id"],
        },
    ),
    types.Tool(
        name="fichero_mp_create_note",
        description="Create a first-class text note in Mind Palace",
        inputSchema={
            "type": "object",
            "properties": {
                "room_id": {"type": "string", "description": "Room ID"},
                "content": {
                    "type": "string",
                    "description": "Note content",
                    "required": True,
                },
                "note_type": {
                    "type": "string",
                    "description": "Note type: user, ai_workspace, ai_hypothesis, ai_summary, ai_relation, shared",
                    "default": "user",
                },
                "author_id": {
                    "type": "string",
                    "description": "Author ID",
                    "default": "user",
                },
                "linked_claim_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Linked claim IDs",
                },
                "linked_source_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Linked source IDs",
                },
            },
            "required": ["content"],
        },
    ),
    types.Tool(
        name="fichero_mp_suggest_arrangement",
        description="Get AI-suggested positions for nodes based on an arrangement strategy",
        inputSchema={
            "type": "object",
            "properties": {
                "room_id": {
                    "type": "string",
                    "description": "Room ID",
                    "required": True,
                },
                "node_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Node IDs to arrange",
                    "required": True,
                },
                "arrangement_type": {
                    "type": "string",
                    "description": "Strategy: semantic, chronological, thematic",
                    "default": "semantic",
                },
            },
            "required": ["room_id", "node_ids"],
        },
    ),
    types.Tool(
        name="fichero_mp_get_scene",
        description="Get a summary of a Mind Palace room scene (node count, connection count, etc.)",
        inputSchema={
            "type": "object",
            "properties": {
                "room_id": {
                    "type": "string",
                    "description": "Room ID",
                    "required": True,
                },
            },
            "required": ["room_id"],
        },
    ),
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
