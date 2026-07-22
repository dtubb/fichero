"""Security tests for Phase 2 Hermeneutics components.

These tests verify that hermeneutics endpoints are secure and do not fabricate
LLM output.
"""


# ═══════════════════════════════════════════════════════════════════════════════
# Framework Security Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestFrameworkSecurity:
    """Test interpretive framework security."""

    def test_framework_metadata_safe_for_storage(self):
        """LOW-1: Framework metadata should be JSON-serializable only.

        The metadata dict should not allow code execution.
        This test verifies Pydantic BaseModel constraints.
        """
        from fichero.models.hermeneutics import InterpretiveFramework

        # Test that metadata stores data only
        framework = InterpretiveFramework(
            name="Test Framework",
            framework_type="historical",
            description="A test framework",
            metadata={
                "custom_field": "value",
                "nested": {"key": "value"},
            },
        )

        # Verify metadata is safe dict
        assert isinstance(framework.metadata, dict)
        assert framework.metadata["custom_field"] == "value"

    def test_framework_no_code_execution_in_metadata(self):
        """LOW-1: Framework metadata should not execute code.

        Attempt to store malicious data in metadata.
        """
        from fichero.models.hermeneutics import InterpretiveFramework

        # Store "malicious" string patterns
        framework = InterpretiveFramework(
            name="Test",
            framework_type="historical",
            description="Test",
            metadata={
                "malicious_key": "__import__('os').system('evil')",
                "script": "<script>alert('xss')</script>",
            },
        )

        # Should store as strings, not execute
        assert framework.metadata["malicious_key"] == "__import__('os').system('evil')"
        assert "<script>" in framework.metadata["script"]


# ═══════════════════════════════════════════════════════════════════════════════
# LLM Injection Future Risk Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestLLMInjectionFutureRisk:
    """Test the unavailable suggestion path and future prompt inputs."""

    def test_suggestions_endpoint_is_explicitly_unavailable(self, client):
        """MEDIUM-1: /suggestions does not present placeholder text as AI output."""
        from fichero.models.hermeneutics import HermesSuggestionRequest

        # Create a framework first
        framework_resp = client.post(
            "/api/hermeneutics/frameworks",
            json={
                "name": "Test Framework",
                "framework_type": "historical",
                "description": "Test description",
            },
        )
        assert framework_resp.status_code == 200
        framework_id = framework_resp.json()["id"]

        # Request suggestions
        resp = client.post(
            "/api/hermeneutics/suggestions",
            json=HermesSuggestionRequest(
                claim_ids=[],
                framework_ids=[framework_id],
                num_suggestions=1,
            ).model_dump(),
        )

        assert resp.status_code == 501
        assert resp.json()["detail"] == "Grounded AI interpretation suggestions are not implemented."

    def test_framework_injection_markers_detected(self):
        """MEDIUM-1: Framework fields could contain injection markers.

        This test documents what should be sanitized when LLM is added.
        """
        from fichero.models.hermeneutics import InterpretiveFramework

        injection_patterns = [
            "Ignore previous instructions",
            "Ignore all prior instructions",
            "You are now",
            "Disregard",
            "System prompt",
            "Disobey",
        ]

        # Create framework with injection-like content
        for pattern in injection_patterns:
            framework = InterpretiveFramework(
                name=f"Framework with {pattern}",
                framework_type="historical",
                description=f"Description: {pattern}",
                core_questions=[f"Question: {pattern}?"],
            )

            # Should store without modification
            # Future: should sanitize before LLM prompt
            assert pattern in framework.name or pattern in framework.description
