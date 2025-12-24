"""
Unit tests for the workflow system.

Tests types, registry, builder, and resolver.
"""

import pytest
from unittest.mock import patch, AsyncMock


# =============================================================================
# Resolver Tests
# =============================================================================

class TestResolver:
    """Tests for the input resolver."""

    def test_resolve_literal_string(self):
        """Test that non-path strings are returned as-is."""
        from fichero.workflows.resolver import resolve_value

        state = {"task_id": "t1", "workflow_id": "w1", "inputs": {}, "outputs": {}}
        assert resolve_value("hello", state) == "hello"
        assert resolve_value(123, state) == 123
        assert resolve_value(True, state) is True

    def test_resolve_node_output(self):
        """Test resolving $.nodes.x.y paths."""
        from fichero.workflows.resolver import resolve_value

        state = {
            "task_id": "t1",
            "workflow_id": "w1",
            "inputs": {},
            "outputs": {
                "transcribe": {"text": "Hello world", "count": 42}
            },
        }

        assert resolve_value("$.nodes.transcribe.text", state) == "Hello world"
        assert resolve_value("$.nodes.transcribe.count", state) == 42

    def test_resolve_inputs(self):
        """Test resolving $.inputs.x paths."""
        from fichero.workflows.resolver import resolve_value

        state = {
            "task_id": "t1",
            "workflow_id": "w1",
            "inputs": {"language": "en", "max_pages": 10},
            "outputs": {},
        }

        assert resolve_value("$.inputs.language", state) == "en"
        assert resolve_value("$.inputs.max_pages", state) == 10

    def test_resolve_files(self):
        """Test resolving $.files paths."""
        from fichero.workflows.resolver import resolve_value

        state = {
            "task_id": "t1",
            "workflow_id": "w1",
            "inputs": {},
            "outputs": {},
            "input_files": ["/path/a.jpg", "/path/b.jpg", "/path/c.jpg"],
        }

        assert resolve_value("$.files", state) == ["/path/a.jpg", "/path/b.jpg", "/path/c.jpg"]
        assert resolve_value("$.files[0]", state) == "/path/a.jpg"
        assert resolve_value("$.files[1]", state) == "/path/b.jpg"
        assert resolve_value("$.files[-1]", state) == "/path/c.jpg"

    def test_resolve_wildcard(self):
        """Test resolving [*] wildcard paths."""
        from fichero.workflows.resolver import resolve_value

        state = {
            "task_id": "t1",
            "workflow_id": "w1",
            "inputs": {},
            "outputs": {
                "process": {
                    "items": [
                        {"text": "one", "score": 1},
                        {"text": "two", "score": 2},
                        {"text": "three", "score": 3},
                    ]
                }
            },
        }

        # Extract text from all items
        result = resolve_value("$.nodes.process.items[*].text", state)
        assert result == ["one", "two", "three"]

        # Extract scores
        result = resolve_value("$.nodes.process.items[*].score", state)
        assert result == [1, 2, 3]

    def test_resolve_transforms(self):
        """Test transform pipe syntax."""
        from fichero.workflows.resolver import resolve_value

        state = {
            "task_id": "t1",
            "workflow_id": "w1",
            "inputs": {},
            "outputs": {
                "process": {
                    "texts": ["one", "two", "three"],
                    "name": "  hello world  ",
                }
            },
        }

        # join with comma
        result = resolve_value('$.nodes.process.texts | join(", ")', state)
        assert result == "one, two, three"

        # trim
        result = resolve_value("$.nodes.process.name | trim", state)
        assert result == "hello world"

        # upper
        result = resolve_value("$.nodes.process.name | trim | upper", state)
        assert result == "HELLO WORLD"

        # len
        result = resolve_value("$.nodes.process.texts | len", state)
        assert result == 3

        # first/last
        result = resolve_value("$.nodes.process.texts | first", state)
        assert result == "one"
        result = resolve_value("$.nodes.process.texts | last", state)
        assert result == "three"

    def test_resolve_inputs_dict(self):
        """Test resolving a full inputs dict."""
        from fichero.workflows.resolver import resolve_inputs

        state = {
            "task_id": "t1",
            "workflow_id": "w1",
            "inputs": {"language": "fr"},
            "outputs": {
                "transcribe": {"text": "Bonjour"}
            },
            "input_files": ["/a.jpg"],
        }

        input_mappings = {
            "text": "$.nodes.transcribe.text",
            "lang": "$.inputs.language",
            "files": "$.files",
            "count": 5,  # literal
        }

        resolved = resolve_inputs(input_mappings, state)

        assert resolved["text"] == "Bonjour"
        assert resolved["lang"] == "fr"
        assert resolved["files"] == ["/a.jpg"]
        assert resolved["count"] == 5

    def test_evaluate_condition(self):
        """Test condition evaluation."""
        from fichero.workflows.resolver import evaluate_condition

        state = {
            "task_id": "t1",
            "workflow_id": "w1",
            "inputs": {"skip": True},
            "outputs": {
                "check": {"count": 15, "is_valid": True}
            },
        }

        assert evaluate_condition("$.nodes.check.count > 10", state) is True
        assert evaluate_condition("$.nodes.check.count < 10", state) is False
        assert evaluate_condition("$.nodes.check.is_valid == true", state) is True
        assert evaluate_condition("$.inputs.skip == true", state) is True

    def test_json_parse(self):
        """Test JSON parsing transform."""
        from fichero.workflows.resolver import resolve_value

        state = {
            "task_id": "t1",
            "workflow_id": "w1",
            "inputs": {},
            "outputs": {
                "llm": {"response": '{"name": "test", "value": 42}'}
            },
        }

        result = resolve_value("$.nodes.llm.response | json", state)
        assert result == {"name": "test", "value": 42}

    def test_json_repair(self):
        """Test JSON repair transform."""
        from fichero.workflows.resolver import resolve_value

        state = {
            "task_id": "t1",
            "workflow_id": "w1",
            "inputs": {},
            "outputs": {
                "llm": {
                    # Common LLM issues: trailing comma, single quotes
                    "bad_json": "{'name': 'test', 'value': 42,}"
                }
            },
        }

        result = resolve_value("$.nodes.llm.bad_json | json_repair", state)
        assert result == {"name": "test", "value": 42}

    def test_json_extract(self):
        """Test JSON extraction from mixed text."""
        from fichero.workflows.resolver import resolve_value

        state = {
            "task_id": "t1",
            "workflow_id": "w1",
            "inputs": {},
            "outputs": {
                "llm": {
                    # LLM wrapped JSON in explanation
                    "response": 'Here is the result:\n{"name": "test"}\nHope this helps!'
                }
            },
        }

        result = resolve_value("$.nodes.llm.response | json_extract", state)
        assert result == {"name": "test"}

    def test_json_extract_code_block(self):
        """Test JSON extraction from markdown code block."""
        from fichero.workflows.resolver import resolve_value

        state = {
            "task_id": "t1",
            "workflow_id": "w1",
            "inputs": {},
            "outputs": {
                "llm": {
                    "response": '''Here is the JSON:
```json
{"items": [1, 2, 3]}
```
Let me know if you need anything else.'''
                }
            },
        }

        result = resolve_value("$.nodes.llm.response | json_extract", state)
        assert result == {"items": [1, 2, 3]}


# =============================================================================
# Type Tests
# =============================================================================

class TestWorkflowTypes:
    """Tests for workflow type definitions."""

    def test_state_structure(self):
        """Test State TypedDict has expected keys."""
        from fichero.workflows.types import State

        # Create a valid state
        state: State = {
            "task_id": "test-123",
            "workflow_id": "wf-456",
            "inputs": {"foo": "bar"},
            "outputs": {},
            "current_node": "",
            "completed_nodes": [],
            "error": None,
            "input_files": [],
            "output_files": [],
        }

        assert state["task_id"] == "test-123"
        assert state["workflow_id"] == "wf-456"

    def test_node_def(self):
        """Test NodeDef model."""
        from fichero.workflows.types import NodeDef

        node = NodeDef(
            id="transcribe-1",
            tool="transcribe",
            config={"language": "en"},
        )

        assert node.id == "transcribe-1"
        assert node.tool == "transcribe"
        assert node.config["language"] == "en"

    def test_edge_def(self):
        """Test EdgeDef model."""
        from fichero.workflows.types import EdgeDef

        edge = EdgeDef(
            source="node-1",
            target="node-2",
        )

        assert edge.source == "node-1"
        assert edge.target == "node-2"
        assert edge.source_port == "output"
        assert edge.target_port == "input"

    def test_workflow_def(self):
        """Test WorkflowDef model."""
        from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef

        workflow = WorkflowDef(
            id="wf-001",
            name="Test Workflow",
            description="A test workflow",
            nodes=[
                NodeDef(id="n1", tool="transcribe"),
                NodeDef(id="n2", tool="describe"),
            ],
            edges=[
                EdgeDef(source="n1", target="n2"),
            ],
        )

        assert workflow.id == "wf-001"
        assert workflow.name == "Test Workflow"
        assert len(workflow.nodes) == 2
        assert len(workflow.edges) == 1

    def test_workflow_entry_exit_nodes(self):
        """Test finding entry and exit nodes."""
        from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef

        workflow = WorkflowDef(
            id="wf-002",
            name="Multi-node Workflow",
            nodes=[
                NodeDef(id="start", tool="transcribe"),
                NodeDef(id="middle", tool="describe"),
                NodeDef(id="end", tool="summarize"),
            ],
            edges=[
                EdgeDef(source="start", target="middle"),
                EdgeDef(source="middle", target="end"),
            ],
        )

        assert workflow.get_entry_nodes() == ["start"]
        assert workflow.get_exit_nodes() == ["end"]


class TestToolRegistry:
    """Tests for tool registry."""

    def test_tools_registered(self):
        """Test that built-in tools are registered."""
        from fichero.workflows.registry import TOOLS, TOOL_DEFS

        assert "transcribe" in TOOLS
        assert "transcribe" in TOOL_DEFS

    def test_get_tool(self):
        """Test getting a tool by name."""
        from fichero.workflows.registry import get_tool

        tool = get_tool("transcribe")
        assert tool is not None
        assert callable(tool)

    def test_get_tool_def(self):
        """Test getting tool metadata."""
        from fichero.workflows.registry import get_tool_def

        tool_def = get_tool_def("transcribe")
        assert tool_def is not None
        assert tool_def.name == "transcribe"
        assert tool_def.category == "vision"
        assert tool_def.uses_llm is True

    def test_list_tools(self):
        """Test listing all tools."""
        from fichero.workflows.registry import list_tools

        tools = list_tools()
        assert len(tools) >= 1
        assert any(t.name == "transcribe" for t in tools)

    def test_list_tools_by_category(self):
        """Test listing tools by category."""
        from fichero.workflows.registry import list_tools_by_category

        vision_tools = list_tools_by_category("vision")
        assert len(vision_tools) >= 1
        assert all(t.category == "vision" for t in vision_tools)


class TestWorkflowBuilder:
    """Tests for workflow builder."""

    def test_build_graph(self):
        """Test building a LangGraph from workflow definition."""
        from fichero.workflows.builder import build_graph
        from fichero.workflows.types import WorkflowDef, NodeDef

        workflow = WorkflowDef(
            id="wf-build-test",
            name="Build Test",
            nodes=[
                NodeDef(id="node1", tool="transcribe"),
            ],
            edges=[],  # Single node, no edges
        )

        graph = build_graph(workflow)
        assert graph is not None

    def test_build_graph_with_edges(self):
        """Test building a graph with multiple nodes and edges."""
        from fichero.workflows.builder import build_graph
        from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef

        # Need to register a second tool for this test
        from fichero.workflows.registry import register_tool

        @register_tool(
            name="test_passthrough",
            display_name="Test Passthrough",
            category="utility",
        )
        async def test_passthrough(state, config, llm_config):
            return {"pass": True}

        workflow = WorkflowDef(
            id="wf-multi",
            name="Multi-node Test",
            nodes=[
                NodeDef(id="n1", tool="transcribe"),
                NodeDef(id="n2", tool="test_passthrough"),
            ],
            edges=[
                EdgeDef(source="n1", target="n2"),
            ],
        )

        graph = build_graph(workflow)
        assert graph is not None

    def test_build_graph_unknown_tool_raises(self):
        """Test that unknown tools raise an error."""
        from fichero.workflows.builder import build_graph
        from fichero.workflows.types import WorkflowDef, NodeDef

        workflow = WorkflowDef(
            id="wf-unknown",
            name="Unknown Tool Test",
            nodes=[
                NodeDef(id="node1", tool="nonexistent_tool"),
            ],
            edges=[],
        )

        with pytest.raises(ValueError, match="Unknown tool"):
            build_graph(workflow)


class TestTranscribeTool:
    """Tests for the transcribe tool."""

    @pytest.mark.asyncio
    async def test_transcribe_no_files(self):
        """Test transcribe with no input files returns error."""
        from fichero.workflows.tools.transcribe import transcribe
        from fichero.workflows.types import State
        from fichero.llm import LLMConfig

        state: State = {
            "task_id": "t1",
            "workflow_id": "w1",
            "inputs": {},
            "outputs": {},
            "current_node": "",
            "completed_nodes": [],
            "error": None,
            "input_files": [],
            "output_files": [],
        }

        inputs = {}  # No files specified
        llm_config = LLMConfig(provider="openai", model="gpt-4o")

        result = await transcribe(inputs, state, llm_config)

        assert result["text"] == ""
        assert "error" in result

    @pytest.mark.asyncio
    async def test_transcribe_builds_prompt(self):
        """Test transcribe prompt building."""
        from fichero.workflows.tools.transcribe import _build_transcription_prompt

        prompt = _build_transcription_prompt("en", False)
        assert "English" in prompt or "en" in prompt
        assert "transcribe" in prompt.lower() or "extract" in prompt.lower()

        prompt_with_boxes = _build_transcription_prompt("en", True)
        assert "bounding box" in prompt_with_boxes.lower()

    def test_file_to_data_uri(self):
        """Test file to data URI conversion."""
        import tempfile
        from pathlib import Path
        from fichero.workflows.tools.transcribe import _file_to_data_uri

        # Create a temporary test file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake png data")
            temp_path = f.name

        try:
            uri = _file_to_data_uri(temp_path)
            assert uri.startswith("data:image/png;base64,")
        finally:
            Path(temp_path).unlink()
