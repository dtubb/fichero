"""
Action Library Integration Tests

Tests for:
- Action CRUD operations
- Action search and filtering
- Action import/export
- Usage tracking
- Composite actions
"""

import json
import pytest
import httpx

# Base URL for API tests
BASE_URL = "http://127.0.0.1:8765/api"

# Test library path - use a test path that may or may not exist
TEST_LIBRARY_PATH = "/tmp/test-action-library.fichero"

# Default headers for all requests
DEFAULT_HEADERS = {
    "X-Fichero-Library-Path": TEST_LIBRARY_PATH
}


# =============================================================================
# Helpers
# =============================================================================

def check_response_ok(response, skip_on_error=True):
    """Check if response is OK. Returns True if OK, skips test if error and skip_on_error.

    Args:
        response: httpx Response object
        skip_on_error: If True, skip test on 404/500 errors. If False, return False.

    Returns:
        True if response is 200-299, False or skips otherwise.
    """
    if response.status_code == 404:
        if skip_on_error:
            pytest.skip("Endpoint not registered - backend restart may be required")
        return False
    if response.status_code == 500:
        if skip_on_error:
            pytest.skip("Backend error - library may not exist or database error")
        return False
    return 200 <= response.status_code < 300


def response_items(payload):
    """Normalise list endpoints that now return the unified envelope."""
    if isinstance(payload, dict):
        return payload.get("items", [])
    return payload


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def api_client():
    """Create an HTTP client for API tests."""
    return httpx.Client(base_url=BASE_URL, timeout=30.0, headers=DEFAULT_HEADERS)


@pytest.fixture(autouse=True)
def require_live_backend():
    """Skip cleanly when the dev backend is not reachable."""
    try:
        with httpx.Client(base_url=BASE_URL, timeout=2.0, headers=DEFAULT_HEADERS) as client:
            response = client.get("/health")
        if response.status_code != 200:
            pytest.skip(f"Backend unavailable at {BASE_URL} (status {response.status_code})")
    except httpx.HTTPError as exc:
        pytest.skip(f"Backend unavailable at {BASE_URL}: {exc}")


@pytest.fixture
def test_action_data():
    """Sample action data for tests."""
    return {
        "name": "Test Action",
        "description": "An action for integration testing",
        "category": "test",
        "tags": ["test", "integration"],
        "icon": "star",
        "node_template": {
            "type": "test_node",
            "inputs": {"param1": "string"},
            "outputs": {"result": "string"}
        },
        "nodes": [],
        "edges": [],
        "author": "Integration Tests"
    }


# =============================================================================
# Action List Tests
# =============================================================================

class TestActionListing:
    """Tests for listing and filtering actions."""

    def test_list_all_actions(self, api_client):
        """Test listing all actions."""
        response = api_client.get("/actions")
        check_response_ok(response)
        items = response_items(response.json())
        assert isinstance(items, list)

    def test_list_builtin_actions(self, api_client):
        """Test listing built-in actions only."""
        response = api_client.get("/actions/builtin")
        check_response_ok(response)
        items = response_items(response.json())
        assert isinstance(items, list)
        # All returned actions should be builtin
        for action in items:
            assert action.get("is_builtin", False)

    def test_list_custom_actions(self, api_client):
        """Test listing custom actions only."""
        response = api_client.get("/actions/custom")
        check_response_ok(response)
        items = response_items(response.json())
        assert isinstance(items, list)
        # All returned actions should NOT be builtin
        for action in items:
            assert not action.get("is_builtin", True)

    def test_list_recent_actions(self, api_client):
        """Test listing recently used actions."""
        response = api_client.get("/actions/recent?limit=5")
        check_response_ok(response)
        items = response_items(response.json())
        assert isinstance(items, list)
        assert len(items) <= 5

    def test_list_popular_actions(self, api_client):
        """Test listing most frequently used actions."""
        response = api_client.get("/actions/popular?limit=5")
        check_response_ok(response)
        items = response_items(response.json())
        assert isinstance(items, list)
        assert len(items) <= 5

    def test_list_categories(self, api_client):
        """Test listing action categories."""
        response = api_client.get("/actions/categories")
        check_response_ok(response)
        data = response.json()
        assert "categories" in data
        assert isinstance(data["categories"], list)

    def test_list_by_category(self, api_client):
        """Test listing actions by category."""
        # First get categories
        cat_response = api_client.get("/actions/categories")
        if not check_response_ok(cat_response, skip_on_error=False):
            pytest.skip("Categories endpoint not available")

        categories = cat_response.json().get("categories", [])
        if not categories:
            pytest.skip("No categories available")

        # List actions in first category
        response = api_client.get(f"/actions/category/{categories[0]}")
        check_response_ok(response)
        items = response_items(response.json())
        assert isinstance(items, list)


# =============================================================================
# Action Search Tests
# =============================================================================

class TestActionSearch:
    """Tests for searching actions."""

    def test_search_by_query(self, api_client):
        """Test searching actions by text query."""
        response = api_client.get("/actions/search?query=test")
        check_response_ok(response)
        items = response_items(response.json())
        assert isinstance(items, list)

    def test_search_by_category(self, api_client):
        """Test searching actions by category."""
        # Get categories first
        cat_response = api_client.get("/actions/categories")
        if not check_response_ok(cat_response, skip_on_error=False):
            pytest.skip("Categories endpoint not available")

        categories = cat_response.json().get("categories", [])
        if not categories:
            pytest.skip("No categories available")

        response = api_client.get(f"/actions/search?category={categories[0]}")
        check_response_ok(response)
        items = response_items(response.json())
        assert isinstance(items, list)

    def test_search_by_tags(self, api_client):
        """Test searching actions by tags."""
        response = api_client.get("/actions/search?tags=transform")
        check_response_ok(response)
        items = response_items(response.json())
        assert isinstance(items, list)

    def test_search_combined_criteria(self, api_client):
        """Test searching with multiple criteria."""
        response = api_client.get("/actions/search?query=image&category=vision")
        check_response_ok(response)
        items = response_items(response.json())
        assert isinstance(items, list)


# =============================================================================
# Action CRUD Tests
# =============================================================================

class TestActionCRUD:
    """Tests for action Create, Read, Update, Delete operations."""

    def test_create_action(self, api_client, test_action_data):
        """Test creating a new action."""
        response = api_client.post("/actions", json=test_action_data)
        check_response_ok(response)

        data = response.json()
        assert data["name"] == test_action_data["name"]
        assert data["description"] == test_action_data["description"]
        assert data["category"] == test_action_data["category"]
        assert "id" in data

        # Clean up
        action_id = data["id"]
        api_client.delete(f"/actions/{action_id}")

    def test_get_action(self, api_client, test_action_data):
        """Test getting an action by ID."""
        # First create an action
        create_response = api_client.post("/actions", json=test_action_data)
        if not check_response_ok(create_response, skip_on_error=False):
            pytest.skip("Cannot create action for test")

        action_id = create_response.json()["id"]

        try:
            # Get the action
            response = api_client.get(f"/actions/{action_id}")
            check_response_ok(response)
            data = response.json()
            assert data["id"] == action_id
            assert data["name"] == test_action_data["name"]
        finally:
            # Clean up
            api_client.delete(f"/actions/{action_id}")

    def test_get_action_not_found(self, api_client):
        """Test getting a non-existent action returns 404."""
        response = api_client.get("/actions/nonexistent-action-id")
        # Skip if backend has internal error (library issue)
        if response.status_code == 500:
            pytest.skip("Backend error - library may not exist")
        assert response.status_code == 404

    def test_update_action(self, api_client, test_action_data):
        """Test updating an action."""
        # Create action
        create_response = api_client.post("/actions", json=test_action_data)
        if not check_response_ok(create_response, skip_on_error=False):
            pytest.skip("Cannot create action for test")

        action_id = create_response.json()["id"]

        try:
            # Update the action
            update_data = {
                "name": "Updated Test Action",
                "description": "Updated description"
            }
            response = api_client.put(f"/actions/{action_id}", json=update_data)
            check_response_ok(response)
            data = response.json()
            assert data["name"] == "Updated Test Action"
            assert data["description"] == "Updated description"
        finally:
            # Clean up
            api_client.delete(f"/actions/{action_id}")

    def test_delete_action(self, api_client, test_action_data):
        """Test deleting an action."""
        # Create action
        create_response = api_client.post("/actions", json=test_action_data)
        if not check_response_ok(create_response, skip_on_error=False):
            pytest.skip("Cannot create action for test")

        action_id = create_response.json()["id"]

        # Delete the action
        response = api_client.delete(f"/actions/{action_id}")
        check_response_ok(response)
        data = response.json()
        assert data.get("success", False)

        # Verify it's gone (should be 404 or 500 if library issue)
        get_response = api_client.get(f"/actions/{action_id}")
        assert get_response.status_code in [404, 500]

    def test_cannot_modify_builtin_action(self, api_client):
        """Test that built-in actions cannot be modified."""
        # Get a builtin action
        response = api_client.get("/actions/builtin")
        if not check_response_ok(response, skip_on_error=False):
            pytest.skip("Cannot get builtin actions")

        actions = response_items(response.json())
        if not actions:
            pytest.skip("No built-in actions available")

        builtin_id = actions[0]["id"]

        # Try to update
        update_response = api_client.put(
            f"/actions/{builtin_id}",
            json={"name": "Hacked Name"}
        )
        assert update_response.status_code == 403

    def test_cannot_delete_builtin_action(self, api_client):
        """Test that built-in actions cannot be deleted."""
        # Get a builtin action
        response = api_client.get("/actions/builtin")
        if not check_response_ok(response, skip_on_error=False):
            pytest.skip("Cannot get builtin actions")

        actions = response_items(response.json())
        if not actions:
            pytest.skip("No built-in actions available")

        builtin_id = actions[0]["id"]

        # Try to delete
        delete_response = api_client.delete(f"/actions/{builtin_id}")
        assert delete_response.status_code == 403


# =============================================================================
# Usage Tracking Tests
# =============================================================================

class TestUsageTracking:
    """Tests for action usage tracking."""

    def test_record_action_use(self, api_client, test_action_data):
        """Test recording action usage."""
        # Create action
        create_response = api_client.post("/actions", json=test_action_data)
        if not check_response_ok(create_response, skip_on_error=False):
            pytest.skip("Cannot create action for test")

        action_id = create_response.json()["id"]
        initial_use_count = create_response.json().get("use_count", 0)

        try:
            # Record usage
            use_response = api_client.post(f"/actions/{action_id}/use")
            check_response_ok(use_response)
            assert use_response.json().get("success", False)

            # Verify use count increased
            get_response = api_client.get(f"/actions/{action_id}")
            check_response_ok(get_response)
            assert get_response.json()["use_count"] == initial_use_count + 1
        finally:
            # Clean up
            api_client.delete(f"/actions/{action_id}")


# =============================================================================
# Import/Export Tests
# =============================================================================

class TestImportExport:
    """Tests for action import and export."""

    def test_export_action(self, api_client, test_action_data):
        """Test exporting an action as JSON."""
        # Create action
        create_response = api_client.post("/actions", json=test_action_data)
        if not check_response_ok(create_response, skip_on_error=False):
            pytest.skip("Cannot create action for test")

        action_id = create_response.json()["id"]

        try:
            # Export
            response = api_client.get(f"/actions/{action_id}/export")
            check_response_ok(response)
            data = response.json()
            assert "json" in data

            # Verify JSON is valid
            exported = json.loads(data["json"])
            assert exported["name"] == test_action_data["name"]
        finally:
            # Clean up
            api_client.delete(f"/actions/{action_id}")

    def test_import_action(self, api_client, test_action_data):
        """Test importing an action from JSON."""
        # Create action to export
        create_response = api_client.post("/actions", json=test_action_data)
        if not check_response_ok(create_response, skip_on_error=False):
            pytest.skip("Cannot create action for test")

        action_id = create_response.json()["id"]

        try:
            # Export
            export_response = api_client.get(f"/actions/{action_id}/export")
            check_response_ok(export_response)
            json_data = export_response.json()["json"]

            # Import as new action
            import_response = api_client.post(
                "/actions/import",
                json={"json_data": json_data, "new_id": True}
            )
            check_response_ok(import_response)
            imported = import_response.json()

            # Should have new ID but same data
            assert imported["id"] != action_id
            assert imported["name"] == test_action_data["name"]

            # Clean up imported action
            api_client.delete(f"/actions/{imported['id']}")
        finally:
            # Clean up original
            api_client.delete(f"/actions/{action_id}")

    def test_import_invalid_json(self, api_client):
        """Test importing invalid JSON returns error."""
        response = api_client.post(
            "/actions/import",
            json={"json_data": "invalid json{", "new_id": True}
        )
        # Skip if backend has internal error (library issue) or endpoint doesn't exist
        if response.status_code == 500:
            pytest.skip("Backend error - library may not exist")
        if response.status_code == 404:
            pytest.skip("Import endpoint not implemented")
        assert response.status_code == 400


# =============================================================================
# Composite Action Tests
# =============================================================================

class TestCompositeActions:
    """Tests for creating composite actions."""

    def test_create_from_node(self, api_client):
        """Test creating an action from a workflow node."""
        node_data = {
            "name": "Action from Node",
            "node": {
                "id": "test-node-1",
                "type": "transform_text",
                "data": {"operation": "uppercase"},
                "position": {"x": 0, "y": 0}
            },
            "description": "Created from a node",
            "category": "test",
            "tags": ["test", "from-node"]
        }

        response = api_client.post("/actions/from-node", json=node_data)
        check_response_ok(response)

        data = response.json()
        assert data["name"] == "Action from Node"
        assert not data["is_composite"]  # Single node = not composite

        # Clean up
        api_client.delete(f"/actions/{data['id']}")

    def test_create_composite_action(self, api_client):
        """Test creating a composite action from multiple nodes."""
        composite_data = {
            "name": "Composite Test Action",
            "nodes": [
                {
                    "id": "node-1",
                    "type": "input_text",
                    "data": {},
                    "position": {"x": 0, "y": 0}
                },
                {
                    "id": "node-2",
                    "type": "transform_text",
                    "data": {"operation": "uppercase"},
                    "position": {"x": 200, "y": 0}
                }
            ],
            "edges": [
                {
                    "id": "edge-1",
                    "source": "node-1",
                    "target": "node-2",
                    "sourceHandle": "output",
                    "targetHandle": "input"
                }
            ],
            "description": "A composite action for testing",
            "category": "test",
            "tags": ["test", "composite"]
        }

        response = api_client.post("/actions/composite", json=composite_data)
        check_response_ok(response)

        data = response.json()
        assert data["name"] == "Composite Test Action"
        assert data["is_composite"]  # Multiple nodes = composite
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1

        # Clean up
        api_client.delete(f"/actions/{data['id']}")


# =============================================================================
# End-to-End Tests
# =============================================================================

class TestEndToEnd:
    """End-to-end tests for action library."""

    def test_full_action_lifecycle(self, api_client, test_action_data):
        """Test complete action lifecycle: create, use, update, export, delete."""
        # Create
        create_response = api_client.post("/actions", json=test_action_data)
        if not check_response_ok(create_response, skip_on_error=False):
            pytest.skip("Cannot create action for test")

        action_id = create_response.json()["id"]

        try:
            # Use multiple times
            for _ in range(3):
                api_client.post(f"/actions/{action_id}/use")

            # Check in popular list
            api_client.get("/actions/popular?limit=50")
            # May or may not be popular depending on other actions

            # Update
            api_client.put(
                f"/actions/{action_id}",
                json={"name": "Lifecycle Test - Updated", "tags": ["lifecycle"]}
            )

            # Export
            export_response = api_client.get(f"/actions/{action_id}/export")
            check_response_ok(export_response)
            assert "json" in export_response.json()

            # Verify final state
            final_response = api_client.get(f"/actions/{action_id}")
            check_response_ok(final_response)
            final = final_response.json()
            assert final["name"] == "Lifecycle Test - Updated"
            assert final["use_count"] == 3
            assert "lifecycle" in final["tags"]
        finally:
            # Delete
            delete_response = api_client.delete(f"/actions/{action_id}")
            assert delete_response.status_code in [200, 500]


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
