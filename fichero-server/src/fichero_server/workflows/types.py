"""
Workflow Type Definitions

Defines the data structures used in workflow definitions and execution.

Key concepts:
- PortDef: Input/output connection points on nodes
- InputMapping: Flexible references to any previous node's output
- OutputSchema: JSON Schema for structured LLM outputs
- NodeDef: A node in the workflow graph with ports
- EdgeDef: A connection between node ports
- WorkflowDef: Complete workflow definition
"""

from __future__ import annotations

import json
import uuid
from enum import Enum
from typing import TypedDict, Any, Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_STATE_OUTPUT_MAX_BYTES = 8 * 1024 * 1024


def compact_output_for_state(value: Any) -> Any:
    """Drop redundant per-file payloads before they accumulate in State.

    Downstream nodes read the combined ``text`` / ``records`` outputs, not the
    full per-file ``texts`` / ``results`` / ``values`` arrays. Keep counts so
    callers can still report fan-out cardinality without retaining every branch
    payload in memory or checkpoints.
    """
    if not isinstance(value, dict):
        return value

    compact = dict(value)
    if isinstance(compact.get("texts"), list):
        compact["text_count"] = len(compact["texts"])
        compact.pop("texts", None)
    if isinstance(compact.get("results"), list):
        compact["result_count"] = len(compact["results"])
        compact.pop("results", None)
    if isinstance(compact.get("values"), list):
        compact["value_count"] = len(compact["values"])
        compact.pop("values", None)

    size = len(json.dumps(compact, ensure_ascii=False))
    if size > _STATE_OUTPUT_MAX_BYTES:
        raise ValueError(
            "Workflow State output exceeded the capped serialized size "
            f"({size} > {_STATE_OUTPUT_MAX_BYTES} bytes)"
        )
    return compact


def _merge_parallel_results(
    existing: dict[str, list[Any]] | None,
    new: dict[str, list[Any]] | None,
) -> dict[str, list[Any]]:
    """Reducer for parallel_results - merges results from parallel branches.

    Each parallel branch returns {node_id: [result]} and this reducer
    combines them into {node_id: [result1, result2, ...]}.
    """
    if existing is None:
        existing = {}
    if new is None:
        return existing

    result = dict(existing)
    for node_id, results in new.items():
        if node_id not in result:
            result[node_id] = []
        result[node_id].extend(results)
    return result


def _merge_outputs(
    existing: dict[str, Any] | None,
    new: dict[str, Any] | None,
) -> dict[str, Any]:
    """Reducer for outputs - merges node outputs from concurrent branches.

    Each node returns {node_id: result} and this reducer combines them.
    """
    if existing is None:
        existing = {}
    if new is None:
        return existing
    result = dict(existing)
    result.update(
        {
            node_id: compact_output_for_state(node_output)
            for node_id, node_output in new.items()
        }
    )
    return result


def _merge_completed_nodes(
    existing: list[str] | None,
    new: list[str] | None,
) -> list[str]:
    """Reducer for completed_nodes - merges lists from concurrent branches."""
    if existing is None:
        existing = []
    if new is None:
        return existing
    # Union while preserving order
    seen = set(existing)
    result = list(existing)
    for item in new:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _last_value(existing: str | None, new: str | None) -> str:
    """Reducer for current_node - takes the last value in parallel execution.

    When multiple parallel nodes update current_node simultaneously,
    we just keep the last one (order doesn't matter for tracking).
    """
    if new is not None:
        return new
    return existing or ""


def _merge_output_files(
    existing: list[str] | None,
    new: list[str] | None,
) -> list[str]:
    """Reducer for output_files - merges file lists from concurrent branches."""
    if existing is None:
        existing = []
    if new is None:
        return existing
    # Union while preserving order
    seen = set(existing)
    result = list(existing)
    for item in new:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _merge_error(
    existing: str | None,
    new: str | None,
) -> str | None:
    """Reducer for error field during concurrent execution.

    Multiple nodes may emit an `error` key in the same LangGraph step.
    Keep the newest non-empty error; otherwise preserve existing value.
    """
    if new:
        return new
    return existing


def _new_id() -> str:
    """Generate a new unique ID."""
    return uuid.uuid4().hex


# =============================================================================
# Port and Connection Types
# =============================================================================


class DataType(str, Enum):
    """Data types for port connections."""

    ANY = "any"  # Any data type
    FILES = "files"  # List of file paths
    FILE = "file"  # Single file path
    TEXT = "text"  # String text
    JSON = "json"  # JSON object/dict
    ARRAY = "array"  # List/array
    IMAGE = "image"  # Image file or data
    NUMBER = "number"  # Numeric value
    BOOLEAN = "boolean"  # True/False


class PortDef(BaseModel):
    """Definition of an input or output port on a node.

    Ports are the connection points where edges attach.
    Each port has a data type for validation.
    """

    id: str = Field(..., description="Unique port identifier within the node")
    name: str = Field(..., description="Display name for the port")
    port_type: Literal["input", "output"] = Field(
        ..., description="Whether this is an input or output port"
    )
    data_type: DataType = Field(default=DataType.ANY, description="Expected data type")
    required: bool = Field(default=True, description="Whether this input is required")
    description: str = ""
    default: Any = None  # Default value for optional inputs


class InputMapping(BaseModel):
    """Maps a node input port to a data source.

    Allows referencing output from ANY previous node, not just
    the immediately preceding one in the graph.

    Examples:
        source_path="$.nodes.transcribe.text"
        source_path="$.nodes.entities.people | join:', '"
        source_path="$.inputs.language"
        source_path="$.files"
    """

    port_id: str = Field(..., description="Target input port ID on this node")
    source_path: str = Field(..., description="Path expression to data source")
    transform: str = Field(
        default="",
        description="Optional transform pipe (e.g., '| join:\", \"'), empty if none",
    )


class OutputSchema(BaseModel):
    """JSON Schema for structured output from LLM nodes.

    When specified, the LLM will be instructed to return
    data matching this schema exactly (using structured output mode).

    Example for named entity extraction:
    {
        "type": "object",
        "properties": {
            "people": {"type": "array", "items": {"type": "string"}},
            "organizations": {"type": "array", "items": {"type": "string"}},
            "dates": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["people", "organizations", "dates"]
    }
    """

    json_schema: dict[str, Any] = Field(
        ..., description="JSON Schema definition", alias="schema"
    )
    description: str = Field(
        default="", description="Description for LLM prompt context"
    )

    model_config = ConfigDict(populate_by_name=True)


# =============================================================================
# Execution State
# =============================================================================


class State(TypedDict):
    """Workflow execution state passed between nodes.

    This is the shared state that flows through the LangGraph.
    Each node reads from and writes to this state.
    """

    # Execution metadata
    task_id: str  # Unique execution ID
    workflow_id: str  # Workflow definition ID
    parent_task_id: str  # Parent run id when this is a child workflow
    parent_workflow_id: str  # Parent workflow id when this is a child workflow
    parent_node_id: str  # Parent sub_workflow node id
    lineage_path: str  # Ordered parent/node/child path for nested runs
    sub_workflow_depth: int  # Nested sub-workflow depth
    sub_workflows: dict[str, Any]  # Test/runtime injection map for child workflows

    # Library context (required for source tools)
    library_path: str  # Path to .fichero library package

    # UI selection — document IDs selected when the user clicked Run
    selected_doc_ids: list[str]

    # Input/Output
    inputs: dict[str, Any]  # Initial inputs to workflow
    outputs: Annotated[
        dict[str, Any], _merge_outputs
    ]  # Node outputs (keyed by node_id)

    # Execution tracking
    current_node: Annotated[str, _last_value]  # Current node being executed (uses reducer for parallel)
    completed_nodes: Annotated[list[str], _merge_completed_nodes]  # Nodes that have completed
    error: Annotated[str | None, _merge_error]  # Error message if failed

    # File tracking
    input_files: list[str]  # Input file paths
    # The source node's RESOLVED file list, published at run level (#4283/#4379).
    # This key was read in three places — `_detect_empty_text_output`, the
    # builder's per-file branch, and the runner — and written by the fan-out
    # `Send` sub-states, but it was never a declared channel, so LangGraph
    # dropped every top-level write to it and the terminal state never carried
    # it. The run-level empty-output guard therefore short-circuited to "not
    # empty" on every workflow whose source fans out per DOCUMENT rather than
    # per file, which is every entity-extraction preset: a NER run that
    # extracted nothing reported a green `completed`. Declaring the channel is
    # what makes the existing contract actually hold.
    # `_last_value` (not a merge): the source node resolves this once, and a
    # parallel branch receives its own single-file view through `Send` rather
    # than writing back.
    files: Annotated[list[str], _last_value]
    output_files: Annotated[
        list[str], _merge_output_files
    ]  # Generated output file paths

    # Parallel execution tracking (for Send API fan-out)
    # Annotated with reducer to merge results from concurrent parallel branches
    parallel_results: Annotated[
        dict[str, list[Any]], _merge_parallel_results
    ]  # node_id -> list of results
    parallel_index: int  # Current file index when in parallel branch
    parallel_total: int  # Total files being processed in parallel
    parallel_file: str  # Current file path in parallel branch
    parallel_document: (
        dict[str, Any] | None
    )  # Current document metadata in parallel branch


# =============================================================================
# Workflow Definition
# =============================================================================


class NodeDef(BaseModel):
    """Definition of a single node in the workflow graph.

    Nodes represent tools/operations that process data.

    IMPORTANT: Ports should NOT be stored with nodes. They are defined in the
    tool registry and should be fetched using `enrich_node_with_ports()`.
    The port fields here are kept for backward compatibility and API responses
    but should be empty when persisting to database.

    Input Mapping:
        The `input_mappings` list allows referencing ANY previous node's output,
        not just the immediately preceding one.

        Path syntax:
        - $.nodes.{node_id}.{key}  - Output from another node
        - $.inputs.{key}           - Initial workflow input
        - $.files                  - All input files
        - $.files[n]               - Specific file by index
        - $.config.{key}           - Workflow-level config

        Transform pipes:
        - $.nodes.x.text | upper
        - $.nodes.x.items | join:", "
        - $.nodes.x.data | json_extract:"$.name"

    Structured Output:
        For LLM nodes, `output_schema` defines the exact JSON structure
        the LLM must return (enforced via structured output mode).
    """

    id: str = Field(default_factory=_new_id, description="Unique node identifier")
    tool: str = Field(..., description="Tool function name from registry")

    # Port definitions - DEPRECATED for storage
    # These are populated from the tool registry at runtime for API responses.
    # Do NOT store ports in the database - use enrich_node_with_ports() instead.
    input_ports: list[PortDef] = Field(
        default_factory=list,
        description="Input connection ports (populated from registry, not stored)",
    )
    output_ports: list[PortDef] = Field(
        default_factory=list,
        description="Output connection ports (populated from registry, not stored)",
    )

    # Input mapping - reference any previous node's output
    input_mappings: list[InputMapping] = Field(
        default_factory=list,
        description="Maps input ports to data sources from previous nodes",
    )

    # Input values (can be literal values or path references)
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Input values for the tool (supports path resolution)",
    )

    # Static config (passed directly to tool, not resolved)
    config: dict[str, Any] = Field(
        default_factory=dict, description="Static tool configuration (not resolved)"
    )

    # Structured output schema for LLM nodes
    output_schema: OutputSchema | None = Field(
        default=None, description="JSON Schema for structured LLM output"
    )

    # UI positioning (for node editor) - float for smooth dragging
    position_x: float = 0.0
    position_y: float = 0.0

    # Optional metadata
    label: str = ""  # Display label (defaults to tool name if empty)
    description: str = ""  # Node description
    enabled: bool = True  # Can be disabled without removing

    # Per-node LLM configuration (overrides workflow defaults)
    provider_name: str = ""  # e.g., "openai", "anthropic" (empty for default)
    model_name: str = (
        ""  # e.g., "gpt-4o", "claude-3-5-sonnet-20241022" (empty for default)
    )
    uses_llm: bool = False  # Whether this node uses an LLM

    # Validators to handle null values from Swift/JSON
    @field_validator("config", "inputs", mode="before")
    @classmethod
    def convert_none_to_empty_dict(cls, v):
        """Convert null to empty dict for dict fields."""
        return v if v is not None else {}

    @field_validator("input_mappings", "input_ports", "output_ports", mode="before")
    @classmethod
    def convert_none_to_empty_list(cls, v):
        """Convert null to empty list for list fields."""
        return v if v is not None else []

    @field_validator(
        "label",
        "description",
        "provider_name",
        "model_name",
        mode="before",
    )
    @classmethod
    def convert_none_to_empty_string(cls, v):
        """Convert null to empty string for string fields.

        Swift's OpenAPI client serializes every omitted optional argument as
        a JSON null, so a routine "set this node's tool" save arrives with
        provider_name=null + model_name=null even when the user has them
        configured. Without this validator, NodeDef construction either
        rejects the save (Pydantic strict) or silently sets the field to
        the string "None" (Pydantic lax) — both manifest as #780 (model
        selection lost on save/restart).
        """
        return v if v is not None else ""

    def model_dump_for_storage(self) -> dict:
        """Get a minimal dict for database storage (excludes ports).

        Ports should not be stored - they come from the tool registry.
        Use this method when saving workflows to the database.
        """
        data = self.model_dump()
        # Remove ports - they'll be enriched from registry when loading
        data.pop("input_ports", None)
        data.pop("output_ports", None)
        return data


class EdgeDef(BaseModel):
    """Definition of an edge connecting two nodes via their ports.

    Edges define data flow between nodes. Each edge connects
    an output port on the source node to an input port on the target node.
    """

    id: str = Field(
        default="", description="Unique edge identifier (auto-generated if empty)"
    )
    source: str = Field(..., description="Source node ID")
    target: str = Field(
        default="",
        description="Target node ID (empty for route_map edges that fan to multiple targets)",
    )

    # Port connections (specific ports on each node)
    source_port: str = Field(
        default="output", description="Output port ID on source node"
    )
    target_port: str = Field(
        default="input", description="Input port ID on target node"
    )

    # Conditional routing (for IF/Switch nodes)
    condition: str | None = Field(
        default=None,
        description="Condition expression (e.g., '$.nodes.classify.category == \"invoice\"'), empty for unconditional",
    )

    # Multi-way routing (mutually exclusive with condition)
    route_key: str | None = Field(
        default=None,
        description="Path expression whose resolved value is used to select a route (e.g. '$.nodes.classify.script_type')",
    )
    route_map: dict[str, str] | None = Field(
        default=None,
        description="Maps resolved route_key values to target node IDs (e.g. {'typescript': 'transcribe-ts'})",
    )
    route_files_source: str | None = Field(
        default=None,
        description=(
            "Explicit SOURCE node id whose files drive per-file fan-out for "
            "route_map targets (#4324). When set, the builder uses this node "
            "instead of inferring the files source by walking one hop "
            "upstream of the routing node."
        ),
    )

    # Visual styling
    animated: bool = False  # Show animated flow
    label: str | None = None  # Label on edge (None for none)

    @model_validator(mode="before")
    @classmethod
    def _normalize_edge_field_drift(cls, data: Any) -> Any:
        """Normalize legacy/alternate edge field spellings onto the canonical
        names BEFORE field validation runs.

        The canonical edge fields are ``source`` / ``target`` (node IDs) and
        ``source_port`` / ``target_port`` (port IDs). Older persisted workflows
        and some payloads used ``source_node_id`` / ``target_node_id`` and
        ``source_port_id`` / ``target_port_id``. Accept either spelling on input
        and collapse it onto the canonical field so a single shape is stored and
        read everywhere (#2537). The canonical key always wins when both are
        present; the ``*_id`` alias is consumed so it can't linger as stray
        extra data.
        """
        if not isinstance(data, dict):
            return data
        data = dict(data)  # never mutate the caller's dict
        for canonical, legacy in (
            ("source", "source_node_id"),
            ("target", "target_node_id"),
            ("source_port", "source_port_id"),
            ("target_port", "target_port_id"),
        ):
            if legacy in data:
                legacy_value = data.pop(legacy)
                # Only adopt the legacy value when the canonical field is absent
                # or empty — the canonical spelling is authoritative.
                if not data.get(canonical):
                    data[canonical] = legacy_value
        return data

    @model_validator(mode="after")
    def _validate_endpoints(self) -> "EdgeDef":
        if not self.source:
            raise ValueError("EdgeDef.source is required")
        if self.route_map is not None:
            if not self.route_key:
                raise ValueError("EdgeDef.route_key is required for route_map edges")
            if not self.route_map:
                raise ValueError("EdgeDef.route_map cannot be empty")
            return self
        if not self.target:
            raise ValueError("EdgeDef.target is required for non-route_map edges")
        return self


class WorkflowDef(BaseModel):
    """Complete workflow definition.

    This is the JSON-serializable representation of a workflow
    that can be saved, loaded, and executed.
    """

    id: str = Field(default_factory=_new_id, description="Unique workflow identifier")
    name: str = Field(..., description="Display name")
    description: str = ""

    # Graph structure
    nodes: list[NodeDef] = Field(default_factory=list)
    edges: list[EdgeDef] = Field(default_factory=list)

    # LLM defaults for this workflow
    provider: str = "openai"
    model: str = "gpt-4o"

    # Batch input source: "collection" (from a named collection) or
    # "current_selection" (whatever the user selected in the library).
    input_source: Literal["collection", "current_selection"] = "collection"

    # Execution settings
    timeout_seconds: int = 300  # Max execution time
    max_retries: int = 3  # Retries per node on failure

    # Metadata
    version: str = "1.0"
    created_at: str | None = None
    updated_at: str | None = None
    folder_path: str = "/"  # Folder organization path
    sort_order: int = 0  # Sort order within folder

    @field_validator("version", mode="before")
    @classmethod
    def coerce_version_to_str(cls, v):
        """Shipped preset JSON carries ``version: 1`` (int); the field is str.

        Anything that ``model_validate``s a preset dict directly — the
        sub-workflow JSON fallback does exactly that — threw ValidationError
        on every such preset (#4477 side-finding). Coerce, don't reject: the
        value is metadata, and a hard error here turns a shipped preset into
        an unresolvable child ref.
        """
        if isinstance(v, (int, float)):
            return str(v)
        return v

    @field_validator("description", mode="before")
    @classmethod
    def convert_none_to_empty_description(cls, v):
        """Convert null workflow descriptions to empty string."""
        return v if v is not None else ""

    def get_entry_nodes(self) -> list[str]:
        """Find nodes with no incoming edges (entry points)."""
        targets = {e.target for e in self.edges if e.target}
        for e in self.edges:
            if e.route_map:
                targets.update(e.route_map.values())
        return [n.id for n in self.nodes if n.id not in targets]

    def get_exit_nodes(self) -> list[str]:
        """Find nodes with no outgoing edges (exit points)."""
        sources = {e.source for e in self.edges}
        return [n.id for n in self.nodes if n.id not in sources]

    def get_node(self, node_id: str) -> NodeDef | None:
        """Get node by ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None


# =============================================================================
# Tool Definition
# =============================================================================


class ToolDef(BaseModel):
    """Metadata about a registered tool.

    Used by the UI to display available tools and their parameters.
    When a node is created from this tool, the ports are copied to the node.
    """

    name: str = Field(..., description="Tool function name")
    display_name: str = Field(..., description="Human-readable name")
    description: str = ""
    category: str = "general"  # vision, transform, convert, llm, logic, source, sink

    # Visual styling for node editor
    icon: str = "gearshape"  # SF Symbol name
    color: str = "gray"  # Color name (blue, green, purple, etc.)

    # Port definitions - copied to nodes when created
    input_ports: list[PortDef] = Field(
        default_factory=list,
        description="Default input ports for nodes using this tool",
    )
    output_ports: list[PortDef] = Field(
        default_factory=list,
        description="Default output ports for nodes using this tool",
    )

    # Config schema (JSON Schema for tool-specific configuration)
    config_schema: dict[str, Any] = Field(
        default_factory=dict, description="JSON Schema for tool configuration options"
    )

    # Config defaults (actual default values for new nodes)
    config_defaults: dict[str, Any] = Field(
        default_factory=dict,
        description="Default config values to use when creating a new node",
    )

    # Output schema template (for LLM tools that support structured output)
    default_output_schema: dict[str, Any] | None = Field(
        default=None,
        description="Default structured output schema (can be customized per node)",
    )

    # Default prompt for LLM tools (shown in UI, user can customize)
    default_prompt: str | None = Field(
        default=None, description="Default prompt template for LLM tools"
    )

    # Callable to build dynamic prompt based on config
    # This is not serialized - it's used at runtime
    prompt_builder: Any | None = Field(
        default=None,
        exclude=True,
        description="Function to build prompt from config: (config: dict) -> str",
    )

    # Capabilities
    uses_llm: bool = False  # Requires LLM provider/model selection
    supports_batch: bool = False  # Can process multiple files in parallel
    supports_streaming: bool = False  # Can stream progress updates
    supports_structured_output: bool = False  # Can use JSON Schema output

    # Hard requirement, not a preference (#4345): this tool PARSES the model's
    # answer, so a recognition-only model (Apple Vision OCR returns page text
    # and ignores the prompt) can never satisfy it. Preflight refuses such a
    # node before the run starts instead of failing mid-run on a JSON parse.
    requires_generative_model: bool = False

    # Sort order for UI
    sort_order: int = 100  # Lower = higher in list

    # Trust signal: has this tool been validated end-to-end? Defaults to False
    # so every tool reads as UNTESTED unless explicitly marked. Only the HTR
    # transcription chain is tested=True today.
    tested: bool = False

    def get_prompt(self, config: dict[str, Any] | None = None) -> str | None:
        """Get the prompt for this tool, optionally customized by config.

        If prompt_builder is set, uses it to build a dynamic prompt.
        Otherwise returns default_prompt.
        """
        if self.prompt_builder and callable(self.prompt_builder):
            try:
                return self.prompt_builder(config or {})
            except Exception:
                pass
        return self.default_prompt
