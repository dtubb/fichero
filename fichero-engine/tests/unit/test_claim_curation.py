"""Unit tests for review queue functionality.

Tests cover:
- Curation state validation
- Claim transitions
- Batch transitions
- Queue filtering
- Entity name resolution
"""

import pytest
from fastapi import HTTPException

from fichero.api.routes.claim.curation import (
    _validate_curation_state,
    ClaimTransitionRequest,
    BatchClaimTransitionRequest,
    QueueClaimItem,
)
from fichero.models.knowledge import ClaimCurationState


class TestCurationStateValidation:
    """Test curation state validation helper."""

    def test_valid_curation_states(self):
        """Test all valid curation states are accepted."""
        for state in ClaimCurationState:
            result = _validate_curation_state(state.value)
            assert result == state

    def test_unreviewed_state(self):
        """Test unreviewed state validation."""
        result = _validate_curation_state("unreviewed")
        assert result == ClaimCurationState.unreviewed

    def test_shortlisted_state(self):
        """Test shortlisted state validation."""
        result = _validate_curation_state("shortlisted")
        assert result == ClaimCurationState.shortlisted

    def test_curated_state(self):
        """Test curated state validation."""
        result = _validate_curation_state("curated")
        assert result == ClaimCurationState.curated

    def test_rejected_state(self):
        """Test rejected state validation."""
        result = _validate_curation_state("rejected")
        assert result == ClaimCurationState.rejected

    def test_invalid_state_raises(self):
        """Test invalid state raises HTTPException."""
        with pytest.raises(HTTPException) as exc:
            _validate_curation_state("invalid_state")
        assert exc.value.status_code == 400
        assert "Invalid curation state" in exc.value.detail

    def test_empty_state_raises(self):
        """Test empty state raises HTTPException."""
        with pytest.raises(HTTPException):
            _validate_curation_state("")


class TestClaimTransitionRequest:
    """Test ClaimTransitionRequest model."""

    def test_create_request(self):
        """Test creating a transition request."""
        request = ClaimTransitionRequest(to_state="shortlisted")
        assert request.to_state == "shortlisted"
        assert request.reviewed_by == "human"
        assert request.reason is None

    def test_create_request_with_reason(self):
        """Test creating a request with reason."""
        request = ClaimTransitionRequest(
            to_state="curated",
            reason="Verified by domain expert",
            reviewed_by="expert_1"
        )
        assert request.to_state == "curated"
        assert request.reason == "Verified by domain expert"
        assert request.reviewed_by == "expert_1"


class TestBatchClaimTransitionRequest:
    """Test BatchClaimTransitionRequest model."""

    def test_create_batch_request(self):
        """Test creating a batch transition request."""
        request = BatchClaimTransitionRequest(
            claim_ids=["claim-1", "claim-2", "claim-3"],
            to_state="rejected"
        )
        assert len(request.claim_ids) == 3
        assert request.to_state == "rejected"

    def test_empty_claim_ids_fails(self):
        """Test that empty claim_ids fails validation."""
        # Model has min_length=1, so empty list should fail
        with pytest.raises(ValueError):
            BatchClaimTransitionRequest(
                claim_ids=[],
                to_state="curated"
            )


class TestQueueClaimItem:
    """Test QueueClaimItem model."""

    def test_create_queue_item(self):
        """Test creating a queue item."""
        item = QueueClaimItem(
            claim_id="test-123",
            text="This is a test claim",
            curation_state="unreviewed",
            claim_type="fact",
            epistemic_status="tentative",
            confidence=0.8,
            source_document_id="doc-456",
            entity_ids=["entity-1"],
            entity_names=["Test Entity"],
            created_at="2024-01-01T00:00:00"
        )
        assert item.claim_id == "test-123"
        assert item.curation_state == "unreviewed"
        assert item.confidence == 0.8

    def test_create_queue_item_with_review_history(self):
        """Test creating a queue item with review history."""
        item = QueueClaimItem(
            claim_id="test-123",
            text="Test",
            curation_state="curated",
            claim_type="fact",
            epistemic_status="confirmed",
            confidence=0.95,
            source_document_id="doc-1",
            entity_ids=[],
            entity_names=[],
            created_at="2024-01-01T00:00:00",
            review_history=[
                {"from_state": "unreviewed", "to_state": "shortlisted"},
                {"from_state": "shortlisted", "to_state": "curated"}
            ]
        )
        assert len(item.review_history) == 2


class TestTransitionValidations:
    """Test transition validation combinations."""

    def test_all_valid_transitions(self):
        """Test that all state names are valid."""
        valid_states = ["unreviewed", "shortlisted", "curated", "rejected"]
        for state in valid_states:
            result = _validate_curation_state(state)
            assert result is not None

    def test_rejected_is_valid_target(self):
        """Test that rejected is a valid transition target."""
        result = _validate_curation_state("rejected")
        assert result == ClaimCurationState.rejected
