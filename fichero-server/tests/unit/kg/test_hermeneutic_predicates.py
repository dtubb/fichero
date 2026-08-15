"""Test hermeneutic predicate vocabulary and Interpretation model."""

import pytest
from fichero_server.knowledge._common import (
    HERMENEUTIC_PREDICATES,
    canonical_hermeneutic_predicate,
)
from fichero_server.models.hermeneutics import Interpretation, InterpretiveActType


class TestHermeneuticPredicatesVocabulary:
    """Verify HERMENEUTIC_PREDICATES structure and lookup."""

    def test_hermeneutic_predicates_exists(self):
        """HERMENEUTIC_PREDICATES dict is defined."""
        assert isinstance(HERMENEUTIC_PREDICATES, dict)
        assert len(HERMENEUTIC_PREDICATES) > 0

    def test_hermeneutic_predicates_covers_categories(self):
        """HERMENEUTIC_PREDICATES includes all major categories."""
        canonical_values = set(HERMENEUTIC_PREDICATES.values())
        required_categories = {
            "applies_to",
            "uses_framework",
            "contests_reading",
            "centers",
            "gendered_as",
            "frames_as",
            "exposes",
            "legitimates",
            "analogous_to",
            "critiques",
        }
        assert required_categories.issubset(canonical_values)

    def test_canonical_hermeneutic_predicate_lookup(self):
        """canonical_hermeneutic_predicate maps variants to canonical forms."""
        assert canonical_hermeneutic_predicate("centers") == "centers"
        assert canonical_hermeneutic_predicate("contests reading") == "contests_reading"
        assert canonical_hermeneutic_predicate("uses framework") == "uses_framework"
        assert canonical_hermeneutic_predicate("exposes") == "exposes"

    def test_canonical_hermeneutic_predicate_case_insensitive(self):
        """canonical_hermeneutic_predicate is case-insensitive."""
        assert canonical_hermeneutic_predicate("CENTERS") == "centers"
        assert canonical_hermeneutic_predicate("Contests Reading") == "contests_reading"

    def test_canonical_hermeneutic_predicate_strips_whitespace(self):
        """canonical_hermeneutic_predicate strips whitespace."""
        assert canonical_hermeneutic_predicate("  centers  ") == "centers"
        assert canonical_hermeneutic_predicate("  contests reading  ") == "contests_reading"

    def test_canonical_hermeneutic_predicate_unknown_returns_none(self):
        """canonical_hermeneutic_predicate returns None for unknown predicates."""
        assert canonical_hermeneutic_predicate("frobnicates") is None
        assert canonical_hermeneutic_predicate("") is None
        assert canonical_hermeneutic_predicate(None) is None

    def test_hermeneutic_predicates_multiple_variants(self):
        """Multiple variants can map to the same canonical form."""
        assert HERMENEUTIC_PREDICATES["applies to"] == "applies_to"
        assert HERMENEUTIC_PREDICATES["applies_to"] == "applies_to"
        assert HERMENEUTIC_PREDICATES["contests reading"] == "contests_reading"
        assert HERMENEUTIC_PREDICATES["contests_reading"] == "contests_reading"


class TestInterpretationModel:
    """Verify Interpretation model has predicate fields."""

    def test_interpretation_has_predicate_fields(self):
        """Interpretation model includes predicate and predicate_canonical."""
        interp = Interpretation(
            framework_id="test_framework",
            claim_id="test_claim",
            interpretation_text="This reading centers women's labor",
            act=InterpretiveActType.reading,
        )
        assert hasattr(interp, "predicate")
        assert hasattr(interp, "predicate_canonical")

    def test_interpretation_predicate_default_empty(self):
        """Interpretation.predicate defaults to empty string."""
        interp = Interpretation(
            framework_id="test_framework",
            claim_id="test_claim",
            interpretation_text="A reading",
            act=InterpretiveActType.reading,
        )
        assert interp.predicate == ""

    def test_interpretation_predicate_canonical_default_none(self):
        """Interpretation.predicate_canonical defaults to None."""
        interp = Interpretation(
            framework_id="test_framework",
            claim_id="test_claim",
            interpretation_text="A reading",
            act=InterpretiveActType.reading,
        )
        assert interp.predicate_canonical is None

    def test_interpretation_with_predicate_values(self):
        """Interpretation accepts both predicate and predicate_canonical."""
        interp = Interpretation(
            framework_id="test_framework",
            claim_id="test_claim",
            interpretation_text="This centers women's labor",
            act=InterpretiveActType.reading,
            predicate="centers",
            predicate_canonical="centers",
        )
        assert interp.predicate == "centers"
        assert interp.predicate_canonical == "centers"

    def test_interpretation_serialization_includes_predicates(self):
        """Interpretation serialization includes predicate fields."""
        interp = Interpretation(
            framework_id="test_framework",
            claim_id="test_claim",
            interpretation_text="A reading",
            act=InterpretiveActType.reading,
            predicate="contests reading",
            predicate_canonical="contests_reading",
        )
        data = interp.model_dump()
        assert "predicate" in data
        assert "predicate_canonical" in data
        assert data["predicate"] == "contests reading"
        assert data["predicate_canonical"] == "contests_reading"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
