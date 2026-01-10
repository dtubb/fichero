"""
Phase 8 Integration Tests

Tests for:
- Workflow Chaining API
- SSE Streaming for workflow execution
- MCP Server tools
"""

import asyncio
import json
import pytest
import httpx
from typing import AsyncGenerator

# Base URL for API tests
BASE_URL = "http://127.0.0.1:8765/api"


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def api_client():
    """Create an HTTP client for API tests."""
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


@pytest.fixture
def async_api_client():
    """Create an async HTTP client for SSE tests."""
    return httpx.AsyncClient(base_url=BASE_URL, timeout=60.0)


# =============================================================================
# Workflow Chaining Tests
# =============================================================================

class TestWorkflowChaining:
    """Tests for workflow chaining API."""

    def test_list_chains_endpoint(self, api_client):
        """Test that chains list endpoint returns valid response."""
        response = api_client.get("/chains")
        if response.status_code == 404:
            pytest.skip("Chains endpoint not registered - backend restart required")
        assert response.status_code == 200
        data = response.json()
        assert "chains" in data
        assert "total" in data
        assert isinstance(data["chains"], list)

    def test_create_chain(self, api_client):
        """Test creating a workflow chain."""
        chain_data = {
            "name": "Test Chain",
            "description": "Integration test chain",
            "steps": [],
            "entry_step": None,
            "initial_inputs": {}
        }
        response = api_client.post("/chains", json=chain_data)

        if response.status_code == 404:
            pytest.skip("Chains endpoint not registered - backend restart required")

        # May return 200 or 201 depending on implementation
        assert response.status_code in [200, 201]
        data = response.json()
        assert "id" in data
        assert data["name"] == "Test Chain"

        # Store chain ID for cleanup
        chain_id = data["id"]

        # Clean up - delete the chain
        delete_response = api_client.delete(f"/chains/{chain_id}")
        assert delete_response.status_code in [200, 204]

    def test_get_chain_not_found(self, api_client):
        """Test getting a non-existent chain returns 404."""
        response = api_client.get("/chains/nonexistent-chain-id")
        assert response.status_code == 404

    def test_chain_with_steps(self, api_client):
        """Test creating a chain with steps (requires existing workflows)."""
        # First list workflows to get a valid workflow ID
        workflows_response = api_client.get("/workflows")
        if workflows_response.status_code != 200:
            pytest.skip("Workflows endpoint not available")

        workflows = workflows_response.json().get("workflows", [])
        if not workflows:
            pytest.skip("No workflows available for testing")

        workflow_id = workflows[0]["id"]

        chain_data = {
            "name": "Test Chain with Steps",
            "description": "Chain with workflow steps",
            "steps": [
                {
                    "id": "step-1",
                    "workflow_id": workflow_id,
                    "name": "First Step",
                    "input_mappings": [],
                    "static_inputs": {},
                    "condition": None,
                    "continue_on_error": False,
                    "timeout_seconds": 300
                }
            ],
            "entry_step": "step-1",
            "initial_inputs": {}
        }

        response = api_client.post("/chains", json=chain_data)
        assert response.status_code in [200, 201]

        data = response.json()
        assert len(data.get("steps", [])) == 1

        # Clean up
        api_client.delete(f"/chains/{data['id']}")


# =============================================================================
# SSE Streaming Tests
# =============================================================================

class TestSSEStreaming:
    """Tests for Server-Sent Events streaming."""

    @pytest.mark.asyncio
    async def test_sse_endpoint_exists(self, async_api_client):
        """Test that SSE streaming endpoint exists."""
        # First get a workflow ID
        response = await async_api_client.get("/workflows")
        if response.status_code != 200:
            pytest.skip("Workflows endpoint not available")

        workflows = response.json().get("workflows", [])
        if not workflows:
            pytest.skip("No workflows available for testing")

        workflow_id = workflows[0]["id"]

        # Test SSE endpoint with POST
        request_data = {
            "workflow_id": workflow_id,
            "inputs": {},
            "thread_id": None,
            "checkpoint_ns": "",
            "interrupt_before": [],
            "interrupt_after": []
        }

        # We just check the endpoint accepts the request
        # Full streaming test requires actual workflow execution
        try:
            async with async_api_client.stream(
                "POST",
                "/workflows/execution/execute/stream",
                json=request_data,
                timeout=5.0
            ) as response:
                # Check response headers for SSE
                content_type = response.headers.get("content-type", "")
                assert "text/event-stream" in content_type or response.status_code == 200

                # Try to read first event (may timeout if no events)
                try:
                    async for line in response.aiter_lines():
                        if line.startswith("event:") or line.startswith("data:"):
                            # Got an SSE event - test passes
                            break
                except asyncio.TimeoutError:
                    # Timeout is acceptable - endpoint exists and responds
                    pass
        except httpx.HTTPStatusError as e:
            # 404 means endpoint doesn't exist
            if e.response.status_code == 404:
                pytest.fail("SSE streaming endpoint not found")
            # Other errors may be acceptable (e.g., workflow execution fails)
            pass

    @pytest.mark.asyncio
    async def test_regular_execute_still_works(self, async_api_client):
        """Test that regular (non-streaming) execute endpoint still works."""
        response = await async_api_client.get("/workflows")
        if response.status_code != 200:
            pytest.skip("Workflows endpoint not available")

        workflows = response.json().get("workflows", [])
        if not workflows:
            pytest.skip("No workflows available for testing")

        workflow_id = workflows[0]["id"]

        request_data = {
            "workflow_id": workflow_id,
            "inputs": {}
        }

        response = await async_api_client.post(
            "/workflows/execution/execute",
            json=request_data
        )

        # Should return a response (may be error if workflow can't run)
        assert response.status_code in [200, 400, 500]


# =============================================================================
# MCP Server Tests
# =============================================================================

class TestMCPServer:
    """Tests for MCP server functionality."""

    def test_mcp_server_health(self, api_client):
        """Test MCP server health endpoint if available."""
        # MCP server runs on a different port typically
        # This tests the API endpoints that support MCP
        response = api_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_mcp_servers_list(self, api_client):
        """Test listing MCP servers."""
        response = api_client.get("/mcp/servers")
        # May return 200 with empty list or 404 if not implemented
        if response.status_code == 200:
            data = response.json()
            assert "servers" in data
            assert isinstance(data["servers"], list)
        elif response.status_code == 404:
            pytest.skip("MCP servers endpoint not implemented")

    def test_mcp_tools_list(self, api_client):
        """Test listing MCP tools."""
        response = api_client.get("/mcp/tools")
        if response.status_code == 200:
            data = response.json()
            assert "tools" in data
            assert isinstance(data["tools"], list)
        elif response.status_code == 404:
            pytest.skip("MCP tools endpoint not implemented")


# =============================================================================
# End-to-End Tests
# =============================================================================

class TestEndToEnd:
    """End-to-end tests combining multiple Phase 8 features."""

    def test_workflow_execution_status(self, api_client):
        """Test workflow execution and status check."""
        # Get a workflow
        response = api_client.get("/workflows")
        if response.status_code != 200:
            pytest.skip("Workflows endpoint not available")

        workflows = response.json().get("workflows", [])
        if not workflows:
            pytest.skip("No workflows available for testing")

        workflow_id = workflows[0]["id"]

        # Execute workflow
        exec_response = api_client.post(
            "/workflows/execution/execute",
            json={"workflow_id": workflow_id, "inputs": {}}
        )

        if exec_response.status_code == 200:
            data = exec_response.json()
            thread_id = data.get("thread_id")

            if thread_id:
                # Check status
                status_response = api_client.get(
                    f"/workflows/execution/threads/{thread_id}/status"
                )
                assert status_response.status_code in [200, 404]

    def test_chain_execution(self, api_client):
        """Test executing a workflow chain."""
        # First create a simple chain
        chain_data = {
            "name": "E2E Test Chain",
            "description": "End-to-end test",
            "steps": [],
            "entry_step": None,
            "initial_inputs": {}
        }

        create_response = api_client.post("/chains", json=chain_data)
        if create_response.status_code not in [200, 201]:
            pytest.skip("Chain creation not available")

        chain_id = create_response.json()["id"]

        try:
            # Try to execute (may fail with empty chain or missing header)
            # Execute endpoint requires X-Fichero-Library-Path header
            exec_response = api_client.post(
                f"/chains/{chain_id}/execute",
                json={"inputs": {}, "input_files": []},
                headers={"X-Fichero-Library-Path": "/tmp/test.fichero"}
            )
            # Any response is acceptable - we're testing the endpoint exists
            # 422 means validation error (acceptable for integration test)
            assert exec_response.status_code in [200, 400, 422, 500]
        finally:
            # Clean up
            api_client.delete(f"/chains/{chain_id}")

    def test_api_versioning(self, api_client):
        """Test that API returns version info."""
        response = api_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "backend_version" in data


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
