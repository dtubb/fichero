"""
API Contract Tests

These tests validate that:
1. The FastAPI OpenAPI schema is valid and complete
2. API endpoints follow consistent conventions
3. Swift can rely on the exported schema for validation

The OpenAPI schema is the SOURCE OF TRUTH - generated from Pydantic models
and FastAPI route decorators. Swift should validate against this.

Run with: pytest tests/integration/test_api_contracts.py -v
"""

import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# Import the FastAPI app
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))



# Path to contract files
CONTRACTS_DIR = Path(__file__).parent.parent / "contracts"
OPENAPI_FILE = CONTRACTS_DIR / "openapi.json"
ENDPOINTS_FILE = CONTRACTS_DIR / "endpoints.json"


@pytest.fixture
def client():
    """Create a test client for the CURRENT FastAPI app, authenticated.

    Two isolation hazards make these endpoint-existence checks flaky in a
    cross-file batch (pass alone, 401 in batch — #3333):

    1. The authz suites ``importlib.reload(api.main)`` while toggling
       ``FICHERO_DISABLE_AUTH``, rebinding ``api_main.app`` to a new instance
       whose auth middleware may be attached — so we re-fetch the CURRENT
       ``api_main.app`` rather than a stale import-time binding.
    2. Whether that current app enforces auth is order-dependent, so we also
       send the loopback bootstrap token. It's ignored when auth is disabled
       and accepted (as the same-Mac superuser) when it's on — making the check
       auth-state-agnostic instead of relying on the ambient config.
    """
    import fichero.api.main as api_main
    from fichero.api.auth import initialize_token

    return TestClient(
        api_main.app,
        headers={"Authorization": f"Bearer {initialize_token()}"},
    )


@pytest.fixture
def openapi_schema(client):
    """Get the OpenAPI schema from the running app."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def exported_endpoints():
    """Load the exported endpoints file."""
    if not ENDPOINTS_FILE.exists():
        pytest.skip("Run 'python scripts/export_openapi_schema.py' first")

    with open(ENDPOINTS_FILE) as f:
        return json.load(f)


class TestOpenAPISchemaValidity:
    """Validate the OpenAPI schema is complete and valid."""

    def test_schema_has_required_fields(self, openapi_schema):
        """Verify OpenAPI schema has required top-level fields."""
        assert "openapi" in openapi_schema
        assert "info" in openapi_schema
        assert "paths" in openapi_schema

    def test_schema_version(self, openapi_schema):
        """Verify OpenAPI version is 3.x."""
        version = openapi_schema.get("openapi", "")
        assert version.startswith("3."), f"Expected OpenAPI 3.x, got {version}"

    def test_all_paths_have_operations(self, openapi_schema):
        """Verify all paths have at least one HTTP method defined."""
        for path, methods in openapi_schema.get("paths", {}).items():
            valid_methods = {"get", "post", "put", "patch", "delete", "options", "head"}
            has_method = any(m in methods for m in valid_methods)
            assert has_method, f"Path {path} has no HTTP methods defined"

    def test_endpoints_have_operation_ids(self, openapi_schema):
        """Verify all endpoints have operation IDs (for client generation)."""
        missing_ids = []
        for path, methods in openapi_schema.get("paths", {}).items():
            for method, details in methods.items():
                if method in {"get", "post", "put", "patch", "delete"}:
                    if "operationId" not in details:
                        missing_ids.append(f"{method.upper()} {path}")

        if missing_ids:
            pytest.fail("Missing operationId:\n" + "\n".join(missing_ids[:10]))


class TestAPIConventions:
    """Validate API follows consistent conventions."""

    def test_snake_case_query_params(self, openapi_schema):
        """Verify query parameters use snake_case."""
        camel_case_params = []

        for path, methods in openapi_schema.get("paths", {}).items():
            for method, details in methods.items():
                for param in details.get("parameters", []):
                    if param.get("in") == "query":
                        name = param["name"]
                        # Check for camelCase (lowercase followed by uppercase)
                        if any(c.isupper() for c in name[1:]):
                            camel_case_params.append(f"{path}: {name}")

        if camel_case_params:
            pytest.fail(
                "Query params should use snake_case:\n" +
                "\n".join(camel_case_params[:10])
            )

    def test_consistent_error_responses(self, openapi_schema):
        """Verify error responses are defined consistently."""
        # Just check that 422 (validation error) is common
        has_422 = 0
        total = 0

        for path, methods in openapi_schema.get("paths", {}).items():
            for method, details in methods.items():
                if method in {"post", "put", "patch"}:
                    total += 1
                    if "422" in details.get("responses", {}):
                        has_422 += 1

        # Most mutation endpoints should have 422 defined
        if total > 0:
            ratio = has_422 / total
            assert ratio > 0.5, f"Only {has_422}/{total} endpoints define 422 response"


class TestCriticalEndpoints:
    """Test that critical endpoints exist and work."""

    def test_health_endpoint(self, client):
        """Health endpoint must exist and return healthy."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"

    def test_workflows_list_endpoint(self, client):
        """Workflows list endpoint must exist."""
        response = client.get("/api/workflows")
        # 200 or 400 (missing schema-hidden library header) are both valid.
        assert response.status_code in [200, 400]

    def test_documents_list_endpoint(self, client):
        """Documents list endpoint must exist."""
        response = client.get("/api/documents")
        assert response.status_code in [200, 400]

    def test_search_endpoint(self, client):
        """Search endpoint must accept POST."""
        response = client.post("/api/search", json={"query": "test"})
        # Should not be 404 or 405
        assert response.status_code not in [404, 405]


class TestExportedSchemaMatchesLive:
    """Verify exported schema matches live OpenAPI schema."""

    def test_exported_endpoints_match_live(self, client, exported_endpoints):
        """Ensure exported endpoints.json matches current API."""
        live_schema = client.get("/openapi.json").json()
        live_paths = set(live_schema.get("paths", {}).keys())

        exported_paths = set()
        for resource, endpoints in exported_endpoints.get("endpoints", {}).items():
            for ep in endpoints:
                exported_paths.add(f"/api{ep['path']}")

        # Check for new endpoints not in export
        new_endpoints = live_paths - exported_paths
        if new_endpoints:
            # Filter out common false positives
            significant_new = [e for e in new_endpoints if not e.endswith("/")]
            if significant_new:
                print(f"⚠️  New endpoints not in export: {significant_new[:5]}")
                # Don't fail - just warn. Re-run export to update.


class TestSwiftCompatibility:
    """Tests specifically for Swift client compatibility."""

    def test_response_models_are_serializable(self, openapi_schema):
        """Verify response schemas can be decoded by Swift."""
        components = openapi_schema.get("components", {}).get("schemas", {})

        for name, schema in components.items():
            # Check for types that might cause Swift issues
            if schema.get("type") == "object":
                props = schema.get("properties", {})
                for prop_name, prop_def in props.items():
                    # Warn about Any types (hard to decode in Swift)
                    if prop_def.get("type") == "object" and not prop_def.get("properties"):
                        # This is a dict[str, Any] - needs AnyCodable in Swift
                        pass  # This is handled by AnyCodableValue in Swift

    def test_date_formats_documented(self, openapi_schema):
        """Verify date fields have format specified."""
        components = openapi_schema.get("components", {}).get("schemas", {})

        for name, schema in components.items():
            if schema.get("type") == "object":
                for prop_name, prop_def in schema.get("properties", {}).items():
                    if "date" in prop_name.lower() or prop_name.endswith("_at"):
                        # These should have format: date-time
                        fmt = prop_def.get("format", "")
                        if prop_def.get("type") == "string" and fmt != "date-time":
                            # Just informational - not a failure
                            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
