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


def test_committed_contract_matches_the_code():
    """The committed contract IS what the engine serves, request and response shapes included (#4989).

    What breaks without it: on 2026-09-20 three routes (segments merge/split/carry) each gained a
    REQUIRED request field and every contract check stayed green, because they compared names,
    routes or the copies with each other, never the committed document with the code. The
    generated Swift client and the command-line surface went stale with nothing red. On 2026-09-30
    the same blind spot hid two new request headers on the group routes.

    ``info.version`` is left out: it is stamped from pyproject and has its own guard
    (``check_openapi_version_current.py``). The fix for a failure is the regeneration, never an edit:
    ``FICHERO_PYTHON_BIN=<venv>/bin/python ./fichero-server/scripts/sync_openapi_schema.sh``.
    """
    exporter = _load_exporter()
    live = json.loads(json.dumps(exporter.build_openapi_schema()))
    contract_path = Path(__file__).resolve().parents[2] / "contracts" / "openapi.json"
    committed = json.loads(contract_path.read_text(encoding="utf-8"))
    for document in (live, committed):
        document.get("info", {}).pop("version", None)

    drift = [
        f"{method.upper()} {path}"
        for path in sorted(set(live["paths"]) | set(committed["paths"]))
        for method in sorted(set(live["paths"].get(path, {})) | set(committed["paths"].get(path, {})))
        if live["paths"].get(path, {}).get(method) != committed["paths"].get(path, {}).get(method)
    ]
    live_schemas = live.get("components", {}).get("schemas", {})
    committed_schemas = committed.get("components", {}).get("schemas", {})
    drift += [
        f"schema {name}"
        for name in sorted(set(live_schemas) | set(committed_schemas))
        if live_schemas.get(name) != committed_schemas.get(name)
    ]
    drift += [
        f"top-level {key}"
        for key in sorted(set(live) | set(committed))
        if key not in {"paths", "components"} and live.get(key) != committed.get(key)
    ]
    assert not drift, (
        "The committed contract differs from the code at: " + ", ".join(drift[:25])
        + (f" (+{len(drift) - 25} more)" if len(drift) > 25 else "")
        + ". Regenerate with fichero-server/scripts/sync_openapi_schema.sh; never hand-edit."
    )
