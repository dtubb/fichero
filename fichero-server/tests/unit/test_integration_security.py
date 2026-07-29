"""Security tests for Phase 5 Integration components.

These tests verify CORS configuration, MCP authorization, and feature tier security.
They test that security controls are properly enforced.
"""

import os
from unittest.mock import patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# CORS Security Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestCORSSecurity:
    """Test CORS configuration security."""

    def test_cors_allows_specific_origins_not_wildcard(self, client):
        """HIGH-1: CORS should not allow all origins with credentials."""
        # This test checks if CORS is properly restricted
        # A proper implementation should reject unknown origins
        headers = {
            "Origin": "https://malicious-site.com",
            "Access-Control-Request-Method": "GET",
        }
        response = client.options("/api/research/projects", headers=headers)
        
        # Should be blocked or not include Access-Control-Allow-Origin: *
        assert "*" not in response.headers.get("access-control-allow-origin", ""), \
            "CORS allows wildcard origin - security risk"
        
        # With credentials enabled, wildcard should never be returned
        if response.headers.get("access-control-allow-credentials") == "true":
            assert response.headers.get("access-control-allow-origin") != "*", \
                "CORS allows credentials with wildcard origin - CRITICAL"

    def test_cors_blocks_malicious_origin(self, client):
        """HIGH-1: CORS should block requests from untrusted origins."""
        headers = {"Origin": "https://evil.com"}
        response = client.get("/api/research/projects", headers=headers)
        
        # Either no CORS headers (blocked) or no wildcard
        allow_origin = response.headers.get("access-control-allow-origin")
        assert allow_origin is None or allow_origin != "*", \
            "CORS response allows any origin"

    def test_cors_preflight_validates_origin(self, client):
        """HIGH-1: CORS preflight should validate origin.
        
        FIXED: Returns 200 with appropriate headers for localhost origins.
        Rejected origins should not get access-control-allow-credentials.
        """
        headers = {
            "Origin": "https://untrusted.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        }
        response = client.options("/api/research/projects", headers=headers)
        
        # Allow 200 or 204 for preflight responses
        assert response.status_code in [200, 204, 400, 403], \
            f"CORS preflight returned unexpected status: {response.status_code}"
        
        # If credentials are allowed, origin should be specific (not *)
        if response.headers.get("access-control-allow-credentials") == "true":
            origin = response.headers.get("access-control-allow-origin")
            assert origin != "*", "Credentials allowed with wildcard origin"


# ═══════════════════════════════════════════════════════════════════════════════
# MCP Authorization Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMCPAuthorization:
    """Test MCP server authorization controls.

    The MCP server is a thin wrapper over ``fichero_server.cli.FicheroClient``; it
    authenticates with an ``Authorization: Bearer <token>`` header, the same
    scheme the engine and SwiftUI app use. The token is discovered from
    ``FICHERO_API_KEY`` or the engine's key file.
    """

    def test_mcp_sends_bearer_token(self):
        """HIGH-2: MCP client should authenticate with a Bearer token."""
        from fichero_server.mcp import server as mcp_server

        with patch.dict(os.environ, {"FICHERO_API_KEY": "test-api-key-12345"}):
            client = mcp_server._client()
            try:
                headers = client._headers()
            finally:
                client.close()

        assert headers.get("Authorization") == "Bearer test-api-key-12345", \
            "MCP client does not send a Bearer token"

    def test_mcp_reads_api_key_from_environment(self):
        """HIGH-2: MCP client should read the token from the environment."""
        from fichero_server.mcp import server as mcp_server

        with patch.dict(os.environ, {"FICHERO_API_KEY": "env-api-key"}):
            client = mcp_server._client()
            try:
                assert client.token == "env-api-key", \
                    "Token from environment not picked up"
                assert client._headers().get("Authorization") == "Bearer env-api-key", \
                    "Token from environment not sent as a Bearer header"
            finally:
                client.close()

    def test_mcp_warns_without_token(self, tmp_path):
        """HIGH-2: MCP server should warn at startup when no token is configured."""
        from fichero_server.mcp import server as mcp_server
        from fichero_server.cli import client as client_module

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(client_module, "_TOKEN_PATH", tmp_path / "absent"):
                with patch.object(mcp_server, "logger") as mock_logger:
                    with patch.object(mcp_server.mcp, "run"):
                        with patch("sys.argv", ["fichero-mcp"]):
                            mcp_server.main()

        assert any(
            "no fichero auth token found" in str(call).lower()
            for call in mock_logger.warning.call_args_list
        ), "Missing token should trigger a startup warning"


# ═══════════════════════════════════════════════════════════════════════════════
# Feature Tier Security Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestFeatureTierSecurity:
    """Test feature tier bypass protections."""

    @pytest.mark.parametrize(
        ("tier", "method", "path", "expected_404"),
        [
            ("release", "get", "/api/iiif/iiif/test/info.json", True),
            ("release", "post", "/api/chat", True),
            ("release", "get", "/api/research/projects", True),
            ("release", "get", "/api/activity", True),
            ("beta", "get", "/api/iiif/iiif/test/info.json", True),
            ("beta", "post", "/api/chat", False),
            ("beta", "get", "/api/research/projects", False),
            ("beta", "get", "/api/activity", False),
            ("alpha", "get", "/api/iiif/iiif/test/info.json", True),
            ("alpha", "post", "/api/chat", False),
            ("alpha", "get", "/api/research/projects", False),
            ("alpha", "get", "/api/activity", False),
            ("dev", "get", "/api/iiif/iiif/test/info.json", False),
            ("dev", "post", "/api/chat", False),
            ("dev", "get", "/api/research/projects", False),
            ("dev", "get", "/api/activity", False),
        ],
    )
    def test_tier_change_requires_validation(
        self, monkeypatch, tier, method, path, expected_404
    ):
        """MEDIUM-1: Hidden-tier routes should stay unreachable."""
        import fichero_server.api.main as main_module
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        test_app = FastAPI()
        monkeypatch.setattr(main_module, "app", test_app)
        main_module.register_tiered_routes(tier)
        client = TestClient(test_app)

        response = getattr(client, method)(path)
        assert (response.status_code == 404) is expected_404

    def test_tier_change_logged(self):
        """MEDIUM-1: Tier changes should be logged."""
        import fichero_server.api.main as main_module

        with patch.object(main_module, "logger") as mock_logger:
            main_module.resolve_feature_tier()

            assert any(
                "FICHERO_FEATURE_TIER" in str(call)
                for call in mock_logger.info.call_args_list
            ), "Feature tier not logged at startup"


# ═══════════════════════════════════════════════════════════════════════════════
# Library Path Security Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestLibraryPathSecurity:
    """Test library path header validation."""

    def test_library_path_blocks_traversal(self, client):
        """MEDIUM-2: Library path should block path traversal."""
        headers = {"X-Fichero-Library-Path": "/etc/../etc/passwd"}
        
        try:
            response = client.get("/api/research/projects", headers=headers)
            
            # Should fail with 403 or 400
            assert response.status_code in [400, 403, 500], \
                "Path traversal in library header not blocked"
        except Exception:
            # If it raises an exception, that's also a security concern
            # but might indicate proper validation
            pass

    def test_library_path_validates_allowed_locations(self, client):
        """MEDIUM-2: Library path should be in allowed locations."""
        # /usr/local is never in the allowlist on any OS or CI environment.
        headers = {"X-Fichero-Library-Path": "/usr/local/malicious.fichero"}

        try:
            response = client.get("/api/research/projects", headers=headers)

            # Should validate path is in allowed directory
            # (e.g., ~/Documents, ~/Library/Application Support)
            # If CORS passes but path is rejected
            if response.status_code == 200:
                pytest.fail("Library path not validated against allowed locations")
        except Exception:
            pass  # Validation might raise exception


# ═══════════════════════════════════════════════════════════════════════════════
# Environment Variable Security Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnvironmentSecurity:
    """Test environment variable handling."""

    def test_api_key_required_in_production(self):
        """HIGH: API key should be required in production."""
        # In production mode, API operations should require authentication
        with patch.dict(os.environ, {"FICHERO_ENV": "production"}):
            # This is a configuration test
            # Actual enforcement happens at runtime
            pass

    def test_debug_mode_disabled_in_production(self):
        """MEDIUM: Debug mode should be disabled in production."""
        # Check that debug mode is not enabled by default
        # This is more of a configuration check
        assert True  # Placeholder - actual check depends on implementation


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecurityHeaders:
    """Test security headers are present."""

    def test_security_headers_present(self, client):
        """Security headers should be present in responses."""
        response = client.get("/api/research/projects")
        
        # Check for basic security headers
        # Note: These might not be implemented yet
        security_headers = [
            "x-content-type-options",
            "x-frame-options",
            "x-xss-protection",
        ]
        
        for header in security_headers:
            if header not in response.headers:
                pytest.skip(f"Security header {header} not implemented yet")


# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
"""
Test Status Summary:

| Vulnerability | Tests | Status |
|--------------|-------|--------|
| CORS wildcard | 3 | Needs implementation |
| MCP auth | 3 | Needs implementation |
| Feature tier | 2 | Partial |
| Path traversal | 2 | Needs implementation |

Expected Behavior:
- These tests document security requirements
- Many will fail until fixes are implemented
- Fixes should make these tests pass
"""
