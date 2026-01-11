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

import uuid
from enum import Enum
from typing import TypedDict, Any, Literal
from pydantic import BaseModel, Field, field_validator


def _new_id() -> str:
    """Generate a new unique ID."""
    return uuid.uuid4().hex


# =============================================================================
# Port and Connection Types
# =============================================================================

class DataType(str, Enum):
    """Data types for port connections."""
    ANY = "any"           # Any data type
    FILES = "files"       # List of file paths
    FILE = "file"         # Single file path
    TEXT = "text"         # String text
    JSON = "json"         # JSON object/dict
    ARRAY = "array"       # List/array
    IMAGE = "image"       # Image file or data
    NUMBER = "number"     # Numeric value
    BOOLEAN = "boolean"   # True/False


class PortDef(BaseModel):
    """Definition of an input or output port on a node.

    Ports are the connection points where edges attach.
    Each port has a data type for validation.
    """
    id: str = Field(..., description="Unique port identifier within the node")
    name: str = Field(..., description="Display name for the port")
    port_type: Literal["input", "output"] = Field(..., description="Whether this is an input or output port")
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
    transform: str | None = Field(default=None, description="Optional transform pipe (e.g., '| join:\", \"')")


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
    json_schema: dict[str, Any] = Field(..., description="JSON Schema definition", alias="schema")
    description: str = Field(default="", description="Description for LLM prompt context")

    model_config = {"populate_by_name": True}


# =============================================================================
# Execution State
# =============================================================================

class State(TypedDict):
    """Workflow execution state passed between nodes.

    This is the shared state that flows through the LangGraph.
    Each node reads from and writes to this state.
    """
    # Execution metadata
    task_id: str                    # Unique execution ID
    workflow_id: str                # Workflow definition ID

    # Input/Output
    inputs: dict[str, Any]          # Initial inputs to workflow
    outputs: dict[str, Any]         # Node outputs (keyed by node_id)

    # Execution tracking
    current_node: str               # Current node being executed
    completed_nodes: list[str]      # Nodes that have completed
    error: str | None               # Error message if failed

    # File tracking
    input_files: list[str]          # Input file paths
    output_files: list[str]         # Generated output file paths


# =============================================================================
# Workflow Definition
# =============================================================================

class NodeDef(BaseModel):
    """Definition of a single node in the workflow graph.

    Nodes represent tools/operations that process data.
    Each node has input and output ports for visual edge connections.

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

    # Port definitions (populated from tool registry, can be customized)
    input_ports: list[PortDef] = Field(
        default_factory=list,
        description="Input connection ports"
    )
    output_ports: list[PortDef] = Field(
        default_factory=list,
        description="Output connection ports"
    )

    # Input mapping - reference any previous node's output
    input_mappings: list[InputMapping] = Field(
        default_factory=list,
        description="Maps input ports to data sources from previous nodes"
    )

    # Input values (can be literal values or path references)
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Input values for the tool (supports path resolution)"
    )

    # Static config (passed directly to tool, not resolved)
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Static tool configuration (not resolved)"
    )

    # Structured output schema for LLM nodes
    output_schema: OutputSchema | None = Field(
        default=None,
        description="JSON Schema for structured LLM output"
    )

    # UI positioning (for node editor) - float for smooth dragging
    position_x: float = 0.0
    position_y: float = 0.0

    # Optional metadata
    label: str | None = None        # Display label (defaults to tool name)
    description: str | None = None  # Node description
    enabled: bool = True            # Can be disabled without removing

    # Validators to handle null values from Swift/JSON
    @field_validator('config', 'inputs', mode='before')
    @classmethod
    def convert_none_to_empty_dict(cls, v):
        """Convert null to empty dict for dict fields."""
        return v if v is not None else {}

    @field_validator('input_mappings', 'input_ports', 'output_ports', mode='before')
    @classmethod
    def convert_none_to_empty_list(cls, v):
        """Convert null to empty list for list fields."""
        return v if v is not None else []


class EdgeDef(BaseModel):
    """Definition of an edge connecting two nodes via their ports.

    Edges define data flow between nodes. Each edge connects
    an output port on the source node to an input port on the target node.
    """
    id: str = Field(default="", description="Unique edge identifier (auto-generated if empty)")
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")

    # Port connections (specific ports on each node)
    source_port: str = Field(default="output", description="Output port ID on source node")
    target_port: str = Field(default="input", description="Input port ID on target node")

    # Conditional routing (for IF/Switch nodes)
    condition: str | None = Field(
        default=None,
        description="Condition expression (e.g., '$.nodes.classify.category == \"invoice\"')"
    )

    # Visual styling
    animated: bool = False          # Show animated flow
    label: str | None = None        # Label on edge


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

    # Execution settings
    timeout_seconds: int = 300      # Max execution time
    max_retries: int = 3            # Retries per node on failure

    # Metadata
    version: str = "1.0"
    created_at: str | None = None
    updated_at: str | None = None

    def get_entry_nodes(self) -> list[str]:
        """Find nodes with no incoming edges (entry points)."""
        targets = {e.target for e in self.edges}
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
    category: str = "general"       # vision, transform, convert, llm, logic, source, sink

    # Visual styling for node editor
    icon: str = "gearshape"         # SF Symbol name
    color: str = "gray"             # Color name (blue, green, purple, etc.)

    # Port definitions - copied to nodes when created
    input_ports: list[PortDef] = Field(
        default_factory=list,
        description="Default input ports for nodes using this tool"
    )
    output_ports: list[PortDef] = Field(
        default_factory=list,
        description="Default output ports for nodes using this tool"
    )

    # Config schema (JSON Schema for tool-specific configuration)
    config_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for tool configuration options"
    )

    # Output schema template (for LLM tools that support structured output)
    default_output_schema: dict[str, Any] | None = Field(
        default=None,
        description="Default structured output schema (can be customized per node)"
    )

    # Capabilities
    uses_llm: bool = False          # Requires LLM provider/model selection
    supports_batch: bool = False    # Can process multiple files in parallel
    supports_streaming: bool = False # Can stream progress updates
    supports_structured_output: bool = False  # Can use JSON Schema output

    # Sort order for UI
    sort_order: int = 100           # Lower = higher in list
