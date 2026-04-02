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
    fichero-api/tests/contracts/openapi.json - Full OpenAPI 3.0 schema
    fichero-api/tests/contracts/endpoints.json - Simplified endpoint list for Swift validation

The Swift app can validate its API calls against these files.
"""

import json
import os
import sys
from pathlib import Path

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


def extract_endpoints(openapi_schema: dict) -> dict:
    """
    Extract a simplified endpoint list from OpenAPI schema.

    This creates a Swift-friendly format for validating API calls.
    """
    endpoints = {}

    for path, methods in openapi_schema.get("paths", {}).items():
        # Remove /api prefix for cleaner paths
        clean_path = path.replace("/api", "", 1) if path.startswith("/api") else path

        for method, details in methods.items():
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
                for param in details.get("parameters", []):
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

    return endpoints


def main():
    # Get OpenAPI schema from FastAPI app
    openapi_schema = app.openapi()

    # Convert nullable schemas for Swift compatibility
    openapi_schema = convert_nullable_schemas(openapi_schema)

    # Use OpenAPI 3.0.3 for better Swift compatibility (nullable is a 3.0 feature)
    openapi_schema["openapi"] = "3.0.3"

    # Create output directory
    output_dir = Path(__file__).parent.parent / "tests" / "contracts"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save full OpenAPI schema
    openapi_path = output_dir / "openapi.json"
    with open(openapi_path, "w") as f:
        json.dump(openapi_schema, f, indent=2)
    print(f"✓ OpenAPI schema exported to {openapi_path}")

    # Extract and save simplified endpoints
    endpoints = extract_endpoints(openapi_schema)
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
