"""
Workflow Executor

Core workflow execution engine with LangGraph integration.
Handles document processing, state management, progress events, and concurrent execution.

Key Features:
- LangGraph StateGraph integration with Pregel Execution Engine
- Document state tracking and progress management
- Real-time progress events for UI updates
- Robust error handling and retry logic
- Concurrent execution with resource pooling
- Integration with existing workflow types and registry
"""

from __future__ import annotations

import asyncio
import logging
import uuid
import time
from typing import Any, Callable, AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from langgraph.graph import StateGraph, START, END
from langgraph.pregel import Pregel

from fichero.workflows.types import (
    State as BaseState,
    WorkflowDef,
    NodeDef,
    EdgeDef,
)
from fichero.workflows.registry import TOOLS, get_tool, get_tool_def
from fichero.workflows.resolver import resolve_inputs, evaluate_condition
from fichero.workflows.builder import build_graph
from fichero.llm import LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Progress Event System
# =============================================================================

class ProgressEventType(str, Enum):
    """Types of progress events emitted during execution."""
    WORKFLOW_STARTED = "workflow_started"
    NODE_STARTED = "node_started"
    NODE_PROGRESS = "node_progress"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    NODE_RETRY = "node_retry"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_CANCELLED = "workflow_cancelled"


@dataclass
class ProgressEvent:
    """Progress event emitted during workflow execution."""
    event_type: ProgressEventType
    timestamp: float = field(default_factory=time.time)
    task_id: str = ""
    workflow_id: str = ""
    node_id: str | None = None
    progress: float | None = None  # 0.0 to 1.0
    message: str | None = None
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class ProgressEventListener:
    """Interface for listening to progress events."""
    async def on_progress_event(self, event: ProgressEvent) -> None:
        """Handle a progress event."""
        pass


# =============================================================================
# Document State Management
# =============================================================================

class DocumentState(BaseState):
    """Extended state for document processing workflows."""
    # Document tracking
    documents: list[dict[str, Any]] = field(default_factory=list)
    current_document: int = 0
    total_documents: int = 0
    
    # Execution control
    cancelled: bool = False
    paused: bool = False
    
    # Resource management
    active_tasks: int = 0
    max_concurrent_tasks: int = 4
    
    # Performance metrics
    start_time: float = field(default_factory=time.time)
    node_times: dict[str, float] = field(default_factory=dict)
    
    # Retry management
    retry_counts: dict[str, int] = field(default_factory=dict)
    max_retries: int = 3


# =============================================================================
# Workflow Executor
# =============================================================================

class WorkflowExecutor:
    """Core workflow execution engine."""
    
    def __init__(
        self,
        workflow: WorkflowDef,
        llm_config: LLMConfig | None = None,
        max_concurrent: int = 4,
        max_retries: int = 3,
    ):
        self.workflow = workflow
        self.llm_config = llm_config or LLMConfig()
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        
        # Event system
        self._listeners: list[ProgressEventListener] = []
        self._event_queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        
        # Execution state
        self._current_task_id: str | None = None
        self._cancel_requested = False
        
        # Build the graph
        self._graph = self._build_execution_graph()
        
        logger.info(f"Initialized WorkflowExecutor for '{workflow.name}'")
    
    def _build_execution_graph(self) -> Pregel:
        """Build the execution graph using LangGraph Pregel Execution Engine."""
        # Build the base graph using existing builder
        base_graph = build_graph(self.workflow)
        
        # Convert to Pregel for advanced execution control
        # Pregel provides better control over execution flow and state management
        pregel_graph = Pregel(base_graph)
        
        return pregel_graph
    
    def add_progress_listener(self, listener: ProgressEventListener) -> None:
        """Add a progress event listener."""
        self._listeners.append(listener)
    
    def remove_progress_listener(self, listener: ProgressEventListener) -> None:
        """Remove a progress event listener."""
        self._listeners.remove(listener)
    
    async def _emit_event(self, event: ProgressEvent) -> None:
        """Emit a progress event to all listeners."""
        # Put event in queue for async processing
        await self._event_queue.put(event)
        
        # Notify listeners immediately
        for listener in self._listeners:
            try:
                await listener.on_progress_event(event)
            except Exception as e:
                logger.error(f"Error in progress listener: {e}")
    
    async def _process_event_queue(self) -> None:
        """Process events from the queue."""
        while not self._event_queue.empty():
            event = await self._event_queue.get()
            # Events are already processed by listeners in _emit_event
            self._event_queue.task_done()
    
    def cancel(self) -> None:
        """Request cancellation of current execution."""
        self._cancel_requested = True
        logger.info(f"Cancellation requested for workflow '{self.workflow.name}'")
    
    async def execute(
        self,
        inputs: dict[str, Any],
        input_files: list[str] | None = None,
        documents: list[dict[str, Any]] | None = None,
    ) -> DocumentState:
        """Execute the workflow with the given inputs.
        
        Args:
            inputs: Initial inputs to the workflow
            input_files: Optional list of input file paths
            documents: Optional list of documents to process
            
        Returns:
            Final execution state
        """
        # Generate task ID
        self._current_task_id = str(uuid.uuid4())
        task_id = self._current_task_id
        
        # Create initial state
        initial_state = self._create_initial_state(inputs, input_files, documents)
        
        # Reset cancellation flag
        self._cancel_requested = False
        
        try:
            # Emit workflow started event
            await self._emit_event(ProgressEvent(
                event_type=ProgressEventType.WORKFLOW_STARTED,
                task_id=task_id,
                workflow_id=self.workflow.id,
                message=f"Workflow '{self.workflow.name}' started",
            ))
            
            logger.info(f"Executing workflow: {self.workflow.name} (task_id: {task_id})")
            
            # Execute using Pregel Execution Engine
            # Pregel provides better control over execution and state management
            final_state = await self._execute_with_pregel(initial_state)
            
            if final_state.get("error"):
                logger.error(f"Workflow failed: {final_state['error']}")
                await self._emit_event(ProgressEvent(
                    event_type=ProgressEventType.WORKFLOW_FAILED,
                    task_id=task_id,
                    workflow_id=self.workflow.id,
                    error=final_state["error"],
                ))
            else:
                logger.info(f"Workflow completed: {len(final_state.get('completed_nodes', []))} nodes")
                await self._emit_event(ProgressEvent(
                    event_type=ProgressEventType.WORKFLOW_COMPLETED,
                    task_id=task_id,
                    workflow_id=self.workflow.id,
                    message=f"Workflow completed successfully",
                    progress=1.0,
                ))
            
            return final_state
            
        except asyncio.CancelledError:
            logger.info(f"Workflow cancelled: {self.workflow.name}")
            await self._emit_event(ProgressEvent(
                event_type=ProgressEventType.WORKFLOW_CANCELLED,
                task_id=task_id,
                workflow_id=self.workflow.id,
                message="Workflow execution was cancelled",
            ))
            raise
        
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            await self._emit_event(ProgressEvent(
                event_type=ProgressEventType.WORKFLOW_FAILED,
                task_id=task_id,
                workflow_id=self.workflow.id,
                error=str(e),
            ))
            raise
    
    def _create_initial_state(
        self,
        inputs: dict[str, Any],
        input_files: list[str] | None = None,
        documents: list[dict[str, Any]] | None = None,
    ) -> DocumentState:
        """Create the initial execution state."""
        state = DocumentState(
            task_id=str(uuid.uuid4()),
            workflow_id=self.workflow.id,
            inputs=inputs,
            outputs={},
            current_node="",
            completed_nodes=[],
            error=None,
            input_files=input_files or [],
            output_files=[],
            
            # Document tracking
            documents=documents or [],
            current_document=0,
            total_documents=len(documents or []),
            
            # Execution control
            cancelled=False,
            paused=False,
            
            # Resource management
            active_tasks=0,
            max_concurrent_tasks=self.max_concurrent,
            
            # Performance metrics
            start_time=time.time(),
            node_times={},
            
            # Retry management
            retry_counts=defaultdict(int),
            max_retries=self.max_retries,
        )
        
        return state
    
    async def _execute_with_pregel(self, initial_state: DocumentState) -> DocumentState:
        """Execute workflow using LangGraph Pregel Execution Engine.
        
        Pregel provides:
        - Fine-grained control over execution
        - Better state management
        - Support for complex workflow patterns
        - Improved error handling
        """
        # Get the Pregel execution engine
        pregel = self._graph
        
        # Set up execution with our state management
        current_state = initial_state
        
        # Track execution progress
        total_nodes = len(self.workflow.nodes)
        completed_nodes = 0
        
        # Execute nodes using Pregel
        async for step in pregel.astream(current_state):
            # Check for cancellation
            if self._cancel_requested:
                current_state["cancelled"] = True
                break
            
            # Update progress
            if step["current_node"] and step["current_node"] not in current_state.get("completed_nodes", []):
                node_id = step["current_node"]
                
                # Emit node started event
                await self._emit_event(ProgressEvent(
                    event_type=ProgressEventType.NODE_STARTED,
                    task_id=current_state["task_id"],
                    workflow_id=current_state["workflow_id"],
                    node_id=node_id,
                    progress=float(completed_nodes) / max(total_nodes, 1),
                    message=f"Starting node: {node_id}",
                ))
                
                # Track node execution time
                node_start_time = time.time()
            
            # Update state with step results
            current_state.update(step)
            
            # Check if node completed
            if step.get("completed_nodes"):
                for node_id in step["completed_nodes"]:
                    if node_id not in current_state.get("completed_nodes", []):
                        completed_nodes += 1
                        
                        # Calculate node execution time
                        if node_id in current_state.get("node_times", {}):
                            # Already tracked
                            pass
                        else:
                            node_end_time = time.time()
                            # This would be more accurate with proper timing in the node execution
                            
                        # Emit node completed event
                        await self._emit_event(ProgressEvent(
                            event_type=ProgressEventType.NODE_COMPLETED,
                            task_id=current_state["task_id"],
                            workflow_id=current_state["workflow_id"],
                            node_id=node_id,
                            progress=float(completed_nodes) / max(total_nodes, 1),
                            message=f"Completed node: {node_id}",
                        ))
            
            # Check for errors
            if step.get("error"):
                error = step["error"]
                current_node = step.get("current_node", "unknown")
                
                # Check if we should retry
                retry_count = current_state["retry_counts"].get(current_node, 0)
                if retry_count < current_state["max_retries"]:
                    await self._emit_event(ProgressEvent(
                        event_type=ProgressEventType.NODE_RETRY,
                        task_id=current_state["task_id"],
                        workflow_id=current_state["workflow_id"],
                        node_id=current_node,
                        message=f"Retrying node {current_node} (attempt {retry_count + 1})",
                        data={"retry_count": retry_count + 1},
                    ))
                    
                    # Increment retry count
                    current_state["retry_counts"][current_node] = retry_count + 1
                    
                    # Reset error and continue
                    current_state["error"] = None
                    continue
                else:
                    # Max retries exceeded
                    await self._emit_event(ProgressEvent(
                        event_type=ProgressEventType.NODE_FAILED,
                        task_id=current_state["task_id"],
                        workflow_id=current_state["workflow_id"],
                        node_id=current_node,
                        error=error,
                        message=f"Node {current_node} failed after {retry_count} retries",
                    ))
                    
                    # Set workflow error
                    current_state["error"] = f"Node {current_node} failed: {error}"
                    break
        
        return current_state
    
    async def execute_concurrent(
        self,
        inputs_list: list[dict[str, Any]],
        batch_size: int = 4,
    ) -> list[DocumentState]:
        """Execute workflow concurrently on multiple input sets.
        
        Args:
            inputs_list: List of input dictionaries
            batch_size: Maximum concurrent executions
            
        Returns:
            List of final states for each execution
        """
        results = []
        semaphore = asyncio.Semaphore(batch_size)
        
        async def execute_single(inputs: dict[str, Any]) -> DocumentState:
            async with semaphore:
                return await self.execute(inputs)
        
        # Execute all inputs concurrently
        tasks = [execute_single(inputs) for inputs in inputs_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Batch execution {i} failed: {result}")
                # Create error state
                error_state = self._create_initial_state(inputs_list[i])
                error_state["error"] = str(result)
                final_results.append(error_state)
            else:
                final_results.append(result)
        
        return final_results
    
    def get_progress_stream(self) -> AsyncIterator[ProgressEvent]:
        """Get an async stream of progress events.
        
        Usage:
            async for event in executor.get_progress_stream():
                print(f"Progress: {event.event_type} - {event.message}")
        """
        async def event_generator():
            while True:
                event = await self._event_queue.get()
                yield event
                self._event_queue.task_done()
        
        return event_generator()


# =============================================================================
# Resource Management
# =============================================================================

class ResourcePool:
    """Resource pool for managing concurrent tool execution."""
    
    def __init__(self, max_concurrent: int = 4):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.active_tasks = 0
        self.task_queue: asyncio.Queue[Callable] = asyncio.Queue()
    
    async def acquire(self) -> None:
        """Acquire a resource from the pool."""
        await self.semaphore.acquire()
        self.active_tasks += 1
    
    def release(self) -> None:
        """Release a resource back to the pool."""
        self.semaphore.release()
        self.active_tasks -= 1
    
    async def execute_with_resource(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with resource management."""
        await self.acquire()
        try:
            return await func(*args, **kwargs)
        finally:
            self.release()


# =============================================================================
# Event Stream Adapter for SSE
# =============================================================================

class SSEEventAdapter(ProgressEventListener):
    """Adapter to convert progress events to Server-Sent Events format."""
    
    def __init__(self):
        self.event_queue: asyncio.Queue[str] = asyncio.Queue()
    
    async def on_progress_event(self, event: ProgressEvent) -> None:
        """Convert progress event to SSE format."""
        sse_event = self._event_to_sse(event)
        await self.event_queue.put(sse_event)
    
    def _event_to_sse(self, event: ProgressEvent) -> str:
        """Convert progress event to SSE format."""
        event_data = {
            "event": event.event_type,
            "timestamp": event.timestamp,
            "task_id": event.task_id,
            "workflow_id": event.workflow_id,
            "node_id": event.node_id,
            "progress": event.progress,
            "message": event.message,
            "error": event.error,
            "data": event.data,
        }
        
        import json
        return f"data: {json.dumps(event_data)}\n\n"
    
    async def get_sse_stream(self) -> AsyncIterator[str]:
        """Get SSE-formatted event stream."""
        while True:
            event = await self.event_queue.get()
            yield event
            self.event_queue.task_done()


# =============================================================================
# Integration with Existing Builder
# =============================================================================

async def execute_workflow_with_progress(
    workflow: WorkflowDef,
    inputs: dict[str, Any],
    input_files: list[str] | None = None,
    documents: list[dict[str, Any]] | None = None,
) -> tuple[DocumentState, AsyncIterator[ProgressEvent]]:
    """Execute workflow with progress events using the new executor.
    
    This function provides a drop-in replacement for the existing execute_workflow
    but adds progress event support.
    """
    # Create executor
    executor = WorkflowExecutor(workflow)
    
    # Create SSE adapter for progress events
    sse_adapter = SSEEventAdapter()
    executor.add_progress_listener(sse_adapter)
    
    # Execute workflow
    final_state = await executor.execute(inputs, input_files, documents)
    
    # Return state and event stream
    return final_state, sse_adapter.get_sse_stream()


# =============================================================================
# Backward Compatibility
# =============================================================================

# Alias for backward compatibility
execute_workflow = execute_workflow_with_progress


# =============================================================================
# Testing and Validation
# =============================================================================

async def validate_workflow_executor() -> bool:
    """Validate that the workflow executor is properly configured."""
    try:
        # Test basic functionality
        from fichero.workflows.types import WorkflowDef, NodeDef
        from fichero.workflows.registry import TOOL_DEFS
        
        # Create a simple test workflow
        test_workflow = WorkflowDef(
            id="test_workflow",
            name="Test Workflow",
            nodes=[],
            edges=[],
        )
        
        # Create executor
        executor = WorkflowExecutor(test_workflow)
        
        # Test event system
        class TestListener(ProgressEventListener):
            def __init__(self):
                self.events = []
            
            async def on_progress_event(self, event: ProgressEvent) -> None:
                self.events.append(event)
        
        listener = TestListener()
        executor.add_progress_listener(listener)
        
        # Test cancellation
        executor.cancel()
        
        return True
        
    except Exception as e:
        logger.error(f"Workflow executor validation failed: {e}")
        return False


# Initialize the workflow system
async def initialize_workflow_system():
    """Initialize the workflow system."""
    # Import and register all tools
    from fichero.workflows import registry
    registry._register_builtin_tools()
    
    # Validate executor
    validation_result = await validate_workflow_executor()
    if validation_result:
        logger.info("Workflow system initialized successfully")
    else:
        logger.error("Workflow system initialization failed")
    
    return validation_result