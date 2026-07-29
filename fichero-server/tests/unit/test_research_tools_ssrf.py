"""SSRF guards for research tool functions.

Tests the live workflow tools research_browser_navigate and research_document_fetch
directly, without depending on the /api/research/tools/* HTTP routes. This coverage
survives when those routers are later removed.
"""

import asyncio

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools.research import (
    research_browser_navigate,
    research_document_fetch,
)

_LLM = LLMConfig(provider="openai", model="gpt-4o-mini")


class TestResearchToolsDirectSSRFBlocking:
    """Direct URLs (localhost, RFC1918, metadata, file://) must be blocked before any HTTP request."""

    INTERNAL_IP_CASES = [
        ("http://127.0.0.1/", "loopback IPv4"),
        ("http://127.0.0.53/", "loopback IPv4 variant"),
        ("http://[::1]/", "loopback IPv6"),
        ("http://localhost/", "localhost hostname"),
        ("http://localhost:8080/api", "localhost with port"),
        ("http://10.0.0.1/", "private A (10.x)"),
        ("http://10.255.255.254/", "private A boundary"),
        ("http://172.16.0.1/", "private B (172.16-31)"),
        ("http://172.31.255.255/", "private B boundary"),
        ("http://192.168.0.1/", "private C (192.168.x)"),
        ("http://192.168.255.255/", "private C boundary"),
        ("http://169.254.169.254/", "AWS metadata endpoint"),
        ("http://169.254.169.254/latest/meta-data/", "AWS metadata path"),
        ("http://0.0.0.0/", "current network"),
        ("http://[::ffff:127.0.0.1]/", "IPv6 mapped IPv4 loopback"),
        ("http://[fe80::1]/", "IPv6 link-local"),
        ("http://[fc00::1]/", "IPv6 unique local"),
    ]

    SCHEME_BYPASS_CASES = [
        ("FILE:///etc/passwd", "uppercase FILE"),
        ("File:///etc/passwd", "mixed case"),
        ("fIlE:///etc/passwd", "mixed case 2"),
        ("fi%6ce:///etc/passwd", "URL-encoded scheme"),
        ("%66%69%6c%65:///etc/passwd", "fully URL-encoded scheme"),
        ("file:///etc/passwd%00", "null byte suffix"),
        ("file://x%00x/etc/passwd", "null byte in middle"),
    ]

    @pytest.mark.parametrize("url,description", INTERNAL_IP_CASES)
    def test_browser_navigate_blocks_internal_ips(self, url, description):
        result = asyncio.run(research_browser_navigate({"url": url}, {}, _LLM))
        assert result["error"], f"{description} ({url}) was not blocked"
        assert result["title"] is None
        assert result["html_content"] is None

    @pytest.mark.parametrize("url,description", INTERNAL_IP_CASES)
    def test_document_fetch_blocks_internal_ips(self, url, description):
        result = asyncio.run(
            research_document_fetch(
                {"url": url, "project_id": "p1", "create_as_source": False},
                {},
                _LLM,
            )
        )
        assert result["error"], f"{description} ({url}) was not blocked"
        assert result["success"] is False
        assert result["content"] is None

    @pytest.mark.parametrize("url,description", SCHEME_BYPASS_CASES)
    def test_browser_navigate_blocks_scheme_bypass(self, url, description):
        result = asyncio.run(research_browser_navigate({"url": url}, {}, _LLM))
        assert result["error"], f"{description} ({url}) was not blocked"

    @pytest.mark.parametrize("url,description", SCHEME_BYPASS_CASES)
    def test_document_fetch_blocks_scheme_bypass(self, url, description):
        result = asyncio.run(
            research_document_fetch(
                {"url": url, "project_id": "p1", "create_as_source": False},
                {},
                _LLM,
            )
        )
        assert result["error"], f"{description} ({url}) was not blocked"
        assert result["success"] is False


class TestResearchToolsRedirectSSRF:
    """Redirect targets must be re-validated against SSRF rules and capped."""

    @pytest.mark.asyncio
    async def test_browser_navigate_revalidates_redirect_target(self):
        requested_urls = []

        external_response = MagicMock()
        external_response.status_code = 302
        external_response.headers = {"location": "http://127.0.0.1:8765/"}
        external_response.url = httpx.URL("https://example.org/redirect")

        internal_response = MagicMock()
        internal_response.status_code = 200
        internal_response.headers = {"content-type": "text/html"}
        internal_response.text = "<title>internal</title>"
        internal_response.raise_for_status = Mock()

        async def mock_get(url, **kwargs):
            requested_urls.append(str(url))
            if "127.0.0.1" in str(url):
                return internal_response
            assert kwargs.get("follow_redirects") is False
            return external_response

        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.get = AsyncMock(side_effect=mock_get)

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            result = await research_browser_navigate(
                {"url": "https://example.org/redirect"}, {}, _LLM
            )

        assert "127.0.0.1" not in requested_urls
        assert "URL not allowed" in result["error"]

    @pytest.mark.asyncio
    async def test_document_fetch_revalidates_metadata_redirect_target(self):
        requested_urls = []

        redirect_response = MagicMock()
        redirect_response.status_code = 302
        redirect_response.headers = {
            "location": "http://169.254.169.254/latest/meta-data/"
        }
        redirect_response.url = httpx.URL("https://example.org/metadata-redirect")

        async def mock_get(url, **kwargs):
            requested_urls.append(str(url))
            assert kwargs.get("follow_redirects") is False
            return redirect_response

        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.get = AsyncMock(side_effect=mock_get)

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            result = await research_document_fetch(
                {
                    "url": "https://example.org/metadata-redirect",
                    "project_id": "p1",
                    "create_as_source": False,
                },
                {},
                _LLM,
            )

        assert "169.254.169.254" not in requested_urls
        assert result["success"] is False
        assert "URL not allowed" in result["error"]

    @pytest.mark.asyncio
    async def test_document_fetch_redirect_hop_cap_enforced(self):
        requested_urls = []

        async def mock_get(url, **kwargs):
            requested_urls.append(str(url))
            response = MagicMock()
            response.status_code = 302
            response.headers = {
                "location": f"https://example.org/hop-{len(requested_urls)}"
            }
            response.url = httpx.URL(str(url))
            return response

        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.get = AsyncMock(side_effect=mock_get)

        with patch("httpx.AsyncClient", return_value=mock_async_client):
            result = await research_document_fetch(
                {
                    "url": "https://example.org/start",
                    "project_id": "p1",
                    "create_as_source": False,
                },
                {},
                _LLM,
            )

        assert len(requested_urls) == 6
        assert result["success"] is False
        assert "Redirect limit exceeded" in result["error"]
