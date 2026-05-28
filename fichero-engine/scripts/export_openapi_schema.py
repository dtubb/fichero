#!/usr/bin/env python3
"""
Export OpenAPI schema from FastAPI for contract testing.

This exports the AUTO-GENERATED OpenAPI schema from FastAPI.
The schema is derived directly from Pydantic models and route decorators,
so it's always in sync with the actual implementation.

Usage:
    python scripts/export_openapi_schema.py

    FICHERO_FEATURE_TIER=dev python scripts/export_openapi_schema.py
        # Export with dev feature tier (includes knowledge-graph, hermeneutics, mind-palace, research routes)

Output:
    fichero-engine/tests/contracts/openapi.json - Full OpenAPI 3.0 schema
    fichero-engine/tests/contracts/endpoints.json - Simplified endpoint list for Swift validation

The Swift app can validate its API calls against these files.
"""

import json
import sys
from pathlib import Path
from typing import Any

# Add API src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fichero.api.main import app


def convert_nullable_schemas(obj: dict | list) -> dict | list:
    """
    Convert OpenAPI 3.1 nullable patterns to 3.0 style for Swift compatibility.

    OpenAPI 3.1 uses: anyOf: [{type: string}, {type: null}]
    OpenAPI 3.0 uses: type: string, nullable: true

    Swift OpenAPI Generator handles 3.0 style better.
    """
    if isinstance(obj, list):
        return [convert_nullable_schemas(item) for item in obj]

    if not isinstance(obj, dict):
        return obj

    result = {}

    for key, value in obj.items():
        # Check for anyOf with null type (OpenAPI 3.1 nullable pattern)
        if key == "anyOf" and isinstance(value, list):
            non_null_types = [v for v in value if v.get("type") != "null"]
            has_null = any(v.get("type") == "null" for v in value)

            if has_null and len(non_null_types) == 1:
                # Convert to OpenAPI 3.0 nullable style
                converted = convert_nullable_schemas(non_null_types[0])
                if isinstance(converted, dict):
                    converted["nullable"] = True
                    result.update(converted)
                continue
            elif has_null and len(non_null_types) > 1:
                # Multiple types + null: keep as oneOf with nullable
                result["oneOf"] = [convert_nullable_schemas(t) for t in non_null_types]
                result["nullable"] = True
                continue

        # Recursively process nested objects
        result[key] = convert_nullable_schemas(value)

    return result


def _replace_schema_refs(obj: Any, ref_map: dict[str, str]) -> Any:
    """Recursively replace component $ref targets with canonical names."""
    if isinstance(obj, list):
        return [_replace_schema_refs(item, ref_map) for item in obj]

    if not isinstance(obj, dict):
        return obj

    result: dict[str, Any] = {}
    for key, value in obj.items():
        if key == "$ref" and isinstance(value, str):
            for alias, canonical in ref_map.items():
                alias_ref = f"#/components/schemas/{alias}"
                if value == alias_ref:
                    result[key] = f"#/components/schemas/{canonical}"
                    break
            else:
                result[key] = value
            continue
        result[key] = _replace_schema_refs(value, ref_map)
    return result


def _canonicalize_schema_aliases(openapi_schema: dict) -> None:
    """Collapse split workflow schema variants back to their canonical names."""
    ref_map = {
        "NodeDefInput": "NodeDef",
        "NodeDefOutput": "NodeDef",
        "EdgeDefInput": "EdgeDef",
        "EdgeDefOutput": "EdgeDef",
    }

    schemas = openapi_schema.setdefault("components", {}).setdefault("schemas", {})
    for alias, canonical in ref_map.items():
        alias_schema = schemas.pop(alias, None)
        if canonical not in schemas and alias_schema is not None:
            schemas[canonical] = alias_schema

    # Prefer the canonical model-json-schema injected by ensure_named_schemas
    # and rewrite any lingering split refs in-place.
    openapi_schema.update(_replace_schema_refs(openapi_schema, ref_map))


def extract_endpoints(openapi_schema: dict) -> dict:
    """
    Extract a simplified endpoint list from OpenAPI schema.

    This creates a Swift-friendly format for validating API calls.
    """
    endpoints = {}

    for path, methods in sorted(openapi_schema.get("paths", {}).items()):
        # Remove /api prefix for cleaner paths
        clean_path = path.replace("/api", "", 1) if path.startswith("/api") else path

        for method, details in sorted(methods.items()):
            if method in ["get", "post", "put", "patch", "delete"]:
                # Group by first path segment (resource)
                segments = clean_path.strip("/").split("/")
                resource = segments[0] if segments else "root"

                if resource not in endpoints:
                    endpoints[resource] = []

                # Extract path parameters
                path_params = []
                for part in segments:
                    if part.startswith("{") and part.endswith("}"):
                        path_params.append(part[1:-1])

                # Extract query parameters
                query_params = []
                for param in sorted(details.get("parameters", []), key=lambda p: p.get("name", "")):
                    if param.get("in") == "query":
                        query_params.append({
                            "name": param["name"],
                            "required": param.get("required", False),
                            "type": param.get("schema", {}).get("type", "string")
                        })

                # Get request body schema reference
                request_model = None
                if "requestBody" in details:
                    content = details["requestBody"].get("content", {})
                    json_content = content.get("application/json", {})
                    schema = json_content.get("schema", {})
                    if "$ref" in schema:
                        request_model = schema["$ref"].split("/")[-1]

                # Get response schema reference
                response_model = None
                responses = details.get("responses", {})
                success_response = responses.get("200") or responses.get("201")
                if success_response:
                    content = success_response.get("content", {})
                    json_content = content.get("application/json", {})
                    schema = json_content.get("schema", {})
                    if "$ref" in schema:
                        response_model = schema["$ref"].split("/")[-1]
                    elif "items" in schema and "$ref" in schema.get("items", {}):
                        response_model = f"[{schema['items']['$ref'].split('/')[-1]}]"

                endpoints[resource].append({
                    "method": method.upper(),
                    "path": clean_path,
                    "operation_id": details.get("operationId"),
                    "summary": details.get("summary"),
                    "path_params": path_params,
                    "query_params": query_params,
                    "request_model": request_model,
                    "response_model": response_model,
                })

    for resource, entries in list(endpoints.items()):
        endpoints[resource] = sorted(
            entries,
            key=lambda entry: (entry["path"], entry["method"], entry.get("operation_id") or ""),
        )

    return dict(sorted(endpoints.items()))


def build_openapi_schema() -> dict:
    """Build the canonical OpenAPI schema used for contracts and Swift sync."""
    # Get OpenAPI schema from FastAPI app
    openapi_schema = app.openapi()

    # #1275: guarantee Swift-hand-wrapped nested models are always named components
    # (FastAPI nested-model emission is non-deterministic across feature tiers).
    from fichero.workflows.types import EdgeDef, NodeDef
    ensure_named_schemas(openapi_schema, [NodeDef, EdgeDef])
    _canonicalize_schema_aliases(openapi_schema)

    # Convert nullable schemas for Swift compatibility
    openapi_schema = convert_nullable_schemas(openapi_schema)

    # Use OpenAPI 3.0.3 for better Swift compatibility (nullable is a 3.0 feature)
    openapi_schema["openapi"] = "3.0.3"
    return openapi_schema


def build_endpoints(openapi_schema: dict | None = None) -> dict:
    """Build the simplified endpoint listing from a canonical OpenAPI schema."""
    if openapi_schema is None:
        openapi_schema = build_openapi_schema()
    return extract_endpoints(openapi_schema)


def ensure_named_schemas(openapi_schema: dict, models: list) -> None:
    """Guarantee specific Pydantic models appear as named components/schemas.

    FastAPI only emits a nested model as a named component when it is reachable
    during schema generation, and that reachability is non-deterministic across
    feature tiers (#1275 — the export has produced inconsistent schemas on repeated
    runs since 2026-05-25). The Swift client hand-wraps Components.Schemas.NodeDef /
    EdgeDef, so a dropped definition breaks the macOS build. Inject each model's
    JSON schema (and its nested $defs) when absent, without clobbering a correct
    emission.
    """
    schemas = openapi_schema.setdefault("components", {}).setdefault("schemas", {})
    for model in models:
        js = model.model_json_schema(ref_template="#/components/schemas/{model}")
        for dname, dschema in js.pop("$defs", {}).items():
            schemas.setdefault(dname, dschema)
        schemas.setdefault(model.__name__, js)


def main():
    openapi_schema = build_openapi_schema()

    # Create output directory
    output_dir = Path(__file__).parent.parent / "tests" / "contracts"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save full OpenAPI schema
    openapi_path = output_dir / "openapi.json"
    with open(openapi_path, "w") as f:
        json.dump(openapi_schema, f, indent=2)
    print(f"✓ OpenAPI schema exported to {openapi_path}")

    # Extract and save simplified endpoints
    endpoints = build_endpoints(openapi_schema)
    endpoints_path = output_dir / "endpoints.json"
    with open(endpoints_path, "w") as f:
        json.dump({
            "generated_from": "FastAPI OpenAPI schema",
            "note": "This file is auto-generated. Do not edit manually.",
            "endpoints": endpoints
        }, f, indent=2)
    print(f"✓ Endpoints list exported to {endpoints_path}")

    # Print summary
    total_endpoints = sum(len(eps) for eps in endpoints.values())
    print(f"\nExported {total_endpoints} endpoints across {len(endpoints)} resources:")
    for resource, eps in sorted(endpoints.items()):
        print(f"  {resource}: {len(eps)} endpoints")


if __name__ == "__main__":
    main()
