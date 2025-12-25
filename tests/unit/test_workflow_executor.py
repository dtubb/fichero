"""
Unit tests for Workflow Executor

Tests the core workflow execution engine with LangGraph integration.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fichero.workflows.executor import (
    WorkflowExecutor,
    ProgressEvent,
    ProgressEventType,
    ProgressEventListener,
    ResourcePool,
    SSEEventAdapter,
    DocumentState,
    execute_workflow_with_progress,
)
from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef, State
from fichero.workflows.registry import TOOLS, register_tool
from fichero.llm import LLMConfig


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
    
    def test_initialization(self, simple_workflow):
        """Test that WorkflowExecutor initializes correctly."""
        executor = WorkflowExecutor(simple_workflow)
        
        assert executor.workflow == simple_workflow
        assert executor.max_concurrent == 4
        assert executor.max_retries == 3
        assert executor._cancel_requested is False
        assert executor._current_task_id is None
    
    def test_add_remove_progress_listener(self, simple_workflow):
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
    
    def test_cancel(self, simple_workflow):
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
        """Test executing a workflow that gets cancelled."""
        executor = WorkflowExecutor(simple_workflow)
        
        # Request cancellation before execution
        executor.cancel()
        
        with patch.object(executor, '_execute_with_pregel', new_callable=AsyncMock) as mock_execute:
            with pytest.raises(asyncio.CancelledError):
                await executor.execute({"test": "input"})


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
    async def test_progress_event_emission(self, simple_workflow):
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
        """Test creating a DocumentState."""
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
        
        assert state.task_id == "test_task"
        assert state.workflow_id == "test_workflow"
        assert state.max_concurrent_tasks == 4
        assert state.max_retries == 3


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for workflow execution."""
    
    @pytest.mark.asyncio
    async def test_execute_workflow_with_progress(self, simple_workflow, test_tool):
        """Test the execute_workflow_with_progress function."""
        # Mock the executor
        with patch('fichero.workflows.executor.WorkflowExecutor') as MockExecutor:
            mock_executor = MockExecutor.return_value
            mock_executor.execute.return_value = {"status": "completed"}
            
            # Mock SSE adapter
            mock_adapter = MagicMock()
            mock_adapter.get_sse_stream.return_value = AsyncMock()
            
            with patch('fichero.workflows.executor.SSEEventAdapter', return_value=mock_adapter):
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
    async def test_execute_with_exception(self, simple_workflow):
        """Test that exceptions during execution are handled properly."""
        executor = WorkflowExecutor(simple_workflow)
        
        with patch.object(executor, '_execute_with_pregel', new_callable=AsyncMock) as mock_execute:
            mock_execute.side_effect = Exception("Test exception")
            
            with pytest.raises(Exception) as exc_info:
                await executor.execute({"test": "input"})
            
            assert "Test exception" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_event_listener_exception(self, simple_workflow):
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
# Test Configuration
# =============================================================================

def pytest_configure(config):
    """Configure pytest for async tests."""
    config.addinivalue_line(
        "markers",
        "slow: mark tests as slow (deselect with '-m "not slow"')"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])