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
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# Add API src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# OpenAPI is static; app construction should not contend with a running engine's
# app.duckdb lock.
if "FICHERO_BASE_PATH" not in os.environ:
    os.environ["FICHERO_BASE_PATH"] = tempfile.mkdtemp(
        prefix="fichero-openapi-export-"
    )

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


def convert_exclusive_bounds(obj: Any) -> Any:
    """Down-convert Pydantic numeric exclusive bounds for OpenAPI 3.0."""
    if isinstance(obj, list):
        return [convert_exclusive_bounds(item) for item in obj]
    if not isinstance(obj, dict):
        return obj
    result = {key: convert_exclusive_bounds(value) for key, value in obj.items()}
    for exclusive, inclusive in (("exclusiveMinimum", "minimum"), ("exclusiveMaximum", "maximum")):
        value = result.get(exclusive)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result[inclusive] = value
            result[exclusive] = True
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


def _ensure_split_variants(openapi_schema: dict, models: list) -> None:
    """Guarantee FastAPI split variants (ModelName-Input / ModelName-Output) are present.

    FastAPI / Pydantic v2 emits ``ModelName-Input`` and ``ModelName-Output``
    components when a model is used in both request bodies and response bodies.
    That emission is non-deterministic across feature tiers (#1275): some runs
    produce the split, others collapse to a single ``ModelName`` component.

    This function pins the split form deterministically:

    * ``ModelName`` is written from Pydantic's full schema (includes ``default``
      annotations) via ``ensure_named_schemas``, which is called just before this.
    * ``ModelName-Input`` and ``ModelName-Output`` are written as the FastAPI
      *input* variant — identical content but with ``default`` annotations stripped
      from nullable fields, matching what FastAPI emits for request-body parameters.

    Using ``setdefault`` means an already-present entry is never clobbered, so the
    function is idempotent and safe to call on both fresh and cached schemas.
    """
    import copy

    schemas = openapi_schema.setdefault("components", {}).setdefault("schemas", {})
    for model in models:
        canonical_name = model.__name__
        canonical_schema = schemas.get(canonical_name)
        if canonical_schema is None:
            continue

        # Build the input variant: same as canonical but with ``default: null``
        # removed from nullable properties (matches FastAPI's request-body emission).
        # Non-null defaults (e.g. ``default: ""`` or ``default: false``) are kept
        # so the Input variant matches the FastAPI-generated split form exactly.
        _SENTINEL = object()
        input_schema = copy.deepcopy(canonical_schema)
        for _prop_schema in input_schema.get("properties", {}).values():
            if _prop_schema.get("default", _SENTINEL) is None:
                _prop_schema.pop("default")

        schemas.setdefault(f"{canonical_name}-Input", input_schema)
        schemas.setdefault(f"{canonical_name}-Output", input_schema)


def _rewrite_nodedef_schema_refs(openapi_schema: dict) -> None:
    """Rewrite NodeDef $ref pointers in aggregate schemas to the split variants.

    After ``_ensure_split_variants`` adds ``NodeDef-Input`` / ``NodeDef-Output``,
    the schemas that *contain* NodeDef as a field still reference the plain
    ``#/components/schemas/NodeDef``.  FastAPI would normally emit split refs
    directly, but since we inject the split variants post-hoc, we must also
    rewrite the containing schemas.

    Rules (match FastAPI's natural behaviour):
    * ``WorkflowDef.nodes[].items.$ref`` → ``NodeDef-Input``   (request schema)
    * ``WorkflowResponse.nodes[].items.$ref`` → ``NodeDef-Output`` (response schema)
    """
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    _NODEDEF_REF = "#/components/schemas/NodeDef"

    def _rewrite_nodes_ref(schema_name: str, variant: str) -> None:
        schema = schemas.get(schema_name)
        if schema is None:
            return
        nodes_prop = schema.get("properties", {}).get("nodes", {})
        if nodes_prop.get("items", {}).get("$ref") == _NODEDEF_REF:
            nodes_prop["items"]["$ref"] = f"#/components/schemas/{variant}"

    _rewrite_nodes_ref("WorkflowDef", "NodeDef-Input")
    _rewrite_nodes_ref("WorkflowResponse", "NodeDef-Output")


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
    """Build the canonical OpenAPI schema used for contracts and Swift sync.

    Emission is pinned to the SPLIT form (#1275): ``NodeDef`` / ``EdgeDef`` are
    emitted as the canonical (Pydantic-derived, defaults-included) component AND
    as ``NodeDef-Input`` / ``NodeDef-Output`` (default-stripped) variants.  The
    Swift OpenAPI generator converts the hyphenated names to camel-case struct
    names (``NodeDefInput`` / ``NodeDefOutput``) which ``WorkflowServiceGenerated``
    references directly.

    Step order (must not be changed without updating _ensure_split_variants):
    1. Get raw FastAPI schema.
    2. Overwrite NodeDef with the Pydantic-canonical schema (ensure_named_schemas).
    3. Inject NodeDef-Input / NodeDef-Output split variants (strips null defaults).
    3b. Rewrite $refs in WorkflowDef/WorkflowResponse to the split variants.
    4. Convert 3.1 nullable patterns to 3.0 nullable:true (convert_nullable_schemas).
    5. Pin openapi version to 3.0.3.
    """
    # Get OpenAPI schema from FastAPI app
    openapi_schema = app.openapi()

    # Step 2: #1275 — overwrite NodeDef with the Pydantic canonical schema.
    # This guarantees NodeDef always has full default annotations regardless of
    # whether FastAPI happened to emit it.  EdgeDef is left as-is from FastAPI
    # (FastAPI always emits it and the Swift client only references EdgeDef, not a split).
    from fichero.workflows.types import NodeDef
    ensure_named_schemas(openapi_schema, [NodeDef])

    # Step 3: #1275 — inject deterministic NodeDef-Input / NodeDef-Output split variants.
    # The Swift OpenAPI generator converts NodeDef-Input → NodeDefInput and
    # NodeDef-Output → NodeDefOutput structs, which WorkflowServiceGenerated.swift
    # references directly.  EdgeDef does NOT need the split.
    # Must run BEFORE convert_nullable_schemas so the variant schemas go through
    # the same 3.1→3.0 nullable conversion as the canonical schema.
    _ensure_split_variants(openapi_schema, [NodeDef])

    # Step 3b: Rewrite $refs in aggregate schemas (WorkflowDef/WorkflowResponse) that
    # previously pointed to plain NodeDef — now point to the appropriate split variant.
    _rewrite_nodedef_schema_refs(openapi_schema)

    # Step 4: Convert nullable schemas for Swift compatibility
    openapi_schema = convert_nullable_schemas(openapi_schema)
    openapi_schema = convert_exclusive_bounds(openapi_schema)

    # Step 5: Use OpenAPI 3.0.3 for better Swift compatibility (nullable is a 3.0 feature)
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

    The model's own entry is always *overwritten* with the Pydantic-derived schema
    so that ``default`` annotations (e.g. ``default: null`` on nullable fields) are
    always present in the canonical ``ModelName`` component. The ``-Input`` /
    ``-Output`` split variants are added separately by ``_ensure_split_variants``
    and use a default-stripped copy.
    """
    schemas = openapi_schema.setdefault("components", {}).setdefault("schemas", {})
    for model in models:
        js = model.model_json_schema(ref_template="#/components/schemas/{model}")
        for dname, dschema in js.pop("$defs", {}).items():
            schemas.setdefault(dname, dschema)
        # Always overwrite so the canonical schema includes default annotations.
        schemas[model.__name__] = js


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
