"""Tests for contradiction triage API (Issue #436)."""

from datetime import datetime

from fichero.api.routes.contradictions import (
    ContradictionSeverity,
    EvidenceType,
    ResolutionStatus,
    EvidenceItem,
    ContradictingClaimSummary,
    SideBySideComparison,
    EvidenceChain,
    EvidenceChainNode,
    ContradictionVisualizationData,
    CreateContradictionRequest,
    UpdateContradictionRequest,
    _calculate_semantic_similarity,
    _find_points_of_conflict,
    _find_points_of_agreement,
)
from fichero.knowledge_models import KnowledgeClaim, ClaimRelationType


class TestContradictionEnums:
    """Test contradiction-related enums."""

    def test_severity_levels(self):
        """Test severity enum values."""
        assert ContradictionSeverity.MINOR.value == "minor"
        assert ContradictionSeverity.MODERATE.value == "moderate"
        assert ContradictionSeverity.SEVERE.value == "severe"
        assert ContradictionSeverity.CRITICAL.value == "critical"

    def test_evidence_types(self):
        """Test evidence type enum values."""
        assert EvidenceType.PRIMARY_SOURCE.value == "primary_source"
        assert EvidenceType.SECONDARY_SOURCE.value == "secondary_source"
        assert EvidenceType.EXPERT_TESTIMONY.value == "expert_testimony"
        assert EvidenceType.LOGICAL_INFERENCE.value == "logical_inference"

    def test_resolution_status(self):
        """Test resolution status enum values."""
        assert ResolutionStatus.UNRESOLVED.value == "unresolved"
        assert ResolutionStatus.RESOLVED.value == "resolved"
        assert ResolutionStatus.REFUTED.value == "refuted"
        assert ResolutionStatus.SUPERSEDED.value == "superseded"


class TestEvidenceItem:
    """Test EvidenceItem model."""

    def test_create_evidence_item(self):
        """Test creating evidence item."""
        item = EvidenceItem(
            evidence_type=EvidenceType.PRIMARY_SOURCE,
            source_id="source-123",
            description="Direct archival citation",
            relevance_score=0.9,
            citation="Archive Box 5, Folder 2",
        )
        assert item.evidence_type == EvidenceType.PRIMARY_SOURCE
        assert item.source_id == "source-123"
        assert item.relevance_score == 0.9


class TestContradictingClaimSummary:
    """Test ContradictingClaimSummary model."""

    def test_create_summary(self):
        """Test creating claim summary."""
        now = datetime.now().isoformat()
        summary = ContradictingClaimSummary(
            claim_id="claim-456",
            claim_text="This is a contradicting claim...",
            confidence=0.75,
            epistemic_status="proposed",
            source_count=2,
            relation_quality=0.8,
            severity=ContradictionSeverity.MODERATE,
            detected_at=now,
            evidence_summary="High quality archival source",
        )
        assert summary.claim_id == "claim-456"
        assert summary.relation_quality == 0.8
        assert summary.severity == ContradictionSeverity.MODERATE


class TestSideBySideComparison:
    """Test side-by-side comparison model."""

    def test_comparison_creation(self):
        """Test creating comparison."""
        comparison = SideBySideComparison(
            claim_a={"id": "a1", "full_text": "Claim A text"},
            claim_b={"id": "b1", "full_text": "Claim B text"},
            points_of_agreement=["Shared source"],
            points_of_conflict=["Different dates"],
            semantic_similarity=0.65,
            confidence_a=0.8,
            confidence_b=0.7,
            source_quality_a=0.75,
            source_quality_b=0.65,
        )
        assert comparison.semantic_similarity == 0.65
        assert len(comparison.points_of_agreement) == 1
        assert len(comparison.points_of_conflict) == 1


class TestEvidenceChain:
    """Test evidence chain model."""

    def test_chain_creation(self):
        """Test creating evidence chain."""
        nodes = [
            EvidenceChainNode(
                node_type="claim",
                node_id="claim-1",
                node_label="Original claim",
                confidence=0.9,
            ),
            EvidenceChainNode(
                node_type="claim",
                node_id="claim-2",
                node_label="Related claim",
                confidence=0.7,
                metadata={"relation_type": "contradicts"},
            ),
        ]

        chain = EvidenceChain(
            start_claim_id="claim-1",
            end_claim_id="claim-2",
            chain_type="contradicting",
            nodes=nodes,
            edges=[{"source": "claim-1", "target": "claim-2", "type": "contradicts"}],
            total_length=2,
            strength_score=0.8,
        )
        assert chain.chain_type == "contradicting"
        assert chain.strength_score == 0.8
        assert len(chain.nodes) == 2


class TestContradictionVisualizationData:
    """Test visualization data model."""

    def test_visualization_creation(self):
        """Test creating visualization data."""
        data = ContradictionVisualizationData(
            nodes=[
                {"id": "c1", "type": "focus", "label": "Main claim"},
                {"id": "c2", "type": "contradiction", "label": "Contradicting"},
            ],
            edges=[{"source": "c1", "target": "c2", "type": "contradicts"}],
            claim_id="c1",
            focus_claim={"id": "c1", "text": "Main claim"},
            contradictions=[{"id": "c2", "text": "Contradicting claim", "severity": "severe"}],
            supports=[],
            severity_distribution={"severe": 1},
        )
        assert data.claim_id == "c1"
        assert len(data.nodes) == 2
        assert data.severity_distribution["severe"] == 1


class TestCreateContradictionRequest:
    """Test create contradiction request model."""

    def test_create_request(self):
        """Test creating request."""
        request = CreateContradictionRequest(
            target_claim_id="claim-target",
            severity=ContradictionSeverity.SEVERE,
            evidence_items=[
                EvidenceItem(
                    evidence_type=EvidenceType.PRIMARY_SOURCE,
                    description="Conflicting evidence",
                ),
            ],
            explanation="Direct contradiction found",
        )
        assert request.target_claim_id == "claim-target"
        assert request.severity == ContradictionSeverity.SEVERE
        assert len(request.evidence_items) == 1


class TestUpdateContradictionRequest:
    """Test update contradiction request model."""

    def test_update_request(self):
        """Test creating update request."""
        request = UpdateContradictionRequest(
            severity=ContradictionSeverity.MODERATE,
            resolution_status=ResolutionStatus.RESOLVED,
            resolution_notes="Reconciled through additional context",
        )
        assert request.severity == ContradictionSeverity.MODERATE
        assert request.resolution_status == ResolutionStatus.RESOLVED
        assert request.resolution_notes == "Reconciled through additional context"


class TestSemanticSimilarity:
    """Test semantic similarity calculation."""

    def test_similar_texts(self):
        """Test similar texts have high similarity."""
        text_a = "The quick brown fox jumps over the lazy dog"
        text_b = "The quick brown fox jumps over the lazy dog"
        similarity = _calculate_semantic_similarity(text_a, text_b)
        assert similarity == 1.0

    def test_different_texts(self):
        """Test different texts have low similarity."""
        text_a = "The quick brown fox"
        text_b = "Completely different sentence about space"
        similarity = _calculate_semantic_similarity(text_a, text_b)
        assert similarity < 0.5

    def test_partial_overlap(self):
        """Test partial overlap."""
        text_a = "The quick brown fox jumps"
        text_b = "The quick brown dog runs"
        similarity = _calculate_semantic_similarity(text_a, text_b)
        assert 0 < similarity < 1  # Partial overlap

    def test_empty_texts(self):
        """Test empty texts."""
        assert _calculate_semantic_similarity("", "text") == 0.0
        assert _calculate_semantic_similarity("text", "") == 0.0
        assert _calculate_semantic_similarity("", "") == 0.0


class TestFindPointsOfConflict:
    """Test points of conflict detection."""

    def test_confidence_disagreement(self):
        """Test detection of confidence disagreement."""
        claim_a = KnowledgeClaim(
            text="Claim A",
            confidence=0.9,
            source_document_id="doc-1",
        )
        claim_b = KnowledgeClaim(
            text="Claim B",
            confidence=0.3,
            source_document_id="doc-2",
        )
        conflicts = _find_points_of_conflict(claim_a, claim_b)
        assert any("Confidence disagreement" in c for c in conflicts)


class TestFindPointsOfAgreement:
    """Test points of agreement detection."""

    def test_similar_confidence(self):
        """Test detection of similar confidence."""
        claim_a = KnowledgeClaim(text="Claim A", confidence=0.8, source_document_id="doc-1")
        claim_b = KnowledgeClaim(text="Claim B", confidence=0.75, source_document_id="doc-2")
        agreements = _find_points_of_agreement(claim_a, claim_b)
        assert any("Similar confidence" in a for a in agreements)

    def test_shared_entities(self):
        """Test detection of shared entities."""
        claim_a = KnowledgeClaim(text="Claim A", confidence=0.8, source_document_id="doc-1", entity_ids=["entity1", "entity2"])
        claim_b = KnowledgeClaim(text="Claim B", confidence=0.8, source_document_id="doc-2", entity_ids=["entity1", "entity3"])
        agreements = _find_points_of_agreement(claim_a, claim_b)
        assert any("Shared entities" in a for a in agreements)


class TestClaimRelationType:
    """Test claim relation type enum."""

    def test_contradicts_value(self):
        """Test contradicts relation type."""
        assert ClaimRelationType.contradicts.value == "contradicts"
        assert ClaimRelationType.supports.value == "supports"
        assert ClaimRelationType.refines.value == "refines"
