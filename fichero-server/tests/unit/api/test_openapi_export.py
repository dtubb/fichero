"""Regression tests for the OpenAPI export script.

The Swift client depends on workflow schema names staying stable. These tests
assert that the exporter deterministically emits the SPLIT NodeDef form
(NodeDef-Input / NodeDef-Output) and produces byte-identical output across
repeated builds.

Background (#1275): FastAPI's nested-model reachability is non-deterministic
across feature tiers, causing the schema to flip-flop between a unified
``NodeDef`` and a split ``NodeDef-Input`` / ``NodeDef-Output``.  The canonical
green-build form is SPLIT — ``WorkflowServiceGenerated.swift`` references
``Components.Schemas.NodeDefInput`` and ``Components.Schemas.NodeDefOutput``
which the Swift OpenAPI generator derives from ``NodeDef-Input`` /
``NodeDef-Output`` component names.
"""

from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys


def _load_exporter():
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "export_openapi_schema.py"
    spec = importlib.util.spec_from_file_location("export_openapi_schema", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_openapi_export_uses_temp_base_path(tmp_path: Path) -> None:
    """Schema export should succeed without the user's app.duckdb."""
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "export_openapi_schema.py"
    src_path = Path(__file__).resolve().parents[3] / "src"
    code = (
        "import importlib.util; "
        f"spec = importlib.util.spec_from_file_location('export_openapi_schema', {str(script_path)!r}); "
        "module = importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(module); "
        "paths = module.build_openapi_schema()['paths']; "
        "assert '/api/health' in paths"
    )
    env = os.environ.copy()
    env["FICHERO_BASE_PATH"] = str(tmp_path)
    env["PYTHONPATH"] = str(src_path)

    result = subprocess.run([sys.executable, "-c", code], env=env, check=True)
    assert result.returncode == 0


def test_openapi_export_is_deterministic_and_split():
    """Two consecutive exports must be byte-identical and in SPLIT form.

    SPLIT form means:
    * ``NodeDef-Input`` and ``NodeDef-Output`` are present as named components.
    * ``WorkflowDef.nodes`` references ``NodeDef-Input``.
    * ``WorkflowResponse.nodes`` references ``NodeDef-Output``.
    * No camelCase ``NodeDefInput`` / ``NodeDefOutput`` appear as raw strings
      (those are Swift struct names, not OpenAPI component names).
    * ``NodeDef`` is also present as the canonical defaults-included component.
    * ``EdgeDef`` is present (unified — no split needed for edges).
    """
    exporter = _load_exporter()
    first = exporter.build_openapi_schema()
    second = exporter.build_openapi_schema()

    first_json = json.dumps(first, indent=2, sort_keys=True)
    second_json = json.dumps(second, indent=2, sort_keys=True)

    # Determinism: two consecutive builds must be byte-identical.
    assert first_json == second_json, "build_openapi_schema() is not deterministic"

    schemas = first["components"]["schemas"]

    # SPLIT form: Input and Output variants must be present.
    assert "NodeDef-Input" in schemas, "NodeDef-Input component is missing"
    assert "NodeDef-Output" in schemas, "NodeDef-Output component is missing"

    # Canonical component must also be present.
    assert "NodeDef" in schemas, "NodeDef canonical component is missing"
    assert "EdgeDef" in schemas, "EdgeDef component is missing"

    # Edge does NOT need a split.
    assert "EdgeDef-Input" not in schemas, "unexpected EdgeDef-Input component"
    assert "EdgeDef-Output" not in schemas, "unexpected EdgeDef-Output component"

    # Aggregate schemas must reference the split variants, not the plain NodeDef.
    workflow_def_nodes = (
        schemas.get("WorkflowDef", {})
        .get("properties", {})
        .get("nodes", {})
        .get("items", {})
        .get("$ref")
    )
    assert workflow_def_nodes == "#/components/schemas/NodeDef-Input", (
        f"WorkflowDef.nodes.$ref should be NodeDef-Input, got {workflow_def_nodes!r}"
    )

    workflow_response_nodes = (
        schemas.get("WorkflowResponse", {})
        .get("properties", {})
        .get("nodes", {})
        .get("items", {})
        .get("$ref")
    )
    assert workflow_response_nodes == "#/components/schemas/NodeDef-Output", (
        f"WorkflowResponse.nodes.$ref should be NodeDef-Output, got {workflow_response_nodes!r}"
    )

    # NodeDef-Input and NodeDef-Output must be identical (FastAPI emits them as
    # the same schema for this model).
    assert schemas["NodeDef-Input"] == schemas["NodeDef-Output"], (
        "NodeDef-Input and NodeDef-Output should have identical content"
    )


def test_library_path_header_is_not_an_operation_parameter():
    """The library path is a transport header, not a generated client argument."""
    exporter = _load_exporter()
    schema = exporter.build_openapi_schema()

    offenders: list[str] = []
    forbidden_names = {"x-fichero-library-path", "x_fichero_library_path"}
    for path, methods in schema.get("paths", {}).items():
        for method, operation in methods.items():
            if not isinstance(operation, dict):
                continue
            for parameter in operation.get("parameters", []) or []:
                if str(parameter.get("name", "")).lower() in forbidden_names:
                    offenders.append(f"{method.upper()} {path}")

    assert offenders == []


def test_kg_query_and_export_surface_is_present():
    """The organized KG SPARQL/RDF surface should be discoverable in OpenAPI."""
    exporter = _load_exporter()
    schema = exporter.build_openapi_schema()
    paths = schema.get("paths", {})

    assert "/api/kg/query/examples" in paths
    assert "/api/kg/query/sparql" in paths
    assert "/api/kg/export/rdf" in paths
    assert "/api/kg/sparql" in paths
    assert paths["/api/kg/sparql"]["post"].get("deprecated") is True


def test_openapi_30_has_no_numeric_exclusive_bounds():
    exporter = _load_exporter()

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"exclusiveMinimum", "exclusiveMaximum"}:
                    assert not isinstance(item, (int, float)) or isinstance(item, bool)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(exporter.build_openapi_schema())
