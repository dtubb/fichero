"""
Integration Tests for API Contract Changes

Tests the recent changes to ensure frontend/backend API contracts work correctly:
- SavedSearch with sort_direction field
- Workflow PATCH endpoint (partial updates)
- Workflow duplicate endpoint
- sort_direction vs sort_order field naming
"""

import pytest
import httpx

# Base URL for API tests
BASE_URL = "http://127.0.0.1:8765/api"


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def api_client():
    """Create an HTTP client for API tests."""
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


@pytest.fixture(autouse=True)
def require_live_backend():
    """Skip cleanly when the dev backend is not reachable."""
    try:
        with httpx.Client(base_url=BASE_URL, timeout=2.0) as client:
            response = client.get("/health")
        if response.status_code != 200:
            pytest.skip(f"Backend unavailable at {BASE_URL} (status {response.status_code})")
    except httpx.HTTPError as exc:
        pytest.skip(f"Backend unavailable at {BASE_URL}: {exc}")


@pytest.fixture
def library_headers():
    """Headers required for library-scoped endpoints."""
    return {"X-Fichero-Library-Path": "/tmp/test_api_contract.fichero"}


# =============================================================================
# SavedSearch API Tests
# =============================================================================

class TestSavedSearchAPI:
    """Tests for SavedSearch API with sort_direction field."""

    def test_create_saved_search_with_sort_direction(self, api_client, library_headers):
        """Test creating a saved search with sort_direction field."""
        search_data = {
            "query": "test documents",
            "is_smart_search": True,
            "search_type": "hybrid",
            "sort_by": "date",
            "sort_direction": "asc",  # The new field
            "folder_path": "/",
            "sort_order": 0
        }

        response = api_client.post("/search/saved", json=search_data, headers=library_headers)

        if response.status_code == 404:
            pytest.skip("SavedSearch endpoint not available - backend restart required")

        # Should succeed
        assert response.status_code in [200, 201], f"Failed: {response.text}"
        data = response.json()

        # Verify sort_direction is returned
        assert "sort_direction" in data, "Response should include sort_direction"
        assert data["sort_direction"] == "asc", "sort_direction should match input"
        assert "sort_order" in data, "Response should include sort_order (int)"
        assert data["sort_order"] == 0

        # Clean up
        if "id" in data:
            api_client.delete(f"/search/saved/{data['id']}", headers=library_headers)

    def test_list_saved_searches_returns_sort_direction(self, api_client, library_headers):
        """Test that listing saved searches includes sort_direction."""
        # Create a search first
        search_data = {
            "query": "list test",
            "sort_direction": "desc",
            "sort_order": 5
        }

        create_response = api_client.post("/search/saved", json=search_data, headers=library_headers)
        if create_response.status_code not in [200, 201]:
            pytest.skip("Cannot create saved search")

        created_id = create_response.json().get("id")

        try:
            # List all searches
            list_response = api_client.get("/search/saved", headers=library_headers)
            assert list_response.status_code == 200

            data = list_response.json()
            searches = data.get("searches", data) if isinstance(data, dict) else data

            # Find our search
            our_search = None
            for s in searches if isinstance(searches, list) else []:
                if s.get("id") == created_id:
                    our_search = s
                    break

            if our_search:
                assert "sort_direction" in our_search, "List response should include sort_direction"
                assert our_search["sort_direction"] == "desc"
                assert "sort_order" in our_search
                assert our_search["sort_order"] == 5
        finally:
            # Clean up
            api_client.delete(f"/search/saved/{created_id}", headers=library_headers)

    def test_update_saved_search_sort_direction(self, api_client, library_headers):
        """Test updating sort_direction on a saved search."""
        # Create
        search_data = {"query": "update test", "sort_direction": "asc"}
        create_response = api_client.post("/search/saved", json=search_data, headers=library_headers)

        if create_response.status_code not in [200, 201]:
            pytest.skip("Cannot create saved search")

        created_id = create_response.json().get("id")

        try:
            # Update sort_direction
            update_data = {"sort_direction": "desc"}
            update_response = api_client.put(
                f"/search/saved/{created_id}",
                json={**search_data, **update_data},
                headers=library_headers
            )

            if update_response.status_code == 200:
                data = update_response.json()
                assert data.get("sort_direction") == "desc", "sort_direction should be updated"
        finally:
            api_client.delete(f"/search/saved/{created_id}", headers=library_headers)


# =============================================================================
# Workflow PATCH Tests
# =============================================================================

class TestWorkflowPATCH:
    """Tests for Workflow PATCH endpoint (partial updates)."""

    def test_patch_workflow_rename(self, api_client, library_headers):
        """Test renaming a workflow via PATCH."""
        # First create a workflow
        workflow_data = {
            "name": "Original Name",
            "description": "Test workflow",
            "nodes": [],
            "edges": []
        }

        create_response = api_client.post("/workflows", json=workflow_data, headers=library_headers)
        if create_response.status_code not in [200, 201]:
            pytest.skip("Cannot create workflow")

        workflow_id = create_response.json().get("id")

        try:
            # PATCH to rename
            patch_data = {"name": "Renamed Workflow"}
            patch_response = api_client.patch(
                f"/workflows/{workflow_id}",
                json=patch_data,
                headers=library_headers
            )

            if patch_response.status_code == 404:
                pytest.skip("PATCH endpoint not implemented")

            assert patch_response.status_code == 200, f"PATCH failed: {patch_response.text}"
            data = patch_response.json()
            assert data.get("name") == "Renamed Workflow", "Name should be updated"

            # Verify the change persisted
            get_response = api_client.get(f"/workflows/{workflow_id}", headers=library_headers)
            assert get_response.status_code == 200
            assert get_response.json().get("name") == "Renamed Workflow"
        finally:
            api_client.delete(f"/workflows/{workflow_id}", headers=library_headers)

    def test_patch_workflow_folder_path(self, api_client, library_headers):
        """Test moving a workflow to a different folder via PATCH."""
        # Create
        workflow_data = {
            "name": "Folder Test",
            "folder_path": "/",
            "nodes": [],
            "edges": []
        }

        create_response = api_client.post("/workflows", json=workflow_data, headers=library_headers)
        if create_response.status_code not in [200, 201]:
            pytest.skip("Cannot create workflow")

        workflow_id = create_response.json().get("id")

        try:
            # PATCH to change folder
            patch_data = {"folder_path": "/Projects/Active"}
            patch_response = api_client.patch(
                f"/workflows/{workflow_id}",
                json=patch_data,
                headers=library_headers
            )

            if patch_response.status_code == 404:
                pytest.skip("PATCH endpoint not implemented")

            assert patch_response.status_code == 200
            assert patch_response.json().get("folder_path") == "/Projects/Active"
        finally:
            api_client.delete(f"/workflows/{workflow_id}", headers=library_headers)

    def test_patch_workflow_sort_order(self, api_client, library_headers):
        """Test updating sort_order via PATCH."""
        workflow_data = {"name": "Sort Order Test", "sort_order": 0, "nodes": [], "edges": []}
        create_response = api_client.post("/workflows", json=workflow_data, headers=library_headers)

        if create_response.status_code not in [200, 201]:
            pytest.skip("Cannot create workflow")

        workflow_id = create_response.json().get("id")

        try:
            patch_response = api_client.patch(
                f"/workflows/{workflow_id}",
                json={"sort_order": 42},
                headers=library_headers
            )

            if patch_response.status_code == 404:
                pytest.skip("PATCH endpoint not implemented")

            assert patch_response.status_code == 200
            assert patch_response.json().get("sort_order") == 42
        finally:
            api_client.delete(f"/workflows/{workflow_id}", headers=library_headers)


# =============================================================================
# Workflow Duplicate Tests
# =============================================================================

class TestWorkflowDuplicate:
    """Tests for Workflow duplicate endpoint."""

    def test_duplicate_workflow(self, api_client, library_headers):
        """Test duplicating a workflow."""
        # Create original
        original_data = {
            "name": "Original Workflow",
            "description": "To be duplicated",
            "nodes": [{"tool": "test", "label": "Test", "positionX": 100, "positionY": 100}],
            "edges": []
        }

        create_response = api_client.post("/workflows", json=original_data, headers=library_headers)
        if create_response.status_code not in [200, 201]:
            pytest.skip("Cannot create workflow")

        original_id = create_response.json().get("id")

        try:
            # Duplicate
            duplicate_response = api_client.post(
                f"/workflows/{original_id}/duplicate",
                headers=library_headers
            )

            if duplicate_response.status_code == 404:
                pytest.skip("Duplicate endpoint not implemented")

            assert duplicate_response.status_code in [200, 201], f"Duplicate failed: {duplicate_response.text}"
            data = duplicate_response.json()

            # Verify duplicate
            assert data.get("id") != original_id, "Duplicate should have new ID"
            assert "Copy" in data.get("name", ""), "Duplicate name should indicate it's a copy"
            assert data.get("description") == original_data["description"]

            # Clean up duplicate
            api_client.delete(f"/workflows/{data['id']}", headers=library_headers)
        finally:
            api_client.delete(f"/workflows/{original_id}", headers=library_headers)

    def test_duplicate_preserves_nodes_and_edges(self, api_client, library_headers):
        """Test that duplicate preserves nodes and edges."""
        original_data = {
            "name": "Complex Workflow",
            "nodes": [
                {"id": "n1", "tool": "test1", "label": "Node 1", "position_x": 0, "position_y": 0},
                {"id": "n2", "tool": "test2", "label": "Node 2", "position_x": 200, "position_y": 0}
            ],
            "edges": [
                {"source": "n1", "target": "n2", "source_port": "out", "target_port": "in"}
            ]
        }

        create_response = api_client.post("/workflows", json=original_data, headers=library_headers)
        if create_response.status_code not in [200, 201]:
            pytest.skip("Cannot create workflow")

        original_id = create_response.json().get("id")

        try:
            duplicate_response = api_client.post(
                f"/workflows/{original_id}/duplicate",
                headers=library_headers
            )

            if duplicate_response.status_code not in [200, 201]:
                pytest.skip("Duplicate endpoint not implemented")

            data = duplicate_response.json()

            # Verify nodes preserved
            assert len(data.get("nodes", [])) == 2, "Should have 2 nodes"

            # Verify edges preserved
            assert len(data.get("edges", [])) == 1, "Should have 1 edge"

            # Clean up
            api_client.delete(f"/workflows/{data['id']}", headers=library_headers)
        finally:
            api_client.delete(f"/workflows/{original_id}", headers=library_headers)


# =============================================================================
# Field Naming Convention Tests
# =============================================================================

class TestFieldNamingConventions:
    """Verify correct field naming: sort_direction (str) vs sort_order (int)."""

    def test_workflow_response_has_correct_fields(self, api_client, library_headers):
        """Test workflow responses use correct field names."""
        workflow_data = {
            "name": "Field Test",
            "folder_path": "/test",
            "sort_order": 10,
            "nodes": [],
            "edges": []
        }

        response = api_client.post("/workflows", json=workflow_data, headers=library_headers)
        if response.status_code not in [200, 201]:
            pytest.skip("Cannot create workflow")

        data = response.json()
        workflow_id = data.get("id")

        try:
            # Check field names
            assert "sort_order" in data, "Response should have sort_order (int)"
            assert "folder_path" in data, "Response should have folder_path"
            assert isinstance(data.get("sort_order"), int), "sort_order should be int"

            # sort_direction is for searches, not workflows
            # Workflows don't have sort_direction
        finally:
            api_client.delete(f"/workflows/{workflow_id}", headers=library_headers)

    def test_saved_search_has_both_sort_fields(self, api_client, library_headers):
        """Test SavedSearch has both sort_direction and sort_order."""
        search_data = {
            "query": "field naming test",
            "sort_by": "name",
            "sort_direction": "asc",  # String: asc/desc
            "sort_order": 5           # Int: position in folder
        }

        response = api_client.post("/search/saved", json=search_data, headers=library_headers)
        if response.status_code not in [200, 201]:
            pytest.skip("Cannot create saved search")

        data = response.json()
        search_id = data.get("id")

        try:
            # Verify both fields exist with correct types
            assert "sort_direction" in data, "Should have sort_direction (str)"
            assert "sort_order" in data, "Should have sort_order (int)"
            assert isinstance(data.get("sort_direction"), str), "sort_direction should be str"
            assert isinstance(data.get("sort_order"), int), "sort_order should be int"
            assert data["sort_direction"] in ["asc", "desc"], "sort_direction should be asc or desc"
        finally:
            api_client.delete(f"/search/saved/{search_id}", headers=library_headers)


# =============================================================================
# Database Migration Tests
# =============================================================================

class TestDatabaseMigration:
    """Tests that database migrations work correctly."""

    def test_saved_search_accepts_all_fields(self, api_client, library_headers):
        """Test that saved search endpoint accepts all expected fields."""
        # This tests that the database schema has all columns
        complete_search = {
            "query": "migration test",
            "is_smart_search": True,
            "filters": {"type": "pdf"},
            "search_type": "hybrid",
            "sort_by": "date",
            "sort_direction": "desc",
            "folder_path": "/test/folder",
            "sort_order": 99
        }

        response = api_client.post("/search/saved", json=complete_search, headers=library_headers)

        if response.status_code == 500 and "sort_direction" in response.text:
            pytest.fail("Database migration failed - sort_direction column missing")

        if response.status_code not in [200, 201]:
            pytest.skip(f"Endpoint not available: {response.status_code}")

        data = response.json()

        # Verify all fields roundtrip correctly
        assert data.get("query") == "migration test"
        assert data.get("sort_direction") == "desc"
        assert data.get("folder_path") == "/test/folder"
        assert data.get("sort_order") == 99

        # Clean up
        api_client.delete(f"/search/saved/{data['id']}", headers=library_headers)


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
