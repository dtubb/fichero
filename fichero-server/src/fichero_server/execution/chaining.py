"""
Workflow Chaining System

Allows workflows to be chained together, with the output of one workflow
becoming the input of the next.

A chain's steps run through the one runner, in list order (`api/routes/workflow/chains.py`); the old executor with its
own graph semantics is retired (`activity.legacy-chain-retired`, #4949). This module keeps the chain's types and store.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from fichero_server.core.timeutil import utc_now
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field



# =============================================================================
# Chain Definition Models
# =============================================================================


class ChainStepCondition(BaseModel):
    """Conditional execution for a chain step.

    Allows branching based on the output of the previous workflow.
    """

    expression: str = Field(
        ...,
        description="Python expression to evaluate (e.g., '$.outputs.category == \"invoice\"')",
    )
    true_step: str | None = Field(
        default=None,
        description="Step ID to execute if condition is true (None = continue to next)",
    )
    false_step: str | None = Field(
        default=None,
        description="Step ID to execute if condition is false (None = skip to end)",
    )


class OutputMapping(BaseModel):
    """Maps output from one workflow to input of the next.

    Supports path expressions like:
    - $.outputs.node_id.key  - Specific node output
    - $.outputs              - All outputs
    - $.files                - Output files from previous workflow
    """

    source_path: str = Field(
        ..., description="Path expression for source data from previous workflow"
    )
    target_key: str = Field(..., description="Input key name in the next workflow")
    transform: str | None = Field(
        default=None,
        description="Optional transformation (e.g., 'json_extract:$.name')",
    )


class ChainStep(BaseModel):
    """A single step in a workflow chain."""

    id: str = Field(..., description="Unique step identifier")
    workflow_id: str = Field(..., description="ID of workflow to execute")
    name: str = Field(default="", description="Display name for step")

    # Input mapping from previous step
    input_mappings: list[OutputMapping] = Field(
        default_factory=list,
        description="Maps outputs from previous workflow to inputs",
    )

    # Static inputs (added to mapped inputs)
    static_inputs: dict[str, Any] = Field(
        default_factory=dict, description="Additional static inputs for this step"
    )

    # Conditional execution
    condition: ChainStepCondition | None = Field(
        default=None, description="Condition for executing this step"
    )

    # Error handling
    continue_on_error: bool = Field(
        default=False, description="Continue chain even if this step fails"
    )

    # Per-step model routing (workflow-bar chains, 2026-08-30). A chain reads a
    # hard hand with the best model and counts entities with something cheap,
    # so the override is a property of the STEP, not the chain. None means the
    # workflow resolves its own alias.
    provider_override: str | None = Field(
        default=None, description="Provider override for this step's run"
    )
    model_override: str | None = Field(
        default=None, description="Model override for this step's run"
    )

    # Execution settings
    timeout_seconds: int = Field(
        default=300, description="Max execution time for this step"
    )


class WorkflowChain(BaseModel):
    """Definition of a workflow chain.

    Chains multiple workflows together, passing outputs from one
    as inputs to the next.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Chain name")
    description: str = ""

    # Chain structure
    steps: list[ChainStep] = Field(
        default_factory=list, description="Ordered list of workflow steps"
    )

    # Entry point (first step to execute)
    entry_step: str | None = Field(
        default=None, description="ID of first step (defaults to first in list)"
    )

    # Initial inputs for the chain
    initial_inputs: dict[str, Any] = Field(
        default_factory=dict, description="Default initial inputs for the chain"
    )

    # Metadata
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    folder_path: str = "/"  # Folder organization path
    sort_order: int = 0  # Sort order within folder

    def get_step(self, step_id: str) -> ChainStep | None:
        """Get step by ID."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None


# =============================================================================
# Chain Execution State
# =============================================================================


class ChainStepStatus(str, Enum):
    """Status of a chain step execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChainStepResult(BaseModel):
    """Result of executing a chain step."""

    step_id: str
    workflow_id: str
    status: ChainStepStatus
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    output_files: list[str] = Field(default_factory=list)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: float = 0


class ChainExecutionResult(BaseModel):
    """Result of executing a complete chain."""

    chain_id: str
    execution_id: str
    status: ChainStepStatus
    step_results: list[ChainStepResult] = Field(default_factory=list)
    final_outputs: dict[str, Any] = Field(default_factory=dict)
    final_files: list[str] = Field(default_factory=list)
    total_duration_ms: float = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None


# =============================================================================
# Chain Event Types
# =============================================================================


class ChainEventType(str, Enum):
    """Types of chain execution events."""

    CHAIN_STARTED = "chain_started"
    CHAIN_COMPLETED = "chain_completed"
    CHAIN_FAILED = "chain_failed"
    CHAIN_CANCELLED = "chain_cancelled"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    STEP_SKIPPED = "step_skipped"


class ChainProgressEvent(BaseModel):
    """Progress event for chain execution."""

    event_type: ChainEventType
    chain_id: str
    execution_id: str
    step_id: str | None = None
    step_index: int | None = None
    total_steps: int = 0
    message: str = ""
    error: str | None = None
    progress: float = 0.0  # 0.0 to 1.0
    timestamp: datetime = Field(default_factory=utc_now)


# =============================================================================
# Chain Store (In-Memory for now)
# =============================================================================


class ChainStore:
    """Manages workflow chain definitions.

    Currently stores in memory; could be extended to persist to database.
    """

    def __init__(self):
        self._chains: dict[str, WorkflowChain] = {}

    def save(self, chain: WorkflowChain) -> WorkflowChain:
        """Save a chain definition."""
        chain.updated_at = utc_now()
        self._chains[chain.id] = chain
        return chain

    def get(self, chain_id: str) -> WorkflowChain | None:
        """Get a chain by ID."""
        return self._chains.get(chain_id)

    def list(self, limit: int = 50, offset: int = 0) -> list[WorkflowChain]:
        """List all chains."""
        chains = sorted(
            self._chains.values(),
            key=lambda c: c.updated_at,
            reverse=True,
        )
        return chains[offset : offset + limit]

    def delete(self, chain_id: str) -> bool:
        """Delete a chain by ID."""
        if chain_id in self._chains:
            del self._chains[chain_id]
            return True
        return False


# Global chain store instance
chain_store = ChainStore()
