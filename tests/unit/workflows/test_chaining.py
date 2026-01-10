"""Unit tests for workflow chaining system."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from fichero.workflows.chaining import (
    WorkflowChain,
    ChainStep,
    OutputMapping,
    ChainStepCondition,
    ChainExecutor,
    ChainStepResult,
    ChainStepStatus,
    ChainStore,
    resolve_output_path,
    map_outputs_to_inputs,
    apply_transform,
    evaluate_condition,
)


# =============================================================================
# Test Output Path Resolution
# =============================================================================

class TestResolveOutputPath:
    """Tests for output path resolution."""

    def test_resolve_simple_path(self):
        """Test resolving a simple path."""
        data = {"outputs": {"node1": {"text": "hello"}}}
        result = resolve_output_path(data, "$.outputs.node1.text")
        assert result == "hello"

    def test_resolve_nested_path(self):
        """Test resolving a deeply nested path."""
        data = {"outputs": {"extractor": {"entities": {"people": ["Alice", "Bob"]}}}}
        result = resolve_output_path(data, "$.outputs.extractor.entities.people")
        assert result == ["Alice", "Bob"]

    def test_resolve_array_index(self):
        """Test resolving array index."""
        data = {"files": ["/a.pdf", "/b.pdf", "/c.pdf"]}
        result = resolve_output_path(data, "$.files.1")
        assert result == "/b.pdf"

    def test_resolve_missing_path(self):
        """Test resolving missing path returns None."""
        data = {"outputs": {}}
        result = resolve_output_path(data, "$.outputs.missing.key")
        assert result is None

    def test_literal_value(self):
        """Test non-path values are returned as-is."""
        result = resolve_output_path({}, "literal string")
        assert result == "literal string"

    def test_resolve_root_key(self):
        """Test resolving root-level key."""
        data = {"files": ["/a.pdf"]}
        result = resolve_output_path(data, "$.files")
        assert result == ["/a.pdf"]


# =============================================================================
# Test Transformations
# =============================================================================

class TestApplyTransform:
    """Tests for value transformations."""

    def test_join_transform(self):
        """Test join transform on array."""
        result = apply_transform(["a", "b", "c"], "join:, ")
        assert result == "a, b, c"

    def test_join_default_separator(self):
        """Test join with default separator."""
        result = apply_transform(["x", "y"], "join")
        assert result == "x, y"

    def test_first_transform(self):
        """Test first element transform."""
        result = apply_transform(["first", "second", "third"], "first")
        assert result == "first"

    def test_first_empty_list(self):
        """Test first on empty list returns None."""
        result = apply_transform([], "first")
        assert result is None

    def test_last_transform(self):
        """Test last element transform."""
        result = apply_transform(["first", "second", "third"], "last")
        assert result == "third"

    def test_count_transform(self):
        """Test count transform."""
        result = apply_transform(["a", "b", "c", "d"], "count")
        assert result == 4

    def test_count_string(self):
        """Test count on string."""
        result = apply_transform("hello", "count")
        assert result == 5

    def test_unknown_transform(self):
        """Test unknown transform returns value unchanged."""
        result = apply_transform("value", "unknown_transform")
        assert result == "value"


# =============================================================================
# Test Input Mapping
# =============================================================================

class TestMapOutputsToInputs:
    """Tests for output-to-input mapping."""

    def test_map_single_output(self):
        """Test mapping a single output."""
        previous = ChainStepResult(
            step_id="step1",
            workflow_id="wf1",
            status=ChainStepStatus.COMPLETED,
            outputs={"summarizer": {"text": "Summary text"}},
        )
        mappings = [
            OutputMapping(source_path="$.outputs.summarizer.text", target_key="input_text"),
        ]

        result = map_outputs_to_inputs(previous, mappings, {})
        assert result["input_text"] == "Summary text"

    def test_map_with_static_inputs(self):
        """Test mapping with additional static inputs."""
        previous = ChainStepResult(
            step_id="step1",
            workflow_id="wf1",
            status=ChainStepStatus.COMPLETED,
            outputs={},
        )
        static = {"language": "en", "format": "json"}

        result = map_outputs_to_inputs(previous, [], static)
        assert result["language"] == "en"
        assert result["format"] == "json"

    def test_map_files(self):
        """Test mapping output files."""
        previous = ChainStepResult(
            step_id="step1",
            workflow_id="wf1",
            status=ChainStepStatus.COMPLETED,
            outputs={},
            output_files=["/output/result.pdf"],
        )
        mappings = [
            OutputMapping(source_path="$.files", target_key="input_files"),
        ]

        result = map_outputs_to_inputs(previous, mappings, {})
        assert result["input_files"] == ["/output/result.pdf"]

    def test_map_with_transform(self):
        """Test mapping with transformation."""
        previous = ChainStepResult(
            step_id="step1",
            workflow_id="wf1",
            status=ChainStepStatus.COMPLETED,
            outputs={"extractor": {"names": ["Alice", "Bob", "Charlie"]}},
        )
        mappings = [
            OutputMapping(
                source_path="$.outputs.extractor.names",
                target_key="names_str",
                transform="join:; ",
            ),
        ]

        result = map_outputs_to_inputs(previous, mappings, {})
        assert result["names_str"] == "Alice; Bob; Charlie"


# =============================================================================
# Test Condition Evaluation
# =============================================================================

class TestEvaluateCondition:
    """Tests for condition evaluation."""

    def test_simple_equality(self):
        """Test simple equality condition."""
        condition = ChainStepCondition(expression='$.outputs.classifier.category == "invoice"')
        data = {"outputs": {"classifier": {"category": "invoice"}}}
        assert evaluate_condition(condition, data) is True

    def test_inequality(self):
        """Test inequality condition."""
        condition = ChainStepCondition(expression='$.outputs.classifier.category != "spam"')
        data = {"outputs": {"classifier": {"category": "invoice"}}}
        assert evaluate_condition(condition, data) is True

    def test_numeric_comparison(self):
        """Test numeric comparison."""
        condition = ChainStepCondition(expression='$.outputs.counter.count > 10')
        data = {"outputs": {"counter": {"count": 15}}}
        assert evaluate_condition(condition, data) is True

    def test_false_condition(self):
        """Test condition that evaluates to false."""
        condition = ChainStepCondition(expression='$.outputs.score.value > 0.9')
        data = {"outputs": {"score": {"value": 0.5}}}
        assert evaluate_condition(condition, data) is False

    def test_missing_path_condition(self):
        """Test condition with missing path."""
        condition = ChainStepCondition(expression='$.outputs.missing == "value"')
        data = {"outputs": {}}
        # None == "value" is False
        assert evaluate_condition(condition, data) is False


# =============================================================================
# Test Chain Definition
# =============================================================================

class TestWorkflowChain:
    """Tests for WorkflowChain model."""

    def test_create_chain(self):
        """Test creating a workflow chain."""
        chain = WorkflowChain(
            name="Test Chain",
            description="A test chain",
            steps=[
                ChainStep(id="step1", workflow_id="wf1"),
                ChainStep(id="step2", workflow_id="wf2"),
            ],
        )
        assert chain.name == "Test Chain"
        assert len(chain.steps) == 2
        assert chain.id is not None

    def test_get_step(self):
        """Test getting step by ID."""
        chain = WorkflowChain(
            name="Test",
            steps=[
                ChainStep(id="s1", workflow_id="wf1"),
                ChainStep(id="s2", workflow_id="wf2"),
            ],
        )
        step = chain.get_step("s2")
        assert step is not None
        assert step.workflow_id == "wf2"

    def test_get_next_step(self):
        """Test getting next step in sequence."""
        chain = WorkflowChain(
            name="Test",
            steps=[
                ChainStep(id="s1", workflow_id="wf1"),
                ChainStep(id="s2", workflow_id="wf2"),
                ChainStep(id="s3", workflow_id="wf3"),
            ],
        )
        next_step = chain.get_next_step("s1")
        assert next_step is not None
        assert next_step.id == "s2"

    def test_get_next_step_last(self):
        """Test getting next step from last returns None."""
        chain = WorkflowChain(
            name="Test",
            steps=[
                ChainStep(id="s1", workflow_id="wf1"),
            ],
        )
        next_step = chain.get_next_step("s1")
        assert next_step is None


# =============================================================================
# Test Chain Store
# =============================================================================

class TestChainStore:
    """Tests for ChainStore."""

    def test_save_and_get(self):
        """Test saving and retrieving a chain."""
        store = ChainStore()
        chain = WorkflowChain(name="Test", steps=[])

        saved = store.save(chain)
        retrieved = store.get(saved.id)

        assert retrieved is not None
        assert retrieved.name == "Test"

    def test_list_chains(self):
        """Test listing chains."""
        store = ChainStore()
        store.save(WorkflowChain(name="Chain 1", steps=[]))
        store.save(WorkflowChain(name="Chain 2", steps=[]))
        store.save(WorkflowChain(name="Chain 3", steps=[]))

        chains = store.list(limit=2)
        assert len(chains) == 2

    def test_delete_chain(self):
        """Test deleting a chain."""
        store = ChainStore()
        chain = store.save(WorkflowChain(name="To Delete", steps=[]))

        assert store.delete(chain.id) is True
        assert store.get(chain.id) is None

    def test_delete_nonexistent(self):
        """Test deleting nonexistent chain returns False."""
        store = ChainStore()
        assert store.delete("nonexistent-id") is False


# =============================================================================
# Test Chain Executor
# =============================================================================

class TestChainExecutor:
    """Tests for ChainExecutor."""

    @pytest.fixture
    def mock_workflow(self):
        """Create a mock workflow definition."""
        mock = MagicMock()
        mock.id = "wf-test"
        mock.name = "Test Workflow"
        return mock

    @pytest.fixture
    def mock_loader(self, mock_workflow):
        """Create a mock workflow loader."""
        return lambda wf_id: mock_workflow if wf_id == "wf-test" else None

    @pytest.mark.asyncio
    async def test_execute_single_step_chain(self, mock_loader, mock_workflow):
        """Test executing a chain with single step."""
        chain = WorkflowChain(
            name="Single Step",
            steps=[ChainStep(id="step1", workflow_id="wf-test")],
        )

        # Mock the workflow executor
        mock_final_state = {
            "outputs": {"result": {"text": "done"}},
            "output_files": ["/out.pdf"],
            "error": None,
        }

        with patch(
            "fichero.workflows.chaining.WorkflowExecutor"
        ) as MockExecutor:
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=mock_final_state)
            MockExecutor.return_value = mock_executor

            executor = ChainExecutor(workflow_loader=mock_loader)
            result = await executor.execute(chain, initial_inputs={"test": "input"})

            assert result.status == ChainStepStatus.COMPLETED
            assert len(result.step_results) == 1
            assert result.step_results[0].status == ChainStepStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_multi_step_chain(self, mock_loader, mock_workflow):
        """Test executing a chain with multiple steps."""
        chain = WorkflowChain(
            name="Multi Step",
            steps=[
                ChainStep(id="step1", workflow_id="wf-test"),
                ChainStep(
                    id="step2",
                    workflow_id="wf-test",
                    input_mappings=[
                        OutputMapping(source_path="$.outputs.result.text", target_key="input_text"),
                    ],
                ),
            ],
        )

        call_count = 0

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return {
                "outputs": {"result": {"text": f"output_{call_count}"}},
                "output_files": [],
                "error": None,
            }

        with patch(
            "fichero.workflows.chaining.WorkflowExecutor"
        ) as MockExecutor:
            mock_executor = MagicMock()
            mock_executor.execute = mock_execute
            MockExecutor.return_value = mock_executor

            executor = ChainExecutor(workflow_loader=mock_loader)
            result = await executor.execute(chain)

            assert result.status == ChainStepStatus.COMPLETED
            assert len(result.step_results) == 2
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_execute_chain_with_workflow_error(self, mock_loader, mock_workflow):
        """Test chain handles workflow step errors."""
        chain = WorkflowChain(
            name="Error Chain",
            steps=[ChainStep(id="step1", workflow_id="wf-test")],
        )

        mock_final_state = {
            "outputs": {},
            "output_files": [],
            "error": "Workflow failed",
        }

        with patch(
            "fichero.workflows.chaining.WorkflowExecutor"
        ) as MockExecutor:
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=mock_final_state)
            MockExecutor.return_value = mock_executor

            executor = ChainExecutor(workflow_loader=mock_loader)
            result = await executor.execute(chain)

            assert result.status == ChainStepStatus.FAILED
            assert result.step_results[0].status == ChainStepStatus.FAILED

    @pytest.mark.asyncio
    async def test_execute_chain_continue_on_error(self, mock_loader, mock_workflow):
        """Test chain continues after error when configured."""
        chain = WorkflowChain(
            name="Continue Chain",
            steps=[
                ChainStep(id="step1", workflow_id="wf-test", continue_on_error=True),
                ChainStep(id="step2", workflow_id="wf-test"),
            ],
        )

        call_count = 0

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"outputs": {}, "output_files": [], "error": "Step 1 failed"}
            return {"outputs": {"done": True}, "output_files": [], "error": None}

        with patch(
            "fichero.workflows.chaining.WorkflowExecutor"
        ) as MockExecutor:
            mock_executor = MagicMock()
            mock_executor.execute = mock_execute
            MockExecutor.return_value = mock_executor

            executor = ChainExecutor(workflow_loader=mock_loader)
            result = await executor.execute(chain)

            # Chain should complete because continue_on_error=True
            assert result.status == ChainStepStatus.COMPLETED
            assert len(result.step_results) == 2
            assert result.step_results[0].status == ChainStepStatus.FAILED
            assert result.step_results[1].status == ChainStepStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_chain_missing_workflow(self, mock_loader):
        """Test chain handles missing workflow."""
        chain = WorkflowChain(
            name="Missing WF",
            steps=[ChainStep(id="step1", workflow_id="nonexistent")],
        )

        executor = ChainExecutor(workflow_loader=mock_loader)
        result = await executor.execute(chain)

        assert result.status == ChainStepStatus.FAILED
        assert "not found" in result.step_results[0].error.lower()

    @pytest.mark.asyncio
    async def test_execute_chain_with_events(self, mock_loader, mock_workflow):
        """Test chain emits progress events."""
        chain = WorkflowChain(
            name="Event Chain",
            steps=[ChainStep(id="step1", workflow_id="wf-test")],
        )

        events = []

        def event_callback(event):
            events.append(event)

        mock_final_state = {
            "outputs": {"done": True},
            "output_files": [],
            "error": None,
        }

        with patch(
            "fichero.workflows.chaining.WorkflowExecutor"
        ) as MockExecutor:
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(return_value=mock_final_state)
            MockExecutor.return_value = mock_executor

            executor = ChainExecutor(
                workflow_loader=mock_loader,
                event_callback=event_callback,
            )
            await executor.execute(chain)

            # Should have chain started, step started, step completed, chain completed
            assert len(events) >= 4
            event_types = [e.event_type.value for e in events]
            assert "chain_started" in event_types
            assert "chain_completed" in event_types
