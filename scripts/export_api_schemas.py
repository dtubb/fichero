#!/usr/bin/env python3
"""
Export JSON schemas from Python Pydantic models for contract testing.

This script generates:
1. JSON Schema files for all API models
2. Sample JSON fixtures that both Python and Swift can validate against
3. A manifest of all models for test discovery

Usage:
    python scripts/export_api_schemas.py

Output:
    fichero-api/tests/contracts/schemas/      - JSON Schema files
    fichero-api/tests/contracts/fixtures/     - Sample JSON fixtures
    fichero-api/tests/contracts/manifest.json - Model manifest
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Any

# Add API src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "fichero-api" / "src"))

from fichero.workflows.types import (
    WorkflowDef,
    NodeDef,
    EdgeDef,
    PortDef,
    InputMapping,
    DataType,
)
from fichero.api.routes.workflows import (
    WorkflowResponse,
    ToolResponse,
    PortResponse,
)


def get_schema_with_examples(model_class) -> dict:
    """Get JSON schema with proper examples."""
    schema = model_class.model_json_schema()
    return schema


def create_sample_workflow_definition() -> dict:
    """Create a sample WorkflowDef for testing."""
    return {
        "id": "test-workflow-abc123",
        "name": "Test Workflow",
        "description": "A workflow for testing serialization",
        "provider": "openai",
        "model": "gpt-4o",
        "nodes": [
            {
                "id": "node-1",
                "tool": "transcribe",
                "label": "Transcribe Audio",
                "description": "Transcribes audio files to text",
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
                        "description": "Audio files to transcribe"
                    }
                ],
                "output_ports": [
                    {
                        "id": "text",
                        "name": "Text Output",
                        "port_type": "output",
                        "data_type": "text",
                        "required": True,
                        "description": "Transcribed text"
                    }
                ],
                "input_mappings": [],
                "inputs": {},
                "config": {},
            },
            {
                "id": "node-2",
                "tool": "summarize",
                "label": "Summarize",
                "description": "Summarizes text using LLM",
                "position_x": 350.0,
                "position_y": 200.0,
                "enabled": True,
                "input_ports": [
                    {
                        "id": "text",
                        "name": "Text",
                        "port_type": "input",
                        "data_type": "text",
                        "required": True,
                        "description": "Text to summarize"
                    }
                ],
                "output_ports": [
                    {
                        "id": "summary",
                        "name": "Summary",
                        "port_type": "output",
                        "data_type": "text",
                        "required": True,
                        "description": "Summarized text"
                    }
                ],
                "input_mappings": [
                    {
                        "port_id": "text",
                        "source_path": "$.nodes.node-1.text"
                    }
                ],
                "inputs": {},
                "config": {},
            }
        ],
        "edges": [
            {
                "id": "edge-1",
                "source": "node-1",
                "target": "node-2",
                "source_port": "text",
                "target_port": "text",
                "condition": None,
                "label": None,
                "animated": False
            }
        ],
        "folder_path": "/",
        "sort_order": 0,
        "timeout_seconds": 300,
        "max_retries": 3,
        "version": "1.0",
        "created_at": None,
        "updated_at": None
    }


def create_sample_workflow_with_nulls() -> dict:
    """Create a workflow with null values (as Swift might send)."""
    return {
        "id": "test-workflow-nulls",
        "name": "Workflow with Nulls",
        "description": "",
        "provider": "",
        "model": "",
        "nodes": [
            {
                "id": "node-null",
                "tool": "echo",
                "label": None,
                "description": None,
                "position_x": 0.0,
                "position_y": 0.0,
                "enabled": True,
                "input_ports": [],
                "output_ports": [],
                "input_mappings": None,  # Swift might send null
                "inputs": None,           # Swift might send null
                "config": None,           # Swift might send null
            }
        ],
        "edges": [],
        "folder_path": "/",
        "sort_order": 0
    }


def create_sample_tool_response() -> dict:
    """Create a sample ToolResponse."""
    return {
        "name": "transcribe",
        "display_name": "Transcribe Audio",
        "description": "Transcribes audio files to text using speech-to-text",
        "category": "vision",
        "icon": "waveform",
        "color": "blue",
        "input_ports": [
            {
                "id": "input",
                "name": "Audio Input",
                "port_type": "input",
                "data_type": "files",
                "required": True,
                "description": "Audio files to process"
            }
        ],
        "output_ports": [
            {
                "id": "text",
                "name": "Transcribed Text",
                "port_type": "output",
                "data_type": "text",
                "required": True,
                "description": "The transcribed text output"
            }
        ],
        "config_schema": {
            "type": "object",
            "properties": {
                "language": {"type": "string", "default": "en"}
            }
        },
        "default_output_schema": None,
        "uses_llm": False,
        "supports_batch": True,
        "supports_streaming": False,
        "supports_structured_output": False,
        "sort_order": 1
    }


def validate_fixture(model_class, fixture: dict) -> bool:
    """Validate a fixture against its Pydantic model."""
    try:
        model_class(**fixture)
        return True
    except Exception as e:
        print(f"Validation failed for {model_class.__name__}: {e}")
        return False


def main():
    # Create output directories
    base_dir = Path(__file__).parent.parent / "fichero-api" / "tests" / "contracts"
    schemas_dir = base_dir / "schemas"
    fixtures_dir = base_dir / "fixtures"

    schemas_dir.mkdir(parents=True, exist_ok=True)
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    # Export schemas
    models = [
        ("WorkflowDef", WorkflowDef),
        ("NodeDef", NodeDef),
        ("EdgeDef", EdgeDef),
        ("PortDef", PortDef),
        ("InputMapping", InputMapping),
    ]

    manifest = {
        "generated_at": datetime.now().isoformat(),
        "models": [],
        "fixtures": [],
    }

    print("Exporting JSON Schemas...")
    for name, model in models:
        schema = get_schema_with_examples(model)
        schema_path = schemas_dir / f"{name}.json"
        with open(schema_path, "w") as f:
            json.dump(schema, f, indent=2)
        print(f"  ✓ {name} -> {schema_path.name}")
        manifest["models"].append({
            "name": name,
            "schema_file": f"schemas/{name}.json"
        })

    # Create and validate fixtures
    fixtures = [
        ("workflow_complete.json", WorkflowDef, create_sample_workflow_definition()),
        ("workflow_with_nulls.json", WorkflowDef, create_sample_workflow_with_nulls()),
        ("tool_response.json", ToolResponse, create_sample_tool_response()),
    ]

    print("\nCreating and validating fixtures...")
    for filename, model, fixture in fixtures:
        if validate_fixture(model, fixture):
            fixture_path = fixtures_dir / filename
            with open(fixture_path, "w") as f:
                json.dump(fixture, f, indent=2)
            print(f"  ✓ {filename} (validates against {model.__name__})")
            manifest["fixtures"].append({
                "file": f"fixtures/{filename}",
                "model": model.__name__
            })
        else:
            print(f"  ✗ {filename} - validation failed!")

    # Write manifest
    manifest_path = base_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest written to {manifest_path}")

    print("\nContract testing files generated successfully!")
    print(f"  Schemas: {schemas_dir}")
    print(f"  Fixtures: {fixtures_dir}")
    print(f"  Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
