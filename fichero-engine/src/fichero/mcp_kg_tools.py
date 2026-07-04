"""
MCP Tool definitions for Knowledge Graph and Hermeneutics.

Covers: claims, entities, semantic search, predictions, hermeneutic circle
navigation, and interpretive frameworks.
"""

from __future__ import annotations

import mcp.types as types

TOOLS: list[types.Tool] = [
    # Knowledge Graph — Claims and entities
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
]
