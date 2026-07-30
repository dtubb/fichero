"""Unit tests for MCP knowledge adapters.

Tests verify thin MCP adapters for canonical knowledge APIs work correctly:
- Entity upsert/create/update
- Claim creation
- CRUD operations
- Error handling
"""

import pytest
from datetime import datetime

from fichero_server.models.knowledge import (
    KnowledgeEntity,
    KnowledgeClaim,
    EntityType,
    ClaimType,
    SourceType,
)


class TestMCPEntityAdapter:
    """Test MCP entity adapter operations."""

    def test_entity_creation_via_adapter(self):
        """Test creating an entity through MCP adapter."""
        from fichero_server.api.routes.mcp.tools import (
            KnowledgeEntityUpsertRequest,
            _validate_entity_type,
        )

        request = KnowledgeEntityUpsertRequest(
            canonical_name="Test Entity",
            entity_type="person",
            language="en",
            aliases=["alias1", "alias2"],
        )

        # Validate entity type
        entity_type = _validate_entity_type(request.entity_type)
        assert entity_type == EntityType.person

        # Verify model conversion
        assert request.canonical_name == "Test Entity"
        assert request.language == "en"
        assert len(request.aliases) == 2

    def test_entity_update_via_adapter(self):
        """Test entity update preserves ID."""
        from fichero_server.api.routes.mcp.tools import KnowledgeEntityUpsertRequest

        request = KnowledgeEntityUpsertRequest(
            id="existing-uuid",
            canonical_name="Updated Name",
            entity_type="organization",
        )

        assert request.id == "existing-uuid"
        assert request.canonical_name == "Updated Name"

    def test_entity_type_validation_error(self):
        """Test invalid entity type raises error."""
        from fichero_server.api.routes.mcp.tools import _validate_entity_type
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            _validate_entity_type("invalid_type")
        assert exc.value.status_code == 400
        assert "invalid_type" in str(exc.value.detail)


class TestMCPClaimAdapter:
    """Test MCP claim adapter operations."""

    def test_claim_creation_via_adapter(self):
        """Test creating a claim through MCP adapter."""
        from fichero_server.api.routes.mcp.tools import (
            KnowledgeClaimCreateRequest,
            _validate_claim_type,
            _validate_source_type,
        )

        request = KnowledgeClaimCreateRequest(
            text="This is a test claim",
            source_document_id="doc-123",
            claim_type="fact",
            source_type="document",
            entity_ids=["entity-1", "entity-2"],
            confidence=0.8,
        )

        # Validate types
        claim_type = _validate_claim_type(request.claim_type)
        assert claim_type == ClaimType.fact

        source_type = _validate_source_type(request.source_type)
        assert source_type == SourceType.document

        # Verify claim data
        assert request.text == "This is a test claim"
        assert request.source_document_id == "doc-123"
        assert request.confidence == 0.8
        assert len(request.entity_ids) == 2

    def test_claim_with_multiple_sources(self):
        """Test claim adapter supports multiple sources."""
        from fichero_server.api.routes.mcp.tools import KnowledgeClaimCreateRequest

        request = KnowledgeClaimCreateRequest(
            text="Synthesized claim",
            source_ids=["doc-1", "doc-2", "doc-3"],
            source_languages=["en", "es", "fr"],
            source_type="multiple",
        )

        assert len(request.source_ids) == 3
        assert len(request.source_languages) == 3
        assert request.source_type == "multiple"

    def test_claim_validation_errors(self):
        """Test claim validation handles errors."""
        from fichero_server.api.routes.mcp.tools import _validate_claim_type
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            _validate_claim_type("invalid_claim_type")
        assert exc.value.status_code == 400


class TestMCPCanonicalMapping:
    """Test MCP adapters map 1:1 to canonical knowledge API."""

    def test_entity_adapter_matches_knowledge_model(self):
        """Verify MCP entity fields match KnowledgeEntity model."""
        from fichero_server.api.routes.mcp.tools import KnowledgeEntityUpsertRequest

        request = KnowledgeEntityUpsertRequest(
            canonical_name="Canonical Name",
            entity_type="location",
            language="en",
            aliases=["alias1"],
            description="A description",
            metadata={"key": "value"},
        )

        # These fields should map directly to KnowledgeEntity
        entity = KnowledgeEntity(
            canonical_name=request.canonical_name,
            entity_type=EntityType(request.entity_type),
            language=request.language,
            aliases=request.aliases,
            description=request.description,
            metadata=request.metadata,
        )

        assert entity.canonical_name == request.canonical_name
        assert entity.language == request.language

    def test_claim_adapter_matches_knowledge_model(self):
        """Verify MCP claim fields match KnowledgeClaim model."""
        from fichero_server.api.routes.mcp.tools import KnowledgeClaimCreateRequest

        request = KnowledgeClaimCreateRequest(
            text="Claim text",
            source_document_id="doc-1",
            claim_type="fact",
            confidence=0.9,
        )

        # These fields should map directly to KnowledgeClaim
        claim = KnowledgeClaim(
            text=request.text,
            source_document_id=request.source_document_id,
            claim_type=ClaimType(request.claim_type),
            confidence=request.confidence,
            canonical_hash=request.text[:64],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        assert claim.text == request.text
        assert claim.confidence == request.confidence


class TestMCPAdapterErrorHandling:
    """Test MCP adapter error handling."""

    def test_empty_entity_name_rejected_by_model(self):
        """Test entity model rejects empty names."""
        from pydantic import ValidationError
        from fichero_server.api.routes.mcp.tools import KnowledgeEntityUpsertRequest

        with pytest.raises(ValidationError):
            KnowledgeEntityUpsertRequest(
                canonical_name="",
                entity_type="person",
            )

    def test_empty_claim_text_rejected_by_pydantic(self):
        """Test claim with empty text is rejected by Pydantic validation."""
        from pydantic import ValidationError
        from fichero_server.api.routes.mcp.tools import KnowledgeClaimCreateRequest

        # Pydantic validation should catch empty text
        with pytest.raises(ValidationError):
            KnowledgeClaimCreateRequest(
                text="",  # Empty text - min_length=1
                source_document_id="doc-1",
            )

    def test_invalid_confidence_range(self):
        """Test confidence outside 0-1 range."""
        from pydantic import ValidationError
        from fichero_server.api.routes.mcp.tools import KnowledgeClaimCreateRequest

        with pytest.raises(ValidationError):
            KnowledgeClaimCreateRequest(
                text="Test claim",
                source_document_id="doc-1",
                confidence=1.5,  # Out of range
            )

    def test_entity_extra_field_rejected(self):
        from pydantic import ValidationError
        from fichero_server.api.routes.mcp.tools import KnowledgeEntityUpsertRequest

        with pytest.raises(ValidationError):
            KnowledgeEntityUpsertRequest(
                canonical_name="Test",
                unexpected=True,
            )

    def test_claim_extra_field_rejected(self):
        from pydantic import ValidationError
        from fichero_server.api.routes.mcp.tools import KnowledgeClaimCreateRequest

        with pytest.raises(ValidationError):
            KnowledgeClaimCreateRequest(
                text="Test claim",
                source_document_id="doc-1",
                unexpected=True,
            )


class TestMCPEndpointCoverage:
    """Test MCP endpoints cover canonical knowledge API surface."""

    def test_entity_endpoints(self):
        """Verify all entity CRUD endpoints exist."""
        from fichero_server.api.routes.mcp.tools import router

        paths = [r.path for r in router.routes]

        # Should have upsert endpoint
        assert "/knowledge/entities/upsert" in paths
        # Should have read endpoint
        assert any("/knowledge/entities/{entity_id}" in p for p in paths)
        # Should have list endpoint
        assert "/knowledge/entities" in paths

    def test_claim_endpoints(self):
        """Verify all claim endpoints exist."""
        from fichero_server.api.routes.mcp.tools import router

        paths = [r.path for r in router.routes]

        # Should have create endpoint
        assert "/knowledge/claims/create" in paths
        # Should have read endpoint
        assert any("/knowledge/claims/{claim_id}" in p for p in paths)
        # Should have list endpoint
        assert "/knowledge/claims" in paths

    def test_soft_delete_supported(self):
        """Verify soft delete is available."""
        from fastapi.routing import APIRoute
        from fichero_server.api.routes.mcp.tools import router

        delete_routes = [
            r
            for r in router.routes
            if isinstance(r, APIRoute) and "DELETE" in str(r.methods)
        ]
        paths = [r.path for r in delete_routes]

        assert any("entities" in p for p in paths)
        assert any("claims" in p for p in paths)
