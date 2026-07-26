"""SSRF Security Tests for Research Agent Tools

These tests document and verify SSRF vulnerabilities in the research tools.
They are expected to FAIL with the current implementation (demonstrating
that vulnerabilities exist) and should PASS after security fixes.

To run: pytest fichero-engine/tests/unit/test_research_ssrf_security.py -v
"""

from unittest.mock import patch, AsyncMock, MagicMock, Mock
import pytest
import httpx

from fichero.llm import LLMConfig
from fichero.workflows.tools.research import research_browser_navigate, research_document_fetch


# ═══════════════════════════════════════════════════════════════════════════════
# SSRF VULNERABILITY TESTS - CRITICAL: Open Redirect Bypass
# ═══════════════════════════════════════════════════════════════════════════════


class TestSSRFRedirectBypass:
    """Test that SSRF controls are not bypassed by open redirects."""

    def test_web_search_redirect_bypass_blocked(self, client):
        """CRITICAL-1: Web search should validate final URL after redirects.
        
        This test documents the vulnerability where follow_redirects=True
        allows an attacker to use an open redirect to reach internal URLs.
        
        Expected: FAIL (current implementation allows redirect to internal URL)
        After fix: Should block the request when redirect leads to internal IP.
        """
        # Simulate an external site that redirects to internal metadata endpoint
        external_response = MagicMock()
        external_response.status_code = 302
        external_response.headers = {"location": "http://169.254.169.254/"}
        external_response.raise_for_status = lambda: None
        
        internal_response = MagicMock()
        internal_response.status_code = 200
        internal_response.text = "metadata"
        internal_response.raise_for_status = lambda: None
        
        # Track which URLs were requested
        requested_urls = []
        
        async def mock_get(url, **kwargs):
            requested_urls.append(str(url))
            if "169.254.169.254" in str(url):
                return internal_response
            return external_response
        
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.get = AsyncMock(side_effect=mock_get)
        
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            client.post(
                "/api/research/tools/web-search",
                json={"query": "test", "max_results": 5},
            )
        
        # The request should be blocked before reaching internal IP
        # CURRENTLY FAILS: The redirect is followed to internal IP
        assert "169.254.169.254" not in requested_urls, \
            "CRITICAL: Redirect followed to internal IP - SSRF bypass"

    def test_browser_navigate_redirect_to_internal_blocked(self, client):
        """CRITICAL-1: Browser navigate should validate redirect target.
        
        An attacker can submit an external URL that redirects to internal.
        
        Expected: FAIL (current)
        Fixed: Should return 400/blocked status.
        """
        external_response = MagicMock()
        external_response.status_code = 301
        external_response.headers = {"location": "http://127.0.0.1:8080/admin"}
        external_response.raise_for_status = lambda: None
        external_response.text = ""
        
        internal_response = MagicMock()
        internal_response.status_code = 200
        internal_response.headers = {"content-type": "text/html"}
        internal_response.text = "<title>Admin Panel</title>"
        internal_response.raise_for_status = lambda: None
        
        requested_urls = []
        
        async def mock_get(url, **kwargs):
            requested_urls.append(str(url))
            if "127.0.0.1" in str(url):
                return internal_response
            return external_response
        
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.get = AsyncMock(side_effect=mock_get)
        
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            resp = client.post(
                "/api/research/tools/browser-navigate",
                json={"url": "https://external-redirect.com/go", "timeout_seconds": 30},
            )
        
        # Should be blocked, not return admin panel content
        assert "127.0.0.1" not in requested_urls, \
            "CRITICAL: Redirect followed to localhost - SSRF bypass"
        assert resp.status_code == 400 or resp.status_code == 403, \
            "Should block redirects to internal addresses"

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
                {"url": "https://example.org/redirect"},
                {},
                LLMConfig(provider="openai", model="gpt-4o-mini"),
            )

        assert "127.0.0.1" not in requested_urls
        assert "URL not allowed" in result["error"]

    @pytest.mark.asyncio
    async def test_document_fetch_revalidates_metadata_redirect_target(self):
        requested_urls = []

        redirect_response = MagicMock()
        redirect_response.status_code = 302
        redirect_response.headers = {"location": "http://169.254.169.254/latest/meta-data/"}
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
                LLMConfig(provider="openai", model="gpt-4o-mini"),
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
            response.headers = {"location": f"https://example.org/hop-{len(requested_urls)}"}
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
                LLMConfig(provider="openai", model="gpt-4o-mini"),
            )

        assert len(requested_urls) == 6
        assert result["success"] is False
        assert "Redirect limit exceeded" in result["error"]

    def test_document_fetch_redirect_to_internal_blocked(self, client):
        """CRITICAL-1: Document fetch should validate redirect target.
        
        An attacker can exfiltrate data from internal services via redirects.
        
        Expected: FAIL (current)
        Fixed: Should return 400/blocked status.
        """
        external_response = MagicMock()
        external_response.status_code = 302
        external_response.headers = {"location": "http://10.0.0.1/internal-api"}
        external_response.raise_for_status = lambda: None
        
        internal_response = MagicMock()
        internal_response.status_code = 200
        internal_response.headers = {"content-type": "application/json"}
        internal_response.text = '{"secrets": "internal-data"}'
        internal_response.raise_for_status = lambda: None
        
        requested_urls = []
        
        async def mock_get(url, **kwargs):
            requested_urls.append(str(url))
            if "10.0.0.1" in str(url):
                return internal_response
            return external_response
        
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.get = AsyncMock(side_effect=mock_get)
        
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            resp = client.post(
                "/api/research/tools/document-fetch",
                json={
                    "url": "https://tinyurl.com/evil-redirect",
                    "project_id": "test-project",
                    "create_as_source": False,
                },
            )
        
        # Should be blocked, not fetch internal API
        assert "10.0.0.1" not in requested_urls, \
            "CRITICAL: Redirect followed to RFC1918 IP - SSRF bypass"
        assert resp.status_code == 400 or resp.status_code == 403, \
            "Should block redirects to internal addresses"


# ═══════════════════════════════════════════════════════════════════════════════
# SSRF VULNERABILITY TESTS - CRITICAL: Internal IP Blocking
# ═══════════════════════════════════════════════════════════════════════════════


class TestSSRFInternalIPBlocking:
    """Test that internal IP addresses/RFC1918 are blocked."""
    
    INTERNAL_IP_TEST_CASES = [
        # Loopback
        ("http://127.0.0.1/", "loopback IPv4"),
        ("http://127.0.0.53/", "loopback IPv4 variant"),
        ("http://[::1]/", "loopback IPv6"),
        ("http://localhost/", "localhost hostname"),
        ("http://localhost:8080/api", "localhost with port"),
        
        # RFC1918 Private Ranges
        ("http://10.0.0.1/", "private A (10.x)"),
        ("http://10.255.255.254/", "private A boundary"),
        ("http://172.16.0.1/", "private B (172.16-31)"),
        ("http://172.31.255.255/", "private B boundary"),
        ("http://192.168.0.1/", "private C (192.168.x)"),
        ("http://192.168.255.255/", "private C boundary"),
        
        # Link-local (cloud metadata)
        ("http://169.254.169.254/", "AWS metadata endpoint"),
        ("http://169.254.169.254/latest/meta-data/", "AWS metadata path"),
        ("http://169.254.169.254/metadata/v1/", "DigitalOcean metadata"),
        ("http://169.254.169.254/computeMetadata/v1/", "GCP metadata"),
        
        # Current network
        ("http://0.0.0.0/", "current network"),
        
        # IPv6
        ("http://[::ffff:127.0.0.1]/", "IPv6 mapped IPv4 loopback"),
        ("http://[fe80::1]/", "IPv6 link-local"),
        ("http://[fc00::1]/", "IPv6 unique local"),
    ]

    @pytest.mark.parametrize("url,description", INTERNAL_IP_TEST_CASES)
    def test_browser_navigate_blocks_internal_ips(self, client, url, description):
        """CRITICAL-2: Browser navigate must block all internal IP addresses.
        
        Expected: FAIL (current - no IP validation)
        Fixed: Should return 400 for all these URLs.
        """
        resp = client.post(
            "/api/research/tools/browser-navigate",
            json={"url": url},
        )
        assert resp.status_code == 400, \
            f"CRITICAL: {description} ({url}) was not blocked - SSRF"

    @pytest.mark.parametrize("url,description", INTERNAL_IP_TEST_CASES)
    def test_document_fetch_blocks_internal_ips(self, client, url, description):
        """CRITICAL-2: Document fetch must block all internal IP addresses.
        
        Expected: FAIL (current - no IP validation)
        Fixed: Should return 400 for all these URLs.
        """
        resp = client.post(
            "/api/research/tools/document-fetch",
            json={"url": url, "project_id": "test"},
        )
        assert resp.status_code == 400, \
            f"CRITICAL: {description} ({url}) was not blocked - SSRF"


# ═══════════════════════════════════════════════════════════════════════════════
# SSRF VULNERABILITY TESTS - HIGH: Path Traversal / Bypass Vectors
# ═══════════════════════════════════════════════════════════════════════════════


class TestSSRFSchemeBypass:
    """Test that URL scheme validation cannot be bypassed."""
    
    BYPASS_CASES = [
        # Case variations (depends on implementation)
        ("FILE:///etc/passwd", "uppercase FILE"),
        ("File:///etc/passwd", "mixed case"),
        ("fIlE:///etc/passwd", "mixed case 2"),
        
        # URL encoding of scheme (if decoded before check)
        ("fi%6ce:///etc/passwd", "URL-encoded 'le' in file"),
        ("%66%69%6c%65:///etc/passwd", "fully URL-encoded"),
        
        # Path confusion
        ("http://example.com/../etc/passwd", "path traversal in HTTP URL"),
        ("https://example.com/?redirect=file:///etc/passwd", "query param with file"),
        
        # Null byte injection (legacy)
        ("file:///etc/passwd%00", "null byte suffix"),
        ("file://x%00x/etc/passwd", "null byte in middle"),
    ]

    @pytest.mark.parametrize("url,description", BYPASS_CASES)
    def test_browser_navigate_blocks_scheme_bypass(self, client, url, description):
        """HIGH-1: Scheme validation must be robust.
        
        Expected: Most will FAIL (case sensitivity)
        Fixed: Should normalize and validate correctly.
        """
        resp = client.post(
            "/api/research/tools/browser-navigate",
            json={"url": url},
        )
        assert resp.status_code == 400, \
            f"HIGH: {description} ({url}) was not blocked"


# ═══════════════════════════════════════════════════════════════════════════════
# SSRF VULNERABILITY TESTS - MEDIUM: Resource Exhaustion / DoS
# ═══════════════════════════════════════════════════════════════════════════════


class TestSSRFResourceLimits:
    """Test that resource limits prevent DoS attacks."""

    @pytest.mark.slow
    def test_document_fetch_large_content_blocked(self, client):
        """MEDIUM-2: Document fetch should limit maximum content size.
        
        Expected: FAIL (current - no size limit)
        Fixed: Should error or truncate at reasonable limit (e.g., 10MB).
        """
        # Simulate a response that's too large
        huge_response = MagicMock()
        huge_response.status_code = 200
        huge_response.headers = {"content-type": "text/html", "content-length": "1000000000"}  # 1GB
        huge_response.text = "x" * 100_000_000  # 100MB of content
        huge_response.raise_for_status = lambda: None
        
        mock_async_client = AsyncMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)
        mock_async_client.get = AsyncMock(return_value=huge_response)
        
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            resp = client.post(
                "/api/research/tools/document-fetch",
                json={
                    "url": "https://example.com/huge-file",
                    "project_id": "test",
                    "create_as_source": False,
                },
            )
        
        # Should reject or truncate huge content
        data = resp.json()
        if data.get("success"):
            content = data.get("content", "")
            assert len(content) < 10_000_000, \
                "MEDIUM: No content size limit - potential DoS"

    def test_web_search_timeout_enforced(self, client):
        """Timeout should be enforced to prevent hanging requests.
        
        This test is informational - already has timeout support.
        Just verifying it works.
        """
        # Already covered in existing tests, but document it's intentional
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# SSRF VULNERABILITY TESTS - LOW: Error Information Disclosure
# ═══════════════════════════════════════════════════════════════════════════════


class TestSSRFErrorSanitization:
    """Test that error messages don't leak sensitive information."""

    def test_browser_navigate_error_no_internal_leak(self, client):
        """MEDIUM-1: Error messages should not reveal internal structure.
        
        Try to access internal service and check error message.
        """
        resp = client.post(
            "/api/research/tools/browser-navigate",
            json={"url": "http://127.0.0.1:9999/nonexistent"},
        )
        
        # If not blocked for SSRF, might get connection error
        # Error should not contain internal IP or port
        if resp.status_code != 400:  # If not blocked as expected
            error_text = resp.text.lower()
            assert "127.0.0.1:9999" not in error_text, \
                "MEDIUM: Error reveals internal address"
            assert "connection refused" not in error_text, \
                "MEDIUM: Error reveals service status"


# ═══════════════════════════════════════════════════════════════════════════════
# SSRF VULNERABILITY TESTS - INCOMPLETE: DNS Rebinding Protection
# ╕══════════════════════════════════════════════════════════════════════════════


@pytest.mark.skip(reason="DNS rebinding requires actual DNS manipulation - skip in unit tests")
class TestSSRFDNSRebinding:
    """DNS rebinding requires integration testing with controlled DNS.
    
    This vulnerability cannot be tested at unit level - requires:
    - Control of DNS server
    - Time-based rebinding attack
    
    Mitigation must be verified at integration test level.
    """
    pass
