"""Unit tests for Fichero MCP Server."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fichero.mcp_server import FicheroAPIClient, DEFAULT_API_URL, _route_tool, TOOLS


class TestFicheroAPIClient:
    """Tests for FicheroAPIClient."""

    def test_init_default_url(self):
        """Test initialization with default URL."""
        client = FicheroAPIClient()
        assert client.api_url == DEFAULT_API_URL
        assert client.library_path is None

    def test_init_custom_url(self):
        """Test initialization with custom URL."""
        client = FicheroAPIClient(api_url="http://custom:9000")
        assert client.api_url == "http://custom:9000"

    def test_init_url_trailing_slash_removed(self):
        """Test trailing slash is removed from URL."""
        client = FicheroAPIClient(api_url="http://custom:9000/")
        assert client.api_url == "http://custom:9000"

    def test_init_with_library_path(self):
        """Test initialization with library path."""
        client = FicheroAPIClient(library_path="/path/to/library.fichero")
        assert client.library_path == "/path/to/library.fichero"

    def test_get_headers_without_library(self):
        """Test headers without library path."""
        client = FicheroAPIClient()
        headers = client._get_headers()
        assert "Content-Type" in headers
        assert headers["Content-Type"] == "application/json"
        assert "X-Fichero-Library-Path" not in headers

    def test_get_headers_with_library(self):
        """Test headers with library path."""
        client = FicheroAPIClient(library_path="/test/lib.fichero")
        headers = client._get_headers()
        assert headers["X-Fichero-Library-Path"] == "/test/lib.fichero"


class TestAPIRequests:
    """Tests for API request handling."""

    @pytest.fixture
    def client(self):
        return FicheroAPIClient()

    @pytest.mark.asyncio
    async def test_api_request_get(self, client):
        """Test GET API request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"documents": []}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            result = await client.request("GET", "/documents")
            assert "documents" in result

    @pytest.mark.asyncio
    async def test_api_request_post(self, client):
        """Test POST API request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "test-123"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            result = await client.request("POST", "/workflows", data={"name": "Test"})
            assert result["id"] == "test-123"

    @pytest.mark.asyncio
    async def test_api_request_put(self, client):
        """Test PUT API request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"updated": True}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.put = AsyncMock(
                return_value=mock_response
            )
            result = await client.request("PUT", "/workflows/123", data={"name": "Updated"})
            assert result["updated"] is True

    @pytest.mark.asyncio
    async def test_api_request_delete(self, client):
        """Test DELETE API request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"deleted": True}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.delete = AsyncMock(
                return_value=mock_response
            )
            result = await client.request("DELETE", "/workflows/123")
            assert result["deleted"] is True

    @pytest.mark.asyncio
    async def test_api_request_error_status(self, client):
        """Test API request error handling for non-2xx status."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            result = await client.request("GET", "/documents")
            assert "error" in result
            assert "500" in result["error"]

    @pytest.mark.asyncio
    async def test_api_request_connection_error(self, client):
        """Test API request connection error handling."""
        import httpx

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            result = await client.request("GET", "/documents")
            assert "error" in result
            assert "Cannot connect" in result["error"]

    @pytest.mark.asyncio
    async def test_api_request_unknown_method(self, client):
        """Test API request with unknown HTTP method."""
        result = await client.request("OPTIONS", "/documents")
        assert "error" in result
        assert "Unknown method" in result["error"]


class TestToolRouting:
    """Tests for tool routing."""

    @pytest.fixture
    def mock_api_client(self):
        """Create a mock API client."""
        mock = AsyncMock()
        mock.request = AsyncMock(return_value={"status": "ok"})
        return mock

    @pytest.mark.asyncio
    async def test_route_health_tool(self, mock_api_client):
        """Test health check tool routing."""
        with patch("fichero.mcp_server.api_client", mock_api_client):
            result = await _route_tool("fichero_health", {})
            mock_api_client.request.assert_called_once_with("GET", "/health")

    @pytest.mark.asyncio
    async def test_route_list_documents(self, mock_api_client):
        """Test list documents tool routing."""
        with patch("fichero.mcp_server.api_client", mock_api_client):
            await _route_tool("fichero_list_documents", {"limit": 10, "folder_id": None})
            mock_api_client.request.assert_called_once_with(
                "GET", "/documents", params={"limit": 10}
            )

    @pytest.mark.asyncio
    async def test_route_search_documents(self, mock_api_client):
        """Test search documents tool routing."""
        with patch("fichero.mcp_server.api_client", mock_api_client):
            await _route_tool("fichero_search_documents", {"query": "test", "limit": 20})
            mock_api_client.request.assert_called_once_with(
                "GET", "/search", params={"query": "test", "limit": 20}
            )

    @pytest.mark.asyncio
    async def test_route_get_document(self, mock_api_client):
        """Test get document tool routing."""
        with patch("fichero.mcp_server.api_client", mock_api_client):
            await _route_tool("fichero_get_document", {"document_id": "doc-123"})
            mock_api_client.request.assert_called_once_with("GET", "/documents/doc-123")

    @pytest.mark.asyncio
    async def test_route_list_workflows(self, mock_api_client):
        """Test list workflows tool routing."""
        with patch("fichero.mcp_server.api_client", mock_api_client):
            await _route_tool("fichero_list_workflows", {"limit": 50})
            mock_api_client.request.assert_called_once_with(
                "GET", "/workflows", params={"limit": 50}
            )

    @pytest.mark.asyncio
    async def test_route_get_workflow(self, mock_api_client):
        """Test get workflow tool routing."""
        with patch("fichero.mcp_server.api_client", mock_api_client):
            await _route_tool("fichero_get_workflow", {"workflow_id": "wf-123"})
            mock_api_client.request.assert_called_once_with("GET", "/workflows/wf-123")

    @pytest.mark.asyncio
    async def test_route_create_workflow(self, mock_api_client):
        """Test create workflow tool routing."""
        with patch("fichero.mcp_server.api_client", mock_api_client):
            await _route_tool("fichero_create_workflow", {
                "name": "Test Workflow",
                "description": "A test",
                "nodes": [],
                "edges": [],
            })
            mock_api_client.request.assert_called_once_with(
                "POST", "/workflows", data={
                    "name": "Test Workflow",
                    "description": "A test",
                    "nodes": [],
                    "edges": [],
                }
            )

    @pytest.mark.asyncio
    async def test_route_run_workflow(self, mock_api_client):
        """Test run workflow tool routing."""
        with patch("fichero.mcp_server.api_client", mock_api_client):
            await _route_tool("fichero_run_workflow", {
                "workflow_id": "wf-1",
                "input_files": ["/path/to/file.pdf"],
                "inputs": {"key": "value"},
            })
            mock_api_client.request.assert_called_once_with(
                "POST", "/workflow-execution/execute", data={
                    "workflow_id": "wf-1",
                    "input_files": ["/path/to/file.pdf"],
                    "inputs": {"key": "value"},
                }
            )

    @pytest.mark.asyncio
    async def test_route_workflow_status(self, mock_api_client):
        """Test workflow status tool routing."""
        with patch("fichero.mcp_server.api_client", mock_api_client):
            await _route_tool("fichero_workflow_status", {"thread_id": "thread-123"})
            mock_api_client.request.assert_called_once_with(
                "GET", "/workflow-execution/status/thread-123"
            )

    @pytest.mark.asyncio
    async def test_route_create_batch(self, mock_api_client):
        """Test create batch tool routing."""
        with patch("fichero.mcp_server.api_client", mock_api_client):
            await _route_tool("fichero_create_batch", {
                "workflow_id": "wf-1",
                "file_paths": ["/a.pdf", "/b.pdf"],
                "concurrency": 2,
            })
            mock_api_client.request.assert_called_once_with(
                "POST", "/batches", data={
                    "workflow_id": "wf-1",
                    "file_paths": ["/a.pdf", "/b.pdf"],
                    "concurrency": 2,
                }
            )

    @pytest.mark.asyncio
    async def test_route_batch_status(self, mock_api_client):
        """Test batch status tool routing."""
        with patch("fichero.mcp_server.api_client", mock_api_client):
            await _route_tool("fichero_batch_status", {"batch_id": "batch-123"})
            mock_api_client.request.assert_called_once_with("GET", "/batches/batch-123")

    @pytest.mark.asyncio
    async def test_route_list_activities(self, mock_api_client):
        """Test list activities tool routing."""
        with patch("fichero.mcp_server.api_client", mock_api_client):
            await _route_tool("fichero_list_activities", {"status": "running", "limit": 20})
            mock_api_client.request.assert_called_once_with(
                "GET", "/activities", params={"status": "running", "limit": 20}
            )

    @pytest.mark.asyncio
    async def test_route_list_actions(self, mock_api_client):
        """Test list actions tool routing."""
        with patch("fichero.mcp_server.api_client", mock_api_client):
            await _route_tool("fichero_list_actions", {"category": "ai"})
            mock_api_client.request.assert_called_once_with(
                "GET", "/actions", params={"category": "ai"}
            )

    @pytest.mark.asyncio
    async def test_route_compare_models(self, mock_api_client):
        """Test model comparison tool routing."""
        with patch("fichero.mcp_server.api_client", mock_api_client):
            await _route_tool("fichero_compare_models", {
                "prompt": "What is AI?",
                "system_prompt": "Be concise",
            })
            mock_api_client.request.assert_called_once()
            call_args = mock_api_client.request.call_args
            assert call_args[0][0] == "POST"
            assert call_args[0][1] == "/model-comparison/compare"
            assert call_args[1]["data"]["prompt"] == "What is AI?"
            assert call_args[1]["data"]["system_prompt"] == "Be concise"

    @pytest.mark.asyncio
    async def test_route_list_tools(self, mock_api_client):
        """Test list tools routing."""
        mock_api_client.request.return_value = {"tools": [
            {"name": "llm", "category": "llm"},
            {"name": "transform", "category": "transform"},
        ]}
        with patch("fichero.mcp_server.api_client", mock_api_client):
            result = await _route_tool("fichero_list_tools", {"category": "llm"})
            mock_api_client.request.assert_called_once_with("GET", "/workflows/tools")
            # Should filter by category
            assert len(result["tools"]) == 1
            assert result["tools"][0]["category"] == "llm"

    @pytest.mark.asyncio
    async def test_route_unknown_tool(self, mock_api_client):
        """Test unknown tool returns error."""
        result = await _route_tool("unknown_tool", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]


class TestToolDefinitions:
    """Tests for tool definitions."""

    def test_tools_list_not_empty(self):
        """Test that tools list is not empty."""
        assert len(TOOLS) > 0

    def test_all_tools_have_required_fields(self):
        """Test all tools have name, description, and inputSchema."""
        for tool in TOOLS:
            assert tool.name is not None
            assert tool.description is not None
            assert tool.inputSchema is not None

    def test_tool_names_are_prefixed(self):
        """Test all tool names have fichero_ prefix."""
        for tool in TOOLS:
            assert tool.name.startswith("fichero_"), f"{tool.name} missing fichero_ prefix"

    def test_expected_tools_exist(self):
        """Test expected tools are defined."""
        tool_names = [t.name for t in TOOLS]
        expected_tools = [
            "fichero_list_documents",
            "fichero_search_documents",
            "fichero_get_document",
            "fichero_list_workflows",
            "fichero_get_workflow",
            "fichero_create_workflow",
            "fichero_run_workflow",
            "fichero_workflow_status",
            "fichero_create_batch",
            "fichero_batch_status",
            "fichero_list_activities",
            "fichero_list_actions",
            "fichero_compare_models",
            "fichero_list_tools",
            "fichero_health",
        ]
        for expected in expected_tools:
            assert expected in tool_names, f"Missing tool: {expected}"
