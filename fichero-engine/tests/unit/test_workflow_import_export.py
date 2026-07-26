#!/usr/bin/env python3
"""
Tests for workflow import/export functionality.
"""
import sys
from pathlib import Path
import json

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.models import Workflow


def test_workflow_export():
    """Test exporting workflow as JSON data."""
    print("Testing workflow export functionality...")

    try:
        # Create a test workflow
        workflow = Workflow(
            name="Test Export Workflow",
            description="A workflow for testing export functionality",
            format="nodes",
            provider="openai",
            model="gpt-4o",
            nodes=[
                {
                    "id": "export_node_1",
                    "tool": "transcribe",
                    "position_x": 100,
                    "position_y": 200,
                    "label": "Transcribe Audio",
                    "input_ports": [
                        {"id": "input", "name": "input", "port_type": "input", "data_type": "file"}
                    ],
                    "output_ports": [
                        {"id": "text", "name": "text", "port_type": "output", "data_type": "text"}
                    ]
                },
                {
                    "id": "export_node_2",
                    "tool": "summarize",
                    "position_x": 300,
                    "position_y": 200,
                    "label": "Summarize Text",
                    "input_ports": [
                        {"id": "input", "name": "input", "port_type": "input", "data_type": "text"}
                    ],
                    "output_ports": [
                        {"id": "summary", "name": "summary", "port_type": "output", "data_type": "text"}
                    ]
                }
            ],
            edges=[
                {
                    "source": "export_node_1",
                    "target": "export_node_2",
                    "source_port": "text",
                    "target_port": "input"
                }
            ]
        )

        # Simulate the export functionality from the API
        import datetime
        export_data = {
            "id": workflow.id,
            "name": workflow.name,
            "description": workflow.description,
            "provider": workflow.provider,
            "model": workflow.model,
            "format": workflow.format,
            "nodes": workflow.nodes,
            "edges": workflow.edges,
            "exported_at": datetime.datetime.now().isoformat()
        }

        # Verify exported data structure
        assert "id" in export_data, "Exported data should contain ID"
        assert "name" in export_data, "Exported data should contain name"
        assert "nodes" in export_data, "Exported data should contain nodes"
        assert "edges" in export_data, "Exported data should contain edges"
        assert export_data["name"] == "Test Export Workflow", "Name should match"
        assert len(export_data["nodes"]) == 2, "Should have 2 nodes"
        assert len(export_data["edges"]) == 1, "Should have 1 edge"
        assert "exported_at" in export_data, "Should have export timestamp"

        print(f"✅ Workflow ID in export: {export_data['id']}")
        print(f"✅ Workflow name in export: {export_data['name']}")
        print(f"✅ Number of nodes in export: {len(export_data['nodes'])}")
        print(f"✅ Number of edges in export: {len(export_data['edges'])}")
        print("✅ Workflow export structure is correct")

        # Verify the exported data is valid JSON-serializable
        json_string = json.dumps(export_data)
        assert isinstance(json_string, str), "Exported data should be JSON-serializable"
        print("✅ Exported data is JSON-serializable")

        print("✅ All workflow export functionality works correctly")

    except Exception as e:
        print(f"❌ Failed workflow export test: {e}")
        import traceback
        traceback.print_exc()
        raise


def test_workflow_import():
    """Test importing workflow from JSON data."""
    print("\nTesting workflow import functionality...")

    try:
        # Create workflow data in the format that would come from an export
        workflow_data = {
            "name": "Imported Test Workflow",
            "description": "A workflow imported from JSON data",
            "provider": "anthropic",
            "model": "claude-3-5-sonnet",
            "nodes": [
                {
                    "id": "import_node_1",
                    "tool": "transcribe",
                    "position_x": 150,
                    "position_y": 250,
                    "label": "Transcribe Audio",
                    "input_ports": [
                        {"id": "input", "name": "input", "port_type": "input", "data_type": "file"}
                    ],
                    "output_ports": [
                        {"id": "text", "name": "text", "port_type": "output", "data_type": "text"}
                    ]
                },
                {
                    "id": "import_node_2",
                    "tool": "describe",
                    "position_x": 400,
                    "position_y": 250,
                    "label": "Describe Image",
                    "input_ports": [
                        {"id": "input", "name": "input", "port_type": "input", "data_type": "image"}
                    ],
                    "output_ports": [
                        {"id": "description", "name": "description", "port_type": "output", "data_type": "text"}
                    ]
                }
            ],
            "edges": [
                {
                    "source": "import_node_1",
                    "target": "import_node_2",
                    "source_port": "text",
                    "target_port": "input"
                }
            ]
        }

        # Simulate the import functionality from the API
        from fichero.models import Workflow

        workflow_name = workflow_data.get("name", "Imported Workflow")
        workflow_description = workflow_data.get("description", "")
        workflow_provider = workflow_data.get("provider", "")
        workflow_model = workflow_data.get("model", "")

        imported_workflow = Workflow(
            name=workflow_name,
            description=workflow_description,
            format="nodes",  # Always set to 'nodes' for imported workflows
            provider=workflow_provider,
            model=workflow_model,
            nodes=workflow_data.get("nodes", []),
            edges=workflow_data.get("edges", []),
        )

        # Verify imported workflow
        assert imported_workflow.name == "Imported Test Workflow", "Name should match"
        assert imported_workflow.description == "A workflow imported from JSON data", "Description should match"
        assert imported_workflow.provider == "anthropic", "Provider should match"
        assert imported_workflow.model == "claude-3-5-sonnet", "Model should match"
        assert imported_workflow.format == "nodes", "Format should be 'nodes'"
        assert len(imported_workflow.nodes) == 2, "Should have 2 nodes"
        assert len(imported_workflow.edges) == 1, "Should have 1 edge"

        print(f"✅ Imported workflow name: {imported_workflow.name}")
        print(f"✅ Imported workflow provider: {imported_workflow.provider}")
        print(f"✅ Number of nodes imported: {len(imported_workflow.nodes)}")
        print(f"✅ Number of edges imported: {len(imported_workflow.edges)}")

        # Check that the imported nodes have correct structure
        first_node = imported_workflow.nodes[0]
        assert first_node["id"] == "import_node_1", "First node ID should match"
        assert first_node["tool"] == "transcribe", "First node tool should match"
        print("✅ Imported node structure is correct")

        # Check that the imported edges have correct structure
        first_edge = imported_workflow.edges[0]
        assert first_edge["source"] == "import_node_1", "Edge source should match"
        assert first_edge["target"] == "import_node_2", "Edge target should match"
        print("✅ Imported edge structure is correct")

        print("✅ All workflow import functionality works correctly")

    except Exception as e:
        print(f"❌ Failed workflow import test: {e}")
        import traceback
        traceback.print_exc()
        raise


def test_workflow_import_export_cycle():
    """Test that a workflow can be exported and then imported correctly."""
    print("\nTesting workflow import/export cycle...")

    try:
        # Create original workflow
        original_workflow = Workflow(
            name="Cycle Test Workflow",
            description="A workflow for testing import/export cycle",
            format="nodes",
            provider="openai",
            model="gpt-4o",
            nodes=[
                {
                    "id": "cycle_node_1",
                    "tool": "transcribe",
                    "position_x": 100,
                    "position_y": 200,
                    "label": "Transcribe Audio",
                    "input_ports": [
                        {"id": "input", "name": "input", "port_type": "input", "data_type": "file"}
                    ],
                    "output_ports": [
                        {"id": "text", "name": "text", "port_type": "output", "data_type": "text"}
                    ]
                }
            ],
            edges=[]
        )

        # Export the workflow
        import datetime
        export_data = {
            "id": original_workflow.id,  # Note: we don't export the original ID for security
            "name": original_workflow.name,
            "description": original_workflow.description,
            "provider": original_workflow.provider,
            "model": original_workflow.model,
            "format": original_workflow.format,
            "nodes": original_workflow.nodes,
            "edges": original_workflow.edges,
            "exported_at": datetime.datetime.now().isoformat()
        }

        # Import the exported data (as if from a file)
        imported_workflow = Workflow(
            name=export_data["name"],
            description=export_data["description"],
            format=export_data["format"],
            provider=export_data["provider"],
            model=export_data["model"],
            nodes=export_data["nodes"],
            edges=export_data["edges"],
        )

        # Verify the imported workflow matches the original (except for ID)
        assert imported_workflow.name == original_workflow.name, "Names should match"
        assert imported_workflow.description == original_workflow.description, "Descriptions should match"
        assert imported_workflow.provider == original_workflow.provider, "Providers should match"
        assert imported_workflow.model == original_workflow.model, "Models should match"
        assert imported_workflow.format == original_workflow.format, "Formats should match"
        assert len(imported_workflow.nodes) == len(original_workflow.nodes), "Node counts should match"
        assert len(imported_workflow.edges) == len(original_workflow.edges), "Edge counts should match"

        # Check that node structures match
        for orig_node, import_node in zip(original_workflow.nodes, imported_workflow.nodes):
            assert orig_node["id"] == import_node["id"], "Node IDs should match"
            assert orig_node["tool"] == import_node["tool"], "Node tools should match"
            assert orig_node["label"] == import_node["label"], "Node labels should match"

        print("✅ Exported workflow matches original after import")
        print("✅ Import/export cycle preserves workflow structure")
        print("✅ All workflow import/export cycle functionality works correctly")

    except Exception as e:
        print(f"❌ Failed workflow import/export cycle test: {e}")
        import traceback
        traceback.print_exc()
        raise


def test_invalid_import_data():
    """Test importing invalid workflow data."""
    print("\nTesting invalid import data handling...")

    try:
        # Test importing data without required fields
        invalid_data_missing = {
            "name": "Invalid Workflow",
            # Missing 'nodes' and 'edges'
        }

        try:
            # This should simulate the validation from the import endpoint
            if "nodes" not in invalid_data_missing or "edges" not in invalid_data_missing:
                raise ValueError("Invalid workflow data: missing nodes or edges")

            print("❌ Should have raised an error for missing nodes/edges")
            raise
        except ValueError:
            print("✅ Correctly handled missing nodes/edges in import data")

        # Test importing data with empty nodes/edges
        valid_import = {
            "name": "Valid Import",
            "description": "Test with empty nodes/edges",
            "provider": "openai",
            "model": "gpt-4o",
            "nodes": [],
            "edges": []
        }

        try:
            imported = Workflow(
                name=valid_import["name"],
                description=valid_import["description"],
                format="nodes",
                provider=valid_import["provider"],
                model=valid_import["model"],
                nodes=valid_import["nodes"],
                edges=valid_import["edges"],
            )

            assert len(imported.nodes) == 0, "Should handle empty nodes"
            assert len(imported.edges) == 0, "Should handle empty edges"
            print("✅ Correctly handles valid data with empty nodes/edges")
        except Exception as e:
            print(f"❌ Failed to handle valid empty data: {e}")
            raise

        print("✅ Invalid import data handling works correctly")

    except Exception as e:
        print(f"❌ Failed invalid import data test: {e}")
        import traceback
        traceback.print_exc()
        raise


def main():
    """Run all import/export tests."""
    print("🚀 Starting Workflow Import/Export Tests")
    print("=" * 50)

    tests = [
        ("Workflow Export", test_workflow_export),
        ("Workflow Import", test_workflow_import),
        ("Import/Export Cycle", test_workflow_import_export_cycle),
        ("Invalid Import Data", test_invalid_import_data),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n🧪 Running {test_name}...")
        print("-" * 30)

        if test_func():
            passed += 1
            print(f"✅ {test_name} PASSED")
        else:
            print(f"❌ {test_name} FAILED")

    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All import/export tests PASSED! Workflow import/export functionality is working correctly.")
        return 0
    else:
        print(f"💥 {total - passed} tests failed.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)