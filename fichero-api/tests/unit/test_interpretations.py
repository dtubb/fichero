"""Unit tests for interpretations workspace functionality.

Tests cover:
- Method taxonomy enums
- Citation lineage models
- Request/response models
- Helper functions
"""


from datetime import datetime

from fichero.api.routes.interpretations import (
    MethodCategory,
    MethodTechnique,
    CitationType,
    MethodTag,
    CitationLineage,
    InterpretationCreateRequest,
    InterpretationUpdateRequest,
    InterpretationDetailResponse,
    InterpretationListItem,
    _to_iso,
)
from fichero.hermeneutics_models import InterpretiveActType


class TestMethodCategory:
    """Test MethodCategory enum."""

    def test_historical_category(self):
        """Test historical category."""
        assert MethodCategory.HISTORICAL.value == "historical"

    def test_textual_category(self):
        """Test textual category."""
        assert MethodCategory.TEXTUAL.value == "textual"

    def test_analytical_category(self):
        """Test analytical category."""
        assert MethodCategory.ANALYTICAL.value == "analytical"


class TestMethodTechnique:
    """Test MethodTechnique enum."""

    def test_close_reading(self):
        """Test close reading technique."""
        assert MethodTechnique.CLOSE_READING.value == "close_reading"

    def test_narrative_analysis(self):
        """Test narrative analysis technique."""
        assert MethodTechnique.NARRATIVE_ANALYSIS.value == "narrative_analysis"

    def test_hermeneutic_circle(self):
        """Test hermeneutic circle technique."""
        assert MethodTechnique.HERMENEUTIC_CIRCLE.value == "hermeneutic_circle"


class TestCitationType:
    """Test CitationType enum."""

    def test_primary_citation(self):
        """Test primary citation type."""
        assert CitationType.PRIMARY.value == "primary"

    def test_secondary_citation(self):
        """Test secondary citation type."""
        assert CitationType.SECONDARY.value == "secondary"

    def test_supporting_citation(self):
        """Test supporting citation type."""
        assert CitationType.SUPPORTING.value == "supporting"


class TestMethodTag:
    """Test MethodTag model."""

    def test_create_method_tag(self):
        """Test creating a method tag."""
        tag = MethodTag(
            category=MethodCategory.HISTORICAL,
            technique=MethodTechnique.SOURCE_CRITICISM,
        )
        assert tag.category == MethodCategory.HISTORICAL
        assert tag.technique == MethodTechnique.SOURCE_CRITICISM
        assert tag.confidence == 1.0

    def test_method_tag_with_rationale(self):
        """Test method tag with rationale."""
        tag = MethodTag(
            category=MethodCategory.TEXTUAL,
            technique=MethodTechnique.DISCOURSE_ANALYSIS,
            confidence=0.85,
            rationale="Close reading reveals rhetorical patterns",
        )
        assert tag.confidence == 0.85
        assert tag.rationale == "Close reading reveals rhetorical patterns"


class TestCitationLineage:
    """Test CitationLineage model."""

    def test_create_citation_lineage(self):
        """Test creating citation lineage."""
        lineage = CitationLineage(
            claim_id="claim-123",
            citation_type=CitationType.PRIMARY,
            relevance_score=0.9,
            excerpt="Key supporting text...",
            notes="Important context",
        )
        assert lineage.claim_id == "claim-123"
        assert lineage.citation_type == CitationType.PRIMARY
        assert lineage.relevance_score == 0.9
        assert lineage.excerpt == "Key supporting text..."


class TestInterpretationCreateRequest:
    """Test InterpretationCreateRequest model."""

    def test_create_request_minimal(self):
        """Test creating request with minimal fields."""
        request = InterpretationCreateRequest(
            framework_id="framework-1",
            claim_ids=["claim-123"],
            interpretation_text="This is an interpretation.",
            act=InterpretiveActType.reading,
        )
        assert request.framework_id == "framework-1"
        assert request.claim_ids == ["claim-123"]
        assert request.interpretation_text == "This is an interpretation."
        assert request.act == InterpretiveActType.reading
        assert request.confidence == 0.5

    def test_create_request_full(self):
        """Test creating request with all fields."""
        request = InterpretationCreateRequest(
            framework_id="framework-1",
            claim_ids=["claim-1", "claim-2"],
            document_id="doc-123",
            passage_text="Original passage text",
            interpretation_text="Detailed interpretation text.",
            act=InterpretiveActType.synthesizing,
            confidence=0.85,
            key_insights=["Insight 1", "Insight 2"],
            tensions=["Tension A"],
            connections=["Connection B"],
            method_tags=[
                MethodTag(category=MethodCategory.HISTORICAL, technique=MethodTechnique.SOURCE_CRITICISM),
            ],
            citation_lineage=[
                CitationLineage(
                    claim_id="claim-1",
                    citation_type=CitationType.PRIMARY,
                    relevance_score=0.9,
                ),
            ],
            created_by="expert_user",
        )
        assert len(request.key_insights) == 2
        assert len(request.method_tags) == 1
        assert len(request.citation_lineage) == 1


class TestInterpretationUpdateRequest:
    """Test InterpretationUpdateRequest model."""

    def test_update_request_partial(self):
        """Test partial update request."""
        request = InterpretationUpdateRequest(
            confidence=0.75,
            key_insights=["New insight"],
        )
        assert request.confidence == 0.75
        assert request.key_insights == ["New insight"]
        assert request.interpretation_text is None


class TestHelperFunctions:
    """Test helper functions."""

    def test_to_iso_with_datetime(self):
        """Test _to_iso with datetime."""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = _to_iso(dt)
        assert "2024-01-15" in result


class TestInterpretationListItem:
    """Test InterpretationListItem model."""

    def test_create_list_item(self):
        """Test creating list item."""
        item = InterpretationListItem(
            id="interp-123",
            framework_name="Marxist Analysis",
            interpretation_preview="Class struggle interpretation...",
            act="synthesizing",
            confidence=0.9,
            num_claims=3,
            method_categories=["historical", "analytical"],
            created_at="2024-01-15T10:30:00",
        )
        assert item.id == "interp-123"
        assert item.framework_name == "Marxist Analysis"
        assert item.num_claims == 3
        assert len(item.method_categories) == 2


class TestInterpretationDetailResponse:
    """Test InterpretationDetailResponse model."""

    def test_create_detail_response(self):
        """Test creating detail response."""
        response = InterpretationDetailResponse(
            id="interp-123",
            framework_id="framework-1",
            framework_name="Historical Materialism",
            claim_ids=["claim-1", "claim-2"],
            claims_summary=[
                {"id": "claim-1", "text": "Summary 1...", "epistemic_status": "confirmed"},
            ],
            document_id=None,
            passage_text="Excerpt text",
            interpretation_text="Full interpretation text.",
            act="synthesizing",
            confidence=0.85,
            key_insights=["Key point"],
            tensions=[],
            connections=[],
            method_tags=[
                MethodTag(category=MethodCategory.HISTORICAL, technique=MethodTechnique.SOURCE_CRITICISM),
            ],
            citation_lineage=[
                CitationLineage(claim_id="claim-1", citation_type=CitationType.PRIMARY),
            ],
            source_provenance=[
                {"document_id": "doc-1", "claim_id": "claim-1", "source_type": "document"},
            ],
            created_by="researcher",
            created_at="2024-01-15T10:30:00",
            updated_at="2024-01-15T10:30:00",
        )
        assert response.framework_name == "Historical Materialism"
        assert len(response.method_tags) == 1
        assert len(response.citation_lineage) == 1
