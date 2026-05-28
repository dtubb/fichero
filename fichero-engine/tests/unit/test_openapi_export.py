"""Regression tests for the OpenAPI export script.

The Swift client depends on workflow schema names staying stable. These tests
assert that the exporter canonicalizes NodeDef/EdgeDef and produces identical
output across repeated builds.
"""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path


def _load_exporter():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "export_openapi_schema.py"
    spec = importlib.util.spec_from_file_location("export_openapi_schema", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_openapi_export_is_deterministic_and_unified():
    exporter = _load_exporter()
    first = exporter.build_openapi_schema()
    second = exporter.build_openapi_schema()

    first_json = json.dumps(first, indent=2, sort_keys=True)
    second_json = json.dumps(second, indent=2, sort_keys=True)

    assert first_json == second_json
    assert "NodeDefInput" not in first_json
    assert "NodeDefOutput" not in first_json
    assert "EdgeDefInput" not in first_json
    assert "EdgeDefOutput" not in first_json

    schemas = first["components"]["schemas"]
    assert "NodeDef" in schemas
    assert "EdgeDef" in schemas
    assert "NodeDefInput" not in schemas
    assert "NodeDefOutput" not in schemas
    assert "EdgeDefInput" not in schemas
    assert "EdgeDefOutput" not in schemas
