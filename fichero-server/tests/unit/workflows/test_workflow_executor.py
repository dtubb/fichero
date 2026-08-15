"""
Unit tests for Workflow Executor

Tests the core workflow execution engine with LangGraph integration.
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from fichero_server.workflows.executor import (
    WorkflowExecutor,
    ProgressEvent,
    ProgressEventType,
    ProgressEventListener,
    ResourcePool,
    SSEEventAdapter,
    DocumentState,
    execute_workflow_with_progress,
)
from fichero_server.workflows.types import WorkflowDef, NodeDef, EdgeDef, State
from fichero_server.workflows.registry import register_tool
from fichero_server.llm import LLMConfig


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def simple_workflow() -> WorkflowDef:
    """Create a simple workflow for testing."""
    return WorkflowDef(
        id="test_workflow",
        name="Test Workflow",
        nodes=[
            NodeDef(
                id="node1",
                tool="test_tool",
                input_ports=[],
                output_ports=[],
            ),
            NodeDef(
                id="node2",
                tool="test_tool",
                input_ports=[],
                output_ports=[],
            ),
        ],
        edges=[
            EdgeDef(
                source="node1",
                target="node2",
                source_port="output",
                target_port="input",
            ),
        ],
    )


@pytest.fixture
def test_tool():
    """Register a test tool for testing."""
    @register_tool(
        name="test_tool",
        display_name="Test Tool",
        description="A tool for testing",
        category="test",
    )
    async def mock_tool(inputs: dict, state: State, llm_config: LLMConfig) -> dict:
        return {"result": "success", **inputs}
    
    return mock_tool


# =============================================================================
# WorkflowExecutor Tests
# =============================================================================

class TestWorkflowExecutor:
    """Test the WorkflowExecutor class."""

    def test_initialization(self, simple_workflow, test_tool):
        """Test that WorkflowExecutor initializes correctly."""
        executor = WorkflowExecutor(simple_workflow)

        assert executor.workflow == simple_workflow
        assert executor.max_concurrent == 4
        assert executor.max_retries == 3
        assert executor._cancel_requested is False
        assert executor._current_task_id is None

    def test_add_remove_progress_listener(self, simple_workflow, test_tool):
        """Test adding and removing progress listeners."""
        executor = WorkflowExecutor(simple_workflow)

        class MockListener(ProgressEventListener):
            async def on_progress_event(self, event: ProgressEvent) -> None:
                pass

        listener = MockListener()
        executor.add_progress_listener(listener)

        assert listener in executor._listeners

        executor.remove_progress_listener(listener)
        assert listener not in executor._listeners

    def test_cancel(self, simple_workflow, test_tool):
        """Test cancellation functionality."""
        executor = WorkflowExecutor(simple_workflow)
        
        assert executor._cancel_requested is False
        
        executor.cancel()
        assert executor._cancel_requested is True
    
    @pytest.mark.asyncio
    async def test_execute_simple_workflow(self, simple_workflow, test_tool):
        """Test executing a simple workflow."""
        executor = WorkflowExecutor(simple_workflow)
        
        # Mock the Pregel execution
        mock_state = {
            "task_id": "test_task",
            "workflow_id": "test_workflow",
            "inputs": {"test": "input"},
            "outputs": {},
            "current_node": "",
            "completed_nodes": ["node1", "node2"],
            "error": None,
            "input_files": [],
            "output_files": [],
        }
        
        with patch.object(executor, '_execute_with_pregel', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_state
            
            result = await executor.execute({"test": "input"})
            
            assert result == mock_state
            mock_execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_with_error(self, simple_workflow, test_tool):
        """Test executing a workflow that encounters an error."""
        executor = WorkflowExecutor(simple_workflow)
        
        mock_state = {
            "task_id": "test_task",
            "workflow_id": "test_workflow",
            "inputs": {"test": "input"},
            "outputs": {},
            "current_node": "node1",
            "completed_nodes": [],
            "error": "Test error",
            "input_files": [],
            "output_files": [],
        }
        
        with patch.object(executor, '_execute_with_pregel', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_state
            
            result = await executor.execute({"test": "input"})
            
            assert result["error"] == "Test error"
    
    @pytest.mark.asyncio
    async def test_execute_cancellation(self, simple_workflow, test_tool):
        """Test that cancel() sets the cancellation flag."""
        executor = WorkflowExecutor(simple_workflow)

        # Initially, cancellation is not requested
        assert executor._cancel_requested is False

        # Request cancellation
        executor.cancel()
        assert executor._cancel_requested is True

        # Note: Calling execute() resets the flag, so pre-execution cancellation
        # doesn't raise CancelledError. The cancellation is checked during execution.

    @pytest.mark.asyncio
    async def test_execute_emits_cancelled_not_completed_when_pregel_stops_on_cancel(
        self, simple_workflow, test_tool
    ):
        """Mid-run cancellation must surface as cancelled, not a false success."""
        executor = WorkflowExecutor(simple_workflow)
        events_received: list[ProgressEvent] = []

        class MockListener(ProgressEventListener):
            async def on_progress_event(self, event: ProgressEvent) -> None:
                events_received.append(event)

        executor.add_progress_listener(MockListener())
        cancelled_state = {
            "task_id": "test_task",
            "workflow_id": "test_workflow",
            "inputs": {"test": "input"},
            "outputs": {},
            "current_node": "node1",
            "completed_nodes": ["node1"],
            "error": None,
            "cancelled": True,
            "input_files": [],
            "output_files": [],
        }

        with patch.object(executor, "_execute_with_pregel", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = cancelled_state

            result = await executor.execute({"test": "input"})

        assert result["cancelled"] is True
        assert [event.event_type for event in events_received] == [
            ProgressEventType.WORKFLOW_STARTED,
            ProgressEventType.WORKFLOW_CANCELLED,
        ]


# =============================================================================
# Progress Event Tests
# =============================================================================

class TestProgressEvents:
    """Test progress event functionality."""
    
    def test_progress_event_creation(self):
        """Test creating progress events."""
        event = ProgressEvent(
            event_type=ProgressEventType.WORKFLOW_STARTED,
            task_id="test_task",
            workflow_id="test_workflow",
            message="Test message",
            progress=0.5,
        )
        
        assert event.event_type == ProgressEventType.WORKFLOW_STARTED
        assert event.task_id == "test_task"
        assert event.workflow_id == "test_workflow"
        assert event.message == "Test message"
        assert event.progress == 0.5
        assert event.timestamp > 0
    
    @pytest.mark.asyncio
    async def test_progress_event_emission(self, simple_workflow, test_tool):
        """Test emitting progress events."""
        executor = WorkflowExecutor(simple_workflow)
        
        events_received = []
        
        class MockListener(ProgressEventListener):
            async def on_progress_event(self, event: ProgressEvent) -> None:
                events_received.append(event)
        
        listener = MockListener()
        executor.add_progress_listener(listener)
        
        test_event = ProgressEvent(
            event_type=ProgressEventType.WORKFLOW_STARTED,
            task_id="test_task",
            workflow_id="test_workflow",
            message="Test",
        )
        
        await executor._emit_event(test_event)
        
        assert len(events_received) == 1
        assert events_received[0] == test_event

    @pytest.mark.asyncio
    async def test_execute_with_pregel_emits_node_completed_for_regular_nodes(self, simple_workflow, test_tool, monkeypatch):
        executor = WorkflowExecutor(simple_workflow)

        class FakeGraph:
            async def astream(self, current_state, stream_mode=None, subgraphs=False):
                yield (
                    (),
                    {
                        "node1": {
                            "current_node": "node1",
                            "completed_nodes": ["node1"],
                        }
                    },
                )

        monkeypatch.setattr(executor, "_graph", FakeGraph())
        state = executor._create_initial_state({})

        final_state = await executor._execute_with_pregel(state)

        assert final_state["completed_nodes"] == ["node1"]
        started = await executor._event_queue.get()
        completed = await executor._event_queue.get()
        assert started.event_type == ProgressEventType.NODE_STARTED
        assert completed.event_type == ProgressEventType.NODE_COMPLETED
        assert completed.node_id == "node1"


# =============================================================================
# Resource Pool Tests
# =============================================================================

class TestResourcePool:
    """Test the ResourcePool class."""
    
    def test_resource_pool_initialization(self):
        """Test ResourcePool initialization."""
        pool = ResourcePool(max_concurrent=2)
        
        assert pool.max_concurrent == 2
        assert pool.active_tasks == 0
    
    @pytest.mark.asyncio
    async def test_resource_acquisition(self):
        """Test acquiring and releasing resources."""
        pool = ResourcePool(max_concurrent=1)
        
        await pool.acquire()
        assert pool.active_tasks == 1
        
        pool.release()
        assert pool.active_tasks == 0
    
    @pytest.mark.asyncio
    async def test_resource_pool_limiting(self):
        """Test that resource pool limits concurrent tasks."""
        pool = ResourcePool(max_concurrent=1)
        
        # Acquire the only available resource
        await pool.acquire()
        
        # Try to acquire another - should wait
        start_time = time.time()
        
        async def acquire_second():
            await pool.acquire()
            return time.time() - start_time
        
        # This should take some time as it waits for the first resource to be released
        task = asyncio.create_task(acquire_second())
        
        # Wait a bit, then release the first resource
        await asyncio.sleep(0.1)
        pool.release()
        
        duration = await task
        assert duration >= 0.1
        
        pool.release()
    
    @pytest.mark.asyncio
    async def test_execute_with_resource(self):
        """Test executing a function with resource management."""
        pool = ResourcePool(max_concurrent=1)
        
        async def test_function(x: int) -> int:
            return x * 2
        
        result = await pool.execute_with_resource(test_function, 5)
        assert result == 10


# =============================================================================
# SSE Event Adapter Tests
# =============================================================================

class TestSSEEventAdapter:
    """Test the SSEEventAdapter class."""
    
    def test_sse_adapter_initialization(self):
        """Test SSEEventAdapter initialization."""
        adapter = SSEEventAdapter()
        assert adapter.event_queue.empty()
    
    @pytest.mark.asyncio
    async def test_event_to_sse_conversion(self):
        """Test converting progress events to SSE format."""
        adapter = SSEEventAdapter()
        
        event = ProgressEvent(
            event_type=ProgressEventType.WORKFLOW_STARTED,
            task_id="test_task",
            workflow_id="test_workflow",
            message="Test message",
            progress=0.5,
        )
        
        await adapter.on_progress_event(event)
        
        # Get the SSE event from the queue
        sse_event = await adapter.event_queue.get()
        
        assert sse_event.startswith("data: {")
        assert "workflow_started" in sse_event
        assert "test_task" in sse_event
        assert "test_workflow" in sse_event
    
    @pytest.mark.asyncio
    async def test_sse_stream(self):
        """Test getting an SSE event stream."""
        adapter = SSEEventAdapter()
        
        # Add some events
        event1 = ProgressEvent(
            event_type=ProgressEventType.WORKFLOW_STARTED,
            task_id="test_task",
            workflow_id="test_workflow",
        )
        
        event2 = ProgressEvent(
            event_type=ProgressEventType.NODE_COMPLETED,
            task_id="test_task",
            workflow_id="test_workflow",
            node_id="node1",
        )
        
        await adapter.on_progress_event(event1)
        await adapter.on_progress_event(event2)
        
        # Get the stream
        stream = adapter.get_sse_stream()
        
        events = []
        async for sse_event in stream:
            events.append(sse_event)
            if len(events) >= 2:
                break
        
        assert len(events) == 2
        assert "workflow_started" in events[0]
        assert "node_completed" in events[1]


# =============================================================================
# Document State Tests
# =============================================================================

class TestDocumentState:
    """Test DocumentState functionality."""

    def test_document_state_creation(self):
        """Test creating a DocumentState.

        Note: DocumentState is a dataclass extending TypedDict, which means
        calling it returns a dict-like object with dict-style access.
        """
        state = DocumentState(
            task_id="test_task",
            workflow_id="test_workflow",
            inputs={"test": "input"},
            outputs={},
            current_node="",
            completed_nodes=[],
            error=None,
            input_files=[],
            output_files=[],
            documents=[],
            current_document=0,
            total_documents=0,
            cancelled=False,
            paused=False,
            active_tasks=0,
            max_concurrent_tasks=4,
            start_time=time.time(),
            node_times={},
            retry_counts={},
            max_retries=3,
        )

        # DocumentState returns dict-like object, use dict-style access
        assert state["task_id"] == "test_task"
        assert state["workflow_id"] == "test_workflow"
        assert state["max_concurrent_tasks"] == 4
        assert state["max_retries"] == 3


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for workflow execution."""

    @pytest.mark.asyncio
    async def test_execute_workflow_with_progress(self, simple_workflow, test_tool):
        """Test the execute_workflow_with_progress function."""
        # Mock the executor
        with patch('fichero_server.workflows.executor.WorkflowExecutor') as MockExecutor:
            mock_executor = MockExecutor.return_value
            # Use AsyncMock for async method
            mock_executor.execute = AsyncMock(return_value={"status": "completed"})
            mock_executor.add_progress_listener = MagicMock()

            # Mock SSE adapter
            mock_adapter = MagicMock()

            async def mock_stream():
                yield "data: test"

            mock_adapter.get_sse_stream.return_value = mock_stream()

            with patch('fichero_server.workflows.executor.SSEEventAdapter', return_value=mock_adapter):
                result, stream = await execute_workflow_with_progress(
                    simple_workflow,
                    {"test": "input"}
                )

                assert result == {"status": "completed"}
                mock_executor.execute.assert_called_once()
                mock_adapter.get_sse_stream.assert_called_once()


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Test error handling in workflow execution."""
    
    @pytest.mark.asyncio
    async def test_execute_with_exception(self, simple_workflow, test_tool):
        """Test that exceptions during execution are handled properly."""
        executor = WorkflowExecutor(simple_workflow)

        with patch.object(executor, '_execute_with_pregel', new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = Exception("Test exception")

            with pytest.raises(Exception) as exc_info:
                await executor.execute({"test": "input"})

            assert "Test exception" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_event_listener_exception(self, simple_workflow, test_tool):
        """Test that exceptions in event listeners don't break execution."""
        executor = WorkflowExecutor(simple_workflow)
        
        class FailingListener(ProgressEventListener):
            async def on_progress_event(self, event: ProgressEvent) -> None:
                raise Exception("Listener failed")
        
        listener = FailingListener()
        executor.add_progress_listener(listener)
        
        # This should not raise an exception
        test_event = ProgressEvent(
            event_type=ProgressEventType.WORKFLOW_STARTED,
            task_id="test_task",
            workflow_id="test_workflow",
        )
        
        await executor._emit_event(test_event)
        # Execution should continue despite the listener failure


# =============================================================================
# Mock Tools for Testing
# =============================================================================

@register_tool(
    name="mock_success_tool",
    display_name="Mock Success Tool",
    description="Always succeeds",
    category="test",
)
async def mock_success_tool(inputs: dict, state: State, llm_config: LLMConfig) -> dict:
    """A tool that always succeeds."""
    return {"result": "success", **inputs}


@register_tool(
    name="mock_fail_tool",
    display_name="Mock Fail Tool",
    description="Always fails",
    category="test",
)
async def mock_fail_tool(inputs: dict, state: State, llm_config: LLMConfig) -> dict:
    """A tool that always fails."""
    raise Exception("Tool failed intentionally")


# =============================================================================
# Parallel Execution Tests
# =============================================================================

class TestParallelExecution:
    """Test parallel file processing with Send API."""

    @pytest.fixture
    def parallel_workflow(self) -> WorkflowDef:
        """Create a workflow with parallel processing nodes."""
        return WorkflowDef(
            id="parallel_test_workflow",
            name="Parallel Test Workflow",
            nodes=[
                NodeDef(
                    id="source",
                    tool="collection",  # Source tool
                    label="Get Files",
                ),
                NodeDef(
                    id="transcribe",
                    tool="transcribe",  # Parallel tool
                    label="Transcribe Files",
                ),
            ],
            edges=[
                EdgeDef(
                    source="source",
                    target="transcribe",
                    source_port="files",
                    target_port="files",
                ),
            ],
        )

    def test_parallel_tools_detection(self):
        """Test that PARALLEL_TOOLS contains expected tools."""
        from fichero_server.workflows.builder import PARALLEL_TOOLS

        assert "transcribe" in PARALLEL_TOOLS
        assert "describe" in PARALLEL_TOOLS
        assert "summarize" in PARALLEL_TOOLS
        # The registered tool name — "entities" was a phantom that resolved to
        # no tool, silently disabling fan-out (test_builder_tool_name_registry).
        assert "extract_entities" in PARALLEL_TOOLS
        # Non-parallel tools should not be in the set
        assert "collection" not in PARALLEL_TOOLS
        assert "search" not in PARALLEL_TOOLS

    def test_parallel_edge_detection(self, parallel_workflow):
        """Test that parallel edges are detected correctly."""
        from fichero_server.workflows.builder import PARALLEL_TOOLS, SOURCE_TOOLS

        # Verify the edge connects source -> parallel tool
        edge = parallel_workflow.edges[0]
        target_node = parallel_workflow.get_node(edge.target)
        source_node = parallel_workflow.get_node(edge.source)

        # Target should be a parallel tool
        assert target_node.tool in PARALLEL_TOOLS, "transcribe should be parallel"
        # Source should be a source tool
        assert source_node.tool == "collection", "source should be collection"
        assert source_node.tool in SOURCE_TOOLS, "collection should be in SOURCE_TOOLS"

    def test_source_tools_includes_all_sources(self):
        """Test that SOURCE_TOOLS includes all expected source tools."""
        from fichero_server.workflows.builder import SOURCE_TOOLS

        # All these tools should trigger parallel processing when connected to PARALLEL_TOOLS
        expected_sources = {"files", "collection", "folder", "search"}
        assert SOURCE_TOOLS == expected_sources, f"Expected {expected_sources}, got {SOURCE_TOOLS}"

    def test_fan_out_function_creation(self):
        """Test creating a fan-out function."""
        from fichero_server.workflows.builder import _make_fan_out_function

        fan_out = _make_fan_out_function(
            "source",
            ["transcribe"],
            {"transcribe": "transcribe"},
        )
        assert callable(fan_out), "fan_out should be callable"

        # Test with mock state
        state = {
            "task_id": "test",
            "workflow_id": "test",
            "outputs": {
                "source": {
                    "files": ["/path/file1.jpg", "/path/file2.jpg", "/path/file3.jpg"],
                    "documents": [],
                }
            },
        }

        sends = fan_out(state)
        assert len(sends) == 3, "Should create 3 Send objects"

        # Check Send objects have correct target
        for send in sends:
            assert send.node == "transcribe_process"

    def test_fan_out_empty_files(self):
        """Zero files FAILS the run (Daniel, 2026-08-11) — except search.

        The old contract (return [] and complete green) read absence as
        success. Full policy coverage lives in
        test_zero_file_fan_out_policy.py.
        """
        import pytest
        from fichero_server.workflows.builder import _make_fan_out_function

        state = {"outputs": {"source": {"files": [], "documents": []}}}

        fan_out = _make_fan_out_function(
            "source",
            ["transcribe"],
            {"transcribe": "transcribe"},
            source_tool="folder",
        )
        with pytest.raises(ValueError, match="0 files"):
            fan_out(state)

        search_fan_out = _make_fan_out_function(
            "source",
            ["transcribe"],
            {"transcribe": "transcribe"},
            source_tool="search",
        )
        assert search_fan_out(state) == []

    def test_aggregation_function_creation(self):
        """Test creating an aggregation function."""
        from fichero_server.workflows.builder import _make_aggregation_function

        aggregate = _make_aggregation_function("transcribe")
        assert callable(aggregate), "aggregate should be callable"

    @pytest.mark.asyncio
    async def test_regular_node_receives_progress_callback(self):
        """Long-running non-parallel tools can emit runner SSE progress."""
        from fichero_server.workflows.builder import _make_node_function

        events = []

        async def event_callback(event_type, data):
            events.append((event_type, data))

        async def tool_fn(inputs, state, llm_config):
            progress = inputs["__progress_callback"]
            await progress("file_start", {"file_path": "chunk 1", "file_index": 1})
            await progress("file_complete", {"file_path": "chunk 1", "file_index": 1})
            return {"text": "ok"}

        node_def = NodeDef(id="extract-node", tool="extract_all")
        node_fn = _make_node_function(
            node_def,
            tool_fn,
            LLMConfig(provider="test", model="test"),
            workflow_config={},
            event_callback=event_callback,
        )
        result = await node_fn({"outputs": {}, "completed_nodes": []})

        assert result["outputs"]["extract-node"]["text"] == "ok"
        assert [event_type for event_type, _ in events] == [
            "file_start",
            "file_complete",
        ]
        assert events[0][1]["node_id"] == "extract-node"

    @pytest.mark.asyncio
    async def test_aggregation_function_combines_results(self):
        """Test that aggregation properly combines parallel results."""
        from fichero_server.workflows.builder import _make_aggregation_function

        aggregate = _make_aggregation_function("transcribe")

        # Mock state with parallel results
        state = {
            "parallel_results": {
                "transcribe": [
                    {"file": "/path/file1.jpg", "index": 0, "result": {"text": "Text 1"}, "success": True},
                    {"file": "/path/file2.jpg", "index": 1, "result": {"text": "Text 2"}, "success": True},
                    {"file": "/path/file3.jpg", "index": 2, "error": "Failed", "success": False},
                ]
            },
            "outputs": {},
            "completed_nodes": [],
        }

        result = await aggregate(state)

        # Check aggregated output
        assert "outputs" in result
        assert "transcribe" in result["outputs"]
        output = result["outputs"]["transcribe"]

        assert output["success_count"] == 2
        assert output["error_count"] == 1
        assert len(output["texts"]) == 2
        assert output["texts"][0] == "Text 1"
        assert output["texts"][1] == "Text 2"

    @pytest.mark.asyncio
    async def test_aggregation_function_concatenates_page_records(self):
        """Per-page records on each parallel result land flat under
        aggregated['records'] in parallel-index order. This is what
        carries page provenance to extract_all so the records port
        can drive page-level KG storage (#701, #837 follow-up)."""
        from fichero_server.workflows.builder import _make_aggregation_function

        aggregate = _make_aggregation_function("transcribe")

        state = {
            "parallel_results": {
                "transcribe": [
                    {
                        "file": "/p/a.pdf", "index": 0, "success": True,
                        "result": {
                            "text": "A1\n\nA2",
                            "page_records": [
                                {"doc_id": "a-p1", "text": "A1"},
                                {"doc_id": "a-p2", "text": "A2"},
                            ],
                        },
                    },
                    {
                        "file": "/p/b.pdf", "index": 1, "success": True,
                        "result": {
                            "text": "B1",
                            "page_records": [{"doc_id": "b-p1", "text": "B1"}],
                        },
                    },
                ]
            },
            "outputs": {},
            "completed_nodes": [],
        }

        result = await aggregate(state)
        records = result["outputs"]["transcribe"]["records"]

        assert [r["doc_id"] for r in records] == ["a-p1", "a-p2", "b-p1"]
        assert [r["text"] for r in records] == ["A1", "A2", "B1"]

    @pytest.mark.asyncio
    async def test_aggregation_function_handles_missing_page_records(self):
        """Results without page_records (legacy / non-vision tools)
        produce an empty records list — never crash, never inject
        garbage entries."""
        from fichero_server.workflows.builder import _make_aggregation_function

        aggregate = _make_aggregation_function("transcribe")
        state = {
            "parallel_results": {
                "transcribe": [
                    {
                        "file": "/p/a.jpg", "index": 0, "success": True,
                        "result": {"text": "T"},  # no page_records key
                    },
                ]
            },
            "outputs": {},
            "completed_nodes": [],
        }
        result = await aggregate(state)
        assert result["outputs"]["transcribe"]["records"] == []

    def test_state_has_parallel_fields(self):
        """Test that State TypedDict has parallel execution fields."""
        from fichero_server.workflows.types import State

        # Check that the required keys are in State's annotations
        annotations = State.__annotations__

        assert "parallel_results" in annotations
        assert "parallel_index" in annotations
        assert "parallel_total" in annotations
        assert "parallel_file" in annotations
        assert "parallel_document" in annotations
        assert "error" in annotations

        # error must be reducer-backed to avoid INVALID_CONCURRENT_GRAPH_UPDATE
        error_annotation = annotations["error"]
        # Future annotations store TypedDict annotations as ForwardRef strings.
        # Verify we keep reducer-backed Annotated form.
        assert "Annotated" in str(error_annotation)
        assert "_merge_error" in str(error_annotation)


# =============================================================================
# Error Detection Tests
# =============================================================================

class TestErrorDetection:
    """Tests for systemic error detection in parallel processing."""

    @pytest.mark.asyncio
    async def test_consecutive_errors_triggers_abort(self):
        """Test that 5+ consecutive errors trigger SystemicErrorDetected."""
        from fichero_server.workflows.builder import (
            _make_aggregation_function,
            SystemicErrorDetected,
        )

        # Create aggregation function
        agg_fn = _make_aggregation_function("test_node")

        # Create results with consecutive errors
        # First 2 succeed, then 5 fail in a row (should trigger abort)
        results = [
            {"index": 0, "success": True, "result": {"text": "ok"}},
            {"index": 1, "success": True, "result": {"text": "ok"}},
            {"index": 2, "success": False, "file": "f3.txt", "error": "API error"},
            {"index": 3, "success": False, "file": "f4.txt", "error": "API error"},
            {"index": 4, "success": False, "file": "f5.txt", "error": "API error"},
            {"index": 5, "success": False, "file": "f6.txt", "error": "API error"},
            {"index": 6, "success": False, "file": "f7.txt", "error": "API error"},
        ]

        state = {"parallel_results": {"test_node": results}}

        with pytest.raises(SystemicErrorDetected) as exc_info:
            await agg_fn(state)

        assert exc_info.value.error_count == 5
        assert exc_info.value.total_count == 7
        assert "consecutive failures" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_scattered_errors_no_abort(self):
        """Test that scattered errors (not consecutive) don't trigger abort."""
        from fichero_server.workflows.builder import _make_aggregation_function

        agg_fn = _make_aggregation_function("test_node")

        # Create results with errors scattered (never 5 in a row)
        results = [
            {"index": 0, "success": True, "result": {"text": "ok"}},
            {"index": 1, "success": False, "file": "f2.txt", "error": "error"},
            {"index": 2, "success": True, "result": {"text": "ok"}},
            {"index": 3, "success": False, "file": "f4.txt", "error": "error"},
            {"index": 4, "success": True, "result": {"text": "ok"}},
            {"index": 5, "success": False, "file": "f6.txt", "error": "error"},
            {"index": 6, "success": True, "result": {"text": "ok"}},
            {"index": 7, "success": False, "file": "f8.txt", "error": "error"},
            {"index": 8, "success": True, "result": {"text": "ok"}},
        ]

        state = {"parallel_results": {"test_node": results}}

        # Should not raise - errors are scattered
        result = await agg_fn(state)

        assert result["outputs"]["test_node"]["error_count"] == 4
        assert result["outputs"]["test_node"]["success_count"] == 5

    @pytest.mark.asyncio
    async def test_high_error_rate_triggers_abort(self):
        """Test that error rate > 50% triggers SystemicErrorDetected."""
        from fichero_server.workflows.builder import (
            _make_aggregation_function,
            SystemicErrorDetected,
        )

        agg_fn = _make_aggregation_function("test_node")

        # Create 12 results with 7 failures (58% error rate)
        # Scatter them to avoid consecutive error detection (max 4 in a row)
        # Pattern: F F F F S F F F S S S S (4 fail, 1 succeed, 3 fail, 4 succeed)
        results = [
            {"index": 0, "success": False, "file": "f0.txt", "error": "error"},
            {"index": 1, "success": False, "file": "f1.txt", "error": "error"},
            {"index": 2, "success": False, "file": "f2.txt", "error": "error"},
            {"index": 3, "success": False, "file": "f3.txt", "error": "error"},
            {"index": 4, "success": True, "result": {"text": "ok"}},  # Break
            {"index": 5, "success": False, "file": "f5.txt", "error": "error"},
            {"index": 6, "success": False, "file": "f6.txt", "error": "error"},
            {"index": 7, "success": False, "file": "f7.txt", "error": "error"},
            {"index": 8, "success": True, "result": {"text": "ok"}},  # Break
            {"index": 9, "success": True, "result": {"text": "ok"}},
            {"index": 10, "success": True, "result": {"text": "ok"}},
            {"index": 11, "success": True, "result": {"text": "ok"}},
        ]

        state = {"parallel_results": {"test_node": results}}

        with pytest.raises(SystemicErrorDetected) as exc_info:
            await agg_fn(state)

        assert exc_info.value.error_count == 7
        assert "error rate" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_small_batch_no_rate_check(self):
        """Test that small batches don't trigger error rate check."""
        from fichero_server.workflows.builder import _make_aggregation_function

        agg_fn = _make_aggregation_function("test_node")

        # 5 files with 3 failures (60% error rate, but < MIN_FILES_FOR_ERROR_RATE)
        # Also ensure errors aren't consecutive (4 would be under threshold of 5)
        results = [
            {"index": 0, "success": True, "result": {"text": "ok"}},
            {"index": 1, "success": False, "file": "f2.txt", "error": "error"},
            {"index": 2, "success": True, "result": {"text": "ok"}},
            {"index": 3, "success": False, "file": "f4.txt", "error": "error"},
            {"index": 4, "success": False, "file": "f5.txt", "error": "error"},
        ]

        state = {"parallel_results": {"test_node": results}}

        # Should not raise - batch too small for error rate check
        result = await agg_fn(state)

        assert result["outputs"]["test_node"]["error_count"] == 3
        assert result["outputs"]["test_node"]["success_count"] == 2


# =============================================================================
# Aggregator barrier (#837)
# =============================================================================


@pytest.mark.asyncio
async def test_aggregator_defers_when_partial_results():
    """The auto-aggregator must NOT emit a partial aggregate when only some
    parallel sub-nodes have completed. Returning the empty result early
    would let downstream nodes consume an empty aggregate while transcribe
    is still running — the #837 race that left catalogue/extract_all with
    no text input. Each parallel_node_function carries its `total` count
    in its result; the aggregator gates on len(results) >= total."""
    from fichero_server.workflows.builder import _make_aggregation_function

    agg = _make_aggregation_function("transcribe")

    # Simulate: 3-file fan-out, only 1 result so far.
    state = {
        "parallel_results": {
            "transcribe": [
                {
                    "file": "page1.jpeg",
                    "index": 0,
                    "total": 3,
                    "result": {"text": "page 1 text"},
                    "success": True,
                },
            ],
        },
    }
    out = await agg(state)
    assert out == {}, (
        "aggregator must return empty (no state update) when partial — "
        "got: %r" % (out,)
    )


@pytest.mark.asyncio
async def test_aggregator_emits_when_all_results_arrive():
    """Sanity: when all parallel sub-nodes have completed, the aggregator
    DOES emit the merged result. Pairs with the deferral test above —
    confirms the gate flips from 'wait' to 'emit' at the expected total."""
    from fichero_server.workflows.builder import _make_aggregation_function

    agg = _make_aggregation_function("transcribe")

    state = {
        "parallel_results": {
            "transcribe": [
                {"file": "page1.jpeg", "index": 0, "total": 2,
                 "result": {"text": "page 1 text"}, "success": True},
                {"file": "page2.jpeg", "index": 1, "total": 2,
                 "result": {"text": "page 2 text"}, "success": True},
            ],
        },
    }
    out = await agg(state)
    assert "outputs" in out, (
        "aggregator must commit the merged result when complete — got: %r"
        % (out,)
    )
    assert out["outputs"]["transcribe"]["text"] == "page 1 text\n\npage 2 text"
    assert out["outputs"]["transcribe"]["success_count"] == 2


@pytest.mark.asyncio
async def test_aggregator_aborts_when_every_parallel_branch_failed():
    """A completed fan-out with zero successes must fail loud, not emit empty text."""
    from fichero_server.workflows.builder import _make_aggregation_function, SystemicErrorDetected

    agg = _make_aggregation_function("transcribe")

    state = {
        "parallel_results": {
            "transcribe": [
                {
                    "file": "page1.jpeg",
                    "index": 0,
                    "total": 2,
                    "error": "provider refused",
                    "success": False,
                },
                {
                    "file": "page2.jpeg",
                    "index": 1,
                    "total": 2,
                    "error": "provider refused",
                    "success": False,
                },
            ],
        },
    }

    with pytest.raises(SystemicErrorDetected, match="All parallel branches failed"):
        await agg(state)


# =============================================================================
# Node-error abort behaviour (#839)
# =============================================================================


@pytest.mark.asyncio
async def test_node_returning_error_dict_aborts_workflow():
    """When a tool returns {'error': '...'}, the wrapping node function
    must raise SystemicErrorDetected so the workflow aborts. Historical
    behaviour was to silently set state.error and let downstream nodes
    proceed on missing input — produced indistinguishable-from-success
    runs that hung waiting on empty inputs (#839)."""
    from fichero_server.workflows.builder import _make_node_function, SystemicErrorDetected
    from fichero_server.workflows.types import NodeDef
    from fichero_server.llm import LLMConfig

    node_def = NodeDef(id="failing", tool="test_failing_tool", config={})

    async def failing_tool(inputs, state, llm_config):
        return {"error": "Extract All: 1/1 LLM calls failed — guardrailViolation"}

    node_fn = _make_node_function(
        node_def,
        failing_tool,
        LLMConfig(provider="apple", model="apple-intelligence"),
        workflow_config={},
        incoming_edges=[],
    )

    state = {"outputs": {}, "completed_nodes": []}
    with pytest.raises(SystemicErrorDetected) as exc_info:
        await node_fn(state)

    assert "failing" in str(exc_info.value) or "Step" in str(exc_info.value)
    assert "1/1 LLM calls failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_node_returning_no_error_does_not_abort():
    """Sanity: a tool returning a normal dict (no 'error' key) should NOT
    raise. Confirms the abort path is gated on the error key, not on
    every tool return."""
    from fichero_server.workflows.builder import _make_node_function
    from fichero_server.workflows.types import NodeDef
    from fichero_server.llm import LLMConfig

    node_def = NodeDef(id="ok", tool="test_ok_tool", config={})

    async def ok_tool(inputs, state, llm_config):
        return {"text": "all good", "value": {"some": "data"}}

    node_fn = _make_node_function(
        node_def,
        ok_tool,
        LLMConfig(provider="apple", model="apple-intelligence"),
        workflow_config={},
        incoming_edges=[],
    )

    state = {"outputs": {}, "completed_nodes": []}
    result = await node_fn(state)
    assert result["outputs"]["ok"]["text"] == "all good"
    assert "ok" in result["completed_nodes"]


# =============================================================================
# Test Configuration
# =============================================================================

def pytest_configure(config):
    """Configure pytest for async tests."""
    config.addinivalue_line(
        "markers",
        'slow: mark tests as slow (deselect with \'-m "not slow"\')'
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
