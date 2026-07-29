"""
Contract Tests for API Models

These tests ensure that the Python models can properly serialize/deserialize
the JSON fixtures that Swift also uses. This helps catch model sync issues
between frontend and backend.

Run with: pytest tests/unit/test_contract_models.py -v
"""

import json
import pytest
from pathlib import Path

from fichero_server.workflows.types import (
    WorkflowDef,
    NodeDef,
    EdgeDef,
    PortDef,
)


# Path to contract fixtures
CONTRACTS_DIR = Path(__file__).parent.parent.parent / "contracts"
FIXTURES_DIR = CONTRACTS_DIR / "fixtures"
SCHEMAS_DIR = CONTRACTS_DIR / "schemas"


class TestWorkflowDefContract:
    """Contract tests for WorkflowDef model."""

    def test_deserialize_complete_workflow(self):
        """Ensure Python can parse a complete workflow fixture."""
        fixture_path = FIXTURES_DIR / "workflow_complete.json"
        if not fixture_path.exists():
            pytest.skip("Contract fixtures not generated yet")

        with open(fixture_path) as f:
            data = json.load(f)

        # This should not raise
        workflow = WorkflowDef(**data)

        assert workflow.id == "test-workflow-abc123"
        assert workflow.name == "Test Workflow"
        assert len(workflow.nodes) == 2
        assert len(workflow.edges) == 1

    def test_deserialize_workflow_with_nulls(self):
        """Ensure Python handles null values from Swift correctly."""
        fixture_path = FIXTURES_DIR / "workflow_with_nulls.json"
        if not fixture_path.exists():
            pytest.skip("Contract fixtures not generated yet")

        with open(fixture_path) as f:
            data = json.load(f)

        # This should not raise - nulls should be converted to empty values
        workflow = WorkflowDef(**data)

        assert workflow.id == "test-workflow-nulls"
        assert len(workflow.nodes) == 1

        # Null values should be converted to empty defaults
        node = workflow.nodes[0]
        assert node.config == {}  # null -> empty dict
        assert node.inputs == {}  # null -> empty dict
        assert node.input_mappings == []  # null -> empty list

    def test_roundtrip_serialization(self):
        """Ensure model can be serialized and deserialized without loss."""
        fixture_path = FIXTURES_DIR / "workflow_complete.json"
        if not fixture_path.exists():
            pytest.skip("Contract fixtures not generated yet")

        with open(fixture_path) as f:
            original = json.load(f)

        # Deserialize
        workflow = WorkflowDef(**original)

        # Serialize back
        serialized = json.loads(workflow.model_dump_json())

        # Core fields should match
        assert serialized["id"] == original["id"]
        assert serialized["name"] == original["name"]
        assert len(serialized["nodes"]) == len(original["nodes"])
        assert len(serialized["edges"]) == len(original["edges"])


class TestNodeDefContract:
    """Contract tests for NodeDef model."""

    def test_node_with_all_fields(self):
        """Test node with all fields populated."""
        node_data = {
            "id": "node-123",
            "tool": "transcribe",
            "label": "Transcribe",
            "description": "Transcribes audio",
            "position_x": 100.0,
            "position_y": 200.0,
            "enabled": True,
            "input_ports": [
                {
                    "id": "input",
                    "name": "Input",
                    "port_type": "input",
                    "data_type": "files",
                    "required": True,
                    "description": ""
                }
            ],
            "output_ports": [],
            "input_mappings": [],
            "inputs": {"key": "value"},
            "config": {"option": True},
        }

        node = NodeDef(**node_data)

        assert node.id == "node-123"
        assert node.tool == "transcribe"
        assert len(node.input_ports) == 1
        assert node.config == {"option": True}

    def test_node_with_null_optional_fields(self):
        """Test that null optional fields are handled correctly."""
        node_data = {
            "id": "node-null",
            "tool": "echo",
            "label": None,
            "description": None,
            "position_x": 0.0,
            "position_y": 0.0,
            "enabled": True,
            "input_ports": None,  # Swift might send null
            "output_ports": None,
            "input_mappings": None,
            "inputs": None,
            "config": None,
        }

        node = NodeDef(**node_data)

        # Null values should be converted to empty defaults
        assert node.input_ports == []
        assert node.output_ports == []
        assert node.input_mappings == []
        assert node.inputs == {}
        assert node.config == {}


class TestEdgeDefContract:
    """Contract tests for EdgeDef model."""

    def test_edge_basic(self):
        """Test basic edge structure."""
        edge_data = {
            "id": "edge-1",
            "source": "node-1",
            "target": "node-2",
            "source_port": "output",
            "target_port": "input",
            "condition": None,
            "label": None,
            "animated": False
        }

        edge = EdgeDef(**edge_data)

        assert edge.source == "node-1"
        assert edge.target == "node-2"
        assert edge.condition is None

    def test_edge_with_condition(self):
        """Test edge with conditional routing."""
        edge_data = {
            "id": "edge-conditional",
            "source": "node-switch",
            "target": "node-branch-a",
            "source_port": "output",
            "target_port": "input",
            "condition": '$.nodes.classify.result == "invoice"',
            "label": "Invoice Branch",
            "animated": True
        }

        edge = EdgeDef(**edge_data)

        assert edge.condition == '$.nodes.classify.result == "invoice"'
        assert edge.label == "Invoice Branch"
        assert edge.animated is True


class TestPortDefContract:
    """Contract tests for PortDef model."""

    def test_port_all_data_types(self):
        """Test that all DataType enum values are accepted."""
        data_types = ["any", "files", "file", "text", "json", "array", "image", "number", "boolean"]

        for data_type in data_types:
            port_data = {
                "id": f"port-{data_type}",
                "name": f"Port {data_type}",
                "port_type": "input",
                "data_type": data_type,
                "required": True,
                "description": f"A {data_type} port"
            }

            port = PortDef(**port_data)
            assert port.data_type.value == data_type


class TestSwiftCompatibility:
    """Tests that simulate how Swift encodes workflow data."""

    def test_swift_style_workflow_encoding(self):
        """Test workflow encoded the way Swift's JSONEncoder does it."""
        # This mimics how Swift would encode a workflow
        swift_encoded = {
            "id": "swift-workflow-123",
            "name": "Swift Workflow",
            "description": "Created in Swift",
            "provider": "openai",
            "model": "gpt-4o",
            "nodes": [
                {
                    "id": "node-swift-1",
                    "tool": "transcribe",
                    "label": "Transcribe",
                    "description": None,  # Swift sends null for nil
                    "position_x": 150,    # Swift might send Int, not Float
                    "position_y": 200,
                    "enabled": True,
                    "input_ports": [
                        {
                            "id": "input",
                            "name": "Input",
                            "port_type": "input",
                            "data_type": "files",
                            "required": True,
                            "description": ""
                        }
                    ],
                    "output_ports": [],
                    "input_mappings": [],
                    # Swift might omit optional fields or send null
                    "config": None,
                    "provider_name": None,  # Extra field from Swift
                    "model_name": None,     # Extra field from Swift
                    "uses_llm": False       # Extra field from Swift
                }
            ],
            "edges": [],
            "folder_path": "/",
            "sort_order": 0
        }

        # Python should accept this without error
        workflow = WorkflowDef(**swift_encoded)

        assert workflow.name == "Swift Workflow"
        assert len(workflow.nodes) == 1
        assert workflow.nodes[0].config == {}  # null -> {}


class TestSchemaGeneration:
    """Tests for JSON Schema generation."""

    def test_schema_files_exist(self):
        """Verify schema files are generated."""
        if not SCHEMAS_DIR.exists():
            pytest.skip("Schema files not generated yet")

        expected_schemas = ["WorkflowDef.json", "NodeDef.json", "EdgeDef.json", "PortDef.json"]

        for schema_name in expected_schemas:
            schema_path = SCHEMAS_DIR / schema_name
            assert schema_path.exists(), f"Missing schema: {schema_name}"

            with open(schema_path) as f:
                schema = json.load(f)

            assert "type" in schema or "$defs" in schema, f"Invalid schema: {schema_name}"

    def test_manifest_exists(self):
        """Verify manifest file is generated."""
        manifest_path = CONTRACTS_DIR / "manifest.json"
        if not manifest_path.exists():
            pytest.skip("Manifest not generated yet")

        with open(manifest_path) as f:
            manifest = json.load(f)

        assert "models" in manifest
        assert "fixtures" in manifest
        assert len(manifest["models"]) > 0
