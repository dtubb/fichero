"""
Workflow State Management

Advanced state management for workflow execution.
Tracks document progress, execution history, and provides utilities for state manipulation.

Key Features:
- Document state tracking and progress management
- Execution history and audit trail
- State serialization and deserialization
- State validation and error recovery
- Integration with LangGraph state management
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, TypedDict
from enum import Enum

from fichero_server.workflows.types import State as BaseState


# =============================================================================
# State Management Types
# =============================================================================


class DocumentStatus(str, Enum):
    """Status of a document in workflow execution."""

    PENDING = "pending"  # Not yet processed
    PROCESSING = "processing"  # Currently being processed
    COMPLETED = "completed"  # Successfully processed
    FAILED = "failed"  # Processing failed
    SKIPPED = "skipped"  # Skipped due to conditions


class DocumentState(TypedDict):
    """State of an individual document in workflow execution."""

    document_id: str
    original_path: str
    status: DocumentStatus
    current_node: str | None
    completed_nodes: list[str]
    error: str | None
    start_time: float
    end_time: float | None
    metadata: dict[str, Any]


class ExecutionHistoryItem(TypedDict):
    """Item in execution history/audit trail."""

    timestamp: float
    event_type: str
    node_id: str | None
    document_id: str | None
    message: str
    data: dict[str, Any]


# =============================================================================
# Extended Workflow State
# =============================================================================


class WorkflowExecutionState(BaseState):
    """Extended workflow execution state with document tracking."""

    # Document management
    documents: list[DocumentState]
    current_document_index: int
    total_documents: int

    # Execution history
    history: list[ExecutionHistoryItem]

    # Performance metrics
    start_time: float
    node_execution_times: dict[str, float]

    # Resource management
    active_connections: int
    max_connections: int

    # Error handling
    error_count: int
    warning_count: int

    # Execution control
    paused: bool
    cancelled: bool

    def __init__(
        self,
        workflow_id: str,
        inputs: dict[str, Any],
        documents: list[str] | None = None,
        max_connections: int = 4,
    ):
        """Initialize workflow execution state."""
        base_state: BaseState = {
            "task_id": str(uuid.uuid4()),
            "workflow_id": workflow_id,
            "inputs": inputs,
            "outputs": {},
            "current_node": "",
            "completed_nodes": [],
            "error": None,
            "input_files": documents or [],
            "output_files": [],
        }

        # Initialize extended state
        self.documents = self._initialize_documents(documents or [])
        self.current_document_index = 0
        self.total_documents = len(self.documents)
        self.history = []
        self.start_time = time.time()
        self.node_execution_times = {}
        self.active_connections = 0
        self.max_connections = max_connections
        self.error_count = 0
        self.warning_count = 0
        self.paused = False
        self.cancelled = False

        # Copy base state attributes
        for key, value in base_state.items():
            setattr(self, key, value)

    def _initialize_documents(self, document_paths: list[str]) -> list[DocumentState]:
        """Initialize document state for all documents."""
        return [
            {
                "document_id": str(uuid.uuid4()),
                "original_path": path,
                "status": DocumentStatus.PENDING,
                "current_node": None,
                "completed_nodes": [],
                "error": None,
                "start_time": time.time(),
                "end_time": None,
                "metadata": {},
            }
            for path in document_paths
        ]

    def add_history_item(
        self,
        event_type: str,
        message: str,
        node_id: str | None = None,
        document_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Add an item to the execution history."""
        item: ExecutionHistoryItem = {
            "timestamp": time.time(),
            "event_type": event_type,
            "node_id": node_id,
            "document_id": document_id,
            "message": message,
            "data": data or {},
        }
        self.history.append(item)

    def start_document_processing(self, document_id: str, node_id: str) -> None:
        """Mark a document as starting processing."""
        for doc in self.documents:
            if doc["document_id"] == document_id:
                doc["status"] = DocumentStatus.PROCESSING
                doc["current_node"] = node_id
                doc["start_time"] = time.time()
                self.add_history_item(
                    "document_started",
                    f"Document {document_id} processing started",
                    node_id=node_id,
                    document_id=document_id,
                )
                break

    def complete_document_processing(self, document_id: str, node_id: str) -> None:
        """Mark a document as completed processing."""
        for doc in self.documents:
            if doc["document_id"] == document_id:
                doc["status"] = DocumentStatus.COMPLETED
                doc["current_node"] = None
                doc["end_time"] = time.time()
                doc["completed_nodes"].append(node_id)
                self.add_history_item(
                    "document_completed",
                    f"Document {document_id} processing completed",
                    node_id=node_id,
                    document_id=document_id,
                )
                break

    def fail_document_processing(
        self, document_id: str, node_id: str, error: str
    ) -> None:
        """Mark a document as failed processing."""
        for doc in self.documents:
            if doc["document_id"] == document_id:
                doc["status"] = DocumentStatus.FAILED
                doc["current_node"] = None
                doc["end_time"] = time.time()
                doc["error"] = error
                self.error_count += 1
                self.add_history_item(
                    "document_failed",
                    f"Document {document_id} processing failed: {error}",
                    node_id=node_id,
                    document_id=document_id,
                    data={"error": error},
                )
                break

    def skip_document(self, document_id: str, reason: str) -> None:
        """Mark a document as skipped."""
        for doc in self.documents:
            if doc["document_id"] == document_id:
                doc["status"] = DocumentStatus.SKIPPED
                doc["current_node"] = None
                doc["end_time"] = time.time()
                self.add_history_item(
                    "document_skipped",
                    f"Document {document_id} skipped: {reason}",
                    document_id=document_id,
                    data={"reason": reason},
                )
                break

    def start_node_execution(self, node_id: str) -> None:
        """Mark the start of node execution."""
        self.current_node = node_id
        self.node_execution_times[node_id] = time.time()
        self.add_history_item(
            "node_started",
            f"Node {node_id} execution started",
            node_id=node_id,
        )

    def complete_node_execution(self, node_id: str) -> None:
        """Mark the completion of node execution."""
        if node_id in self.node_execution_times:
            start_time = self.node_execution_times[node_id]
            duration = time.time() - start_time
            self.node_execution_times[node_id] = duration

        if node_id not in self.completed_nodes:
            self.completed_nodes.append(node_id)

        self.add_history_item(
            "node_completed",
            f"Node {node_id} execution completed in {duration:.2f}s",
            node_id=node_id,
            data={"duration": duration},
        )

    def fail_node_execution(self, node_id: str, error: str) -> None:
        """Mark the failure of node execution."""
        self.error = error
        self.error_count += 1
        self.add_history_item(
            "node_failed",
            f"Node {node_id} execution failed: {error}",
            node_id=node_id,
            data={"error": error},
        )

    def add_output_file(self, file_path: str) -> None:
        """Add an output file to the state."""
        self.output_files.append(file_path)
        self.add_history_item(
            "output_created",
            f"Output file created: {file_path}",
            data={"file_path": file_path},
        )

    def get_execution_duration(self) -> float:
        """Get the total execution duration in seconds."""
        return time.time() - self.start_time

    def get_completion_percentage(self) -> float:
        """Get the completion percentage (0.0 to 1.0)."""
        if self.total_documents == 0:
            return 0.0

        completed = sum(
            1 for doc in self.documents if doc["status"] == DocumentStatus.COMPLETED
        )
        return completed / self.total_documents

    def get_document_status_counts(self) -> dict[DocumentStatus, int]:
        """Get counts of documents by status."""
        counts: dict[DocumentStatus, int] = {
            DocumentStatus.PENDING: 0,
            DocumentStatus.PROCESSING: 0,
            DocumentStatus.COMPLETED: 0,
            DocumentStatus.FAILED: 0,
            DocumentStatus.SKIPPED: 0,
        }

        for doc in self.documents:
            counts[doc["status"]] += 1

        return counts

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary for serialization."""
        base_attrs = {k: v for k, v in vars(self).items() if not k.startswith("_")}

        # Convert TypedDict objects to regular dicts
        result = {}
        for key, value in base_attrs.items():
            if hasattr(value, "items"):  # It's a dict-like object
                result[key] = dict(value)
            elif isinstance(value, list):
                result[key] = [
                    dict(item) if hasattr(item, "items") else item for item in value
                ]
            else:
                result[key] = value

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowExecutionState:
        """Create state from dictionary."""
        # This is a simplified reconstruction
        # In a real implementation, we'd need to handle all the complex state properly
        state = cls(
            workflow_id=data.get("workflow_id", ""),
            inputs=data.get("inputs", {}),
            max_connections=data.get("max_connections", 4),
        )

        # Restore as much state as possible
        for key, value in data.items():
            if hasattr(state, key):
                setattr(state, key, value)

        return state

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the execution state."""
        duration = self.get_execution_duration()
        status_counts = self.get_document_status_counts()

        return {
            "workflow_id": self.workflow_id,
            "task_id": self.task_id,
            "status": "completed" if self.error is None else "failed",
            "error": self.error,
            "duration_seconds": duration,
            "documents_processed": status_counts[DocumentStatus.COMPLETED],
            "documents_failed": status_counts[DocumentStatus.FAILED],
            "documents_skipped": status_counts[DocumentStatus.SKIPPED],
            "nodes_completed": len(self.completed_nodes),
            "errors": self.error_count,
            "warnings": self.warning_count,
            "output_files": len(self.output_files),
        }


# =============================================================================
# State Utilities
# =============================================================================


def create_initial_state(
    workflow_id: str,
    inputs: dict[str, Any],
    document_paths: list[str] | None = None,
    max_connections: int = 4,
) -> WorkflowExecutionState:
    """Create initial workflow execution state."""
    return WorkflowExecutionState(
        workflow_id=workflow_id,
        inputs=inputs,
        documents=document_paths,
        max_connections=max_connections,
    )


def merge_states(
    base_state: BaseState, extended_state: WorkflowExecutionState
) -> WorkflowExecutionState:
    """Merge base state with extended state."""
    # Copy base state attributes to extended state
    for key, value in base_state.items():
        if hasattr(extended_state, key):
            setattr(extended_state, key, value)

    return extended_state


def validate_state(state: WorkflowExecutionState) -> bool:
    """Validate that the state is in a consistent state."""
    # Basic validation
    if not state.workflow_id:
        return False

    if len(state.documents) != state.total_documents:
        return False

    if state.current_document_index >= len(state.documents):
        return False

    # Check document status consistency
    for doc in state.documents:
        if doc["status"] == DocumentStatus.PROCESSING:
            if not doc["current_node"]:
                return False  # Processing but no current node

        if doc["status"] in [
            DocumentStatus.COMPLETED,
            DocumentStatus.FAILED,
            DocumentStatus.SKIPPED,
        ]:
            if doc["current_node"]:
                return False  # Completed but still has current node

    return True


# =============================================================================
# State Serialization
# =============================================================================


def serialize_state(state: WorkflowExecutionState) -> str:
    """Serialize state to JSON string."""

    state_dict = state.to_dict()
    return json.dumps(state_dict, indent=2)


def deserialize_state(json_str: str) -> WorkflowExecutionState:
    """Deserialize state from JSON string."""

    data = json.loads(json_str)
    return WorkflowExecutionState.from_dict(data)


# =============================================================================
# Testing
# =============================================================================


async def test_state_management() -> bool:
    """Test the state management functionality."""
    try:
        # Create initial state
        state = create_initial_state(
            workflow_id="test_workflow",
            inputs={"test_input": "value"},
            document_paths=["/path/to/doc1.pdf", "/path/to/doc2.pdf"],
        )

        # Test document management
        doc1_id = state.documents[0]["document_id"]
        state.start_document_processing(doc1_id, "node1")
        state.complete_document_processing(doc1_id, "node1")

        # Test node execution
        state.start_node_execution("node1")
        state.complete_node_execution("node1")

        # Test serialization
        serialized = serialize_state(state)
        deserialize_state(serialized)

        # Test summary
        state.get_summary()

        return True

    except Exception as e:
        print(f"State management test failed: {e}")
        return False


if __name__ == "__main__":
    import asyncio

    # Run tests
    result = asyncio.run(test_state_management())
    if result:
        print("State management tests passed!")
    else:
        print("State management tests failed!")
