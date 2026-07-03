"""Unit tests for MCP Tools API routes.

Tests cover:
- Knowledge entity upsert (create/update)
- Knowledge claim create
- Entity/claim CRUD operations
- Error handling
- Validation
"""





import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from fichero.api.routes.mcp_tools import (
    KnowledgeEntityUpsertRequest,
    KnowledgeClaimCreateRequest,
    _validate_entity_type,
    _validate_claim_type,
    _validate_curation_state,
    _validate_epistemic_status,
    _validate_source_type,
)
from fichero.knowledge_models import (
    EntityType,
    ClaimType,
    ClaimCurationState,
    EpistemicStatus,
    SourceType,
)


class TestEntityTypeValidation:
    """Test entity type validation."""

    def test_valid_entity_types(self):
        """Test valid entity types are accepted."""
        for et in EntityType:
            result = _validate_entity_type(et.value)
            assert result == et

    def test_invalid_entity_type_raises(self):
        """Test invalid entity type raises HTTPException."""
        with pytest.raises(HTTPException) as exc:
            _validate_entity_type("invalid_type")
        assert exc.value.status_code == 400


class TestClaimTypeValidation:
    """Test claim type validation."""

    def test_valid_claim_types(self):
        """Test valid claim types are accepted."""
        for ct in ClaimType:
            result = _validate_claim_type(ct.value)
            assert result == ct

    def test_invalid_claim_type_raises(self):
        """Test invalid claim type raises HTTPException."""
        with pytest.raises(HTTPException) as exc:
            _validate_claim_type("invalid_type")
        assert exc.value.status_code == 400


class TestCurationStateValidation:
    """Test curation state validation."""

    def test_valid_curation_states(self):
        """Test valid curation states are accepted."""
        for cs in ClaimCurationState:
            result = _validate_curation_state(cs.value)
            assert result == cs

    def test_invalid_curation_state_raises(self):
        """Test invalid curation state raises HTTPException."""
        with pytest.raises(HTTPException) as exc:
            _validate_curation_state("invalid_state")
        assert exc.value.status_code == 400


class TestEpistemicStatusValidation:
    """Test epistemic status validation."""

    def test_valid_epistemic_statuses(self):
        """Test valid epistemic statuses are accepted."""
        for es in EpistemicStatus:
            result = _validate_epistemic_status(es.value)
            assert result == es

    def test_invalid_epistemic_status_raises(self):
        """Test invalid epistemic status raises HTTPException."""
        with pytest.raises(HTTPException) as exc:
            _validate_epistemic_status("invalid_status")
        assert exc.value.status_code == 400


class TestSourceTypeValidation:
    """Test source type validation."""

    def test_valid_source_types(self):
        """Test valid source types are accepted."""
        for st in SourceType:
            result = _validate_source_type(st.value)
            assert result == st

    def test_invalid_source_type_raises(self):
        """Test invalid source type raises HTTPException."""
        with pytest.raises(HTTPException) as exc:
            _validate_source_type("invalid_type")
        assert exc.value.status_code == 400


class TestKnowledgeEntityRequest:
    """Test KnowledgeEntityUpsertRequest model."""

    def test_create_request_valid(self):
        """Test creating a valid entity request."""
        request = KnowledgeEntityUpsertRequest(
            canonical_name="Tokyo",
            entity_type="place",
            language="en",
        )
        assert request.canonical_name == "Tokyo"
        assert request.entity_type == "place"

    def test_create_request_with_aliases(self):
        """Test creating entity request with aliases."""
        request = KnowledgeEntityUpsertRequest(
            canonical_name="Tokyo",
            entity_type="place",
            aliases=["東京都", "Tokyo Metropolis"],
        )
        assert len(request.aliases) == 2

    def test_create_request_with_metadata(self):
        """Test creating entity request with metadata."""
        request = KnowledgeEntityUpsertRequest(
            canonical_name="Tokyo",
            metadata={"population": 13960000, "country": "Japan"},
        )
        assert request.metadata["country"] == "Japan"

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            KnowledgeEntityUpsertRequest(
                canonical_name="Tokyo",
                unexpected=True,
            )


class TestKnowledgeClaimRequest:
    """Test KnowledgeClaimCreateRequest model."""

    def test_create_request_valid(self):
        """Test creating a valid claim request."""
        request = KnowledgeClaimCreateRequest(
            text="Paris is the capital of France",
            source_document_id="doc-123",
            claim_type="fact",
        )
        assert request.text == "Paris is the capital of France"
        assert request.source_document_id == "doc-123"

    def test_create_request_multi_source(self):
        """Test creating claim with multiple sources."""
        request = KnowledgeClaimCreateRequest(
            text="Global warming is accelerating",
            source_ids=["doc-1", "doc-2", "doc-3"],
            source_languages=["en", "es", "fr"],
            source_type="multiple",
        )
        assert len(request.source_ids) == 3

    def test_create_request_defaults(self):
        """Test claim request has correct defaults."""
        request = KnowledgeClaimCreateRequest(
            text="Test claim",
            source_document_id="doc-test",
        )
        assert request.claim_type == "fact"
        assert request.epistemic_status == "tentative"
        assert request.curation_state == "unreviewed"
        assert request.confidence == 0.5

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            KnowledgeClaimCreateRequest(
                text="Test claim",
                source_document_id="doc-test",
                unexpected=True,
            )
