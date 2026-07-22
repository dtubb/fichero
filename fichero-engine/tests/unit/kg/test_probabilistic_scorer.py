"""Tests for probabilistic entity-match scoring (#988 step 3)."""

from fichero.kg.probabilistic_scorer import (
    _alias_overlap_score,
    _canonical_name_similarity,
    apply_thresholds,
    compute_entity_pair_score,
)
from fichero.models.knowledge import EntityType, KnowledgeEntity


class TestCanonicalNameSimilarity:
    """SequenceMatcher-based string similarity."""

    def test_identical_names(self) -> None:
        """Exact match scores 1.0."""
        score = _canonical_name_similarity("Andrés Restrepo", "Andrés Restrepo")
        assert score == 1.0

    def test_case_insensitive(self) -> None:
        """Case differences ignored."""
        score = _canonical_name_similarity("Andrés", "andrés")
        assert score == 1.0

    def test_accent_variant(self) -> None:
        """Surface variation: 'Córdoba' vs 'Cordoba' — high but <1.0."""
        score = _canonical_name_similarity("Córdoba", "Cordoba")
        assert 0.8 < score < 1.0

    def test_prefix_overlap(self) -> None:
        """'Andrés' vs 'Andrés Restrepo' — scores well."""
        score = _canonical_name_similarity("Andrés", "Andrés Restrepo")
        assert 0.5 < score < 1.0

    def test_very_different(self) -> None:
        """'Smith' vs 'Jones' — low score."""
        score = _canonical_name_similarity("Smith", "Jones")
        assert score < 0.3

    def test_empty_strings(self) -> None:
        """Empty or None-like strings return 0.0."""
        assert _canonical_name_similarity("", "Andrés") == 0.0
        assert _canonical_name_similarity("Andrés", "") == 0.0
        assert _canonical_name_similarity("", "") == 0.0


class TestAliasOverlap:
    """Exact alias match (after normalization)."""

    def test_no_aliases(self) -> None:
        """No overlap if either set is empty."""
        assert _alias_overlap_score([], ["nickname"]) == 0.0
        assert _alias_overlap_score(["nickname"], []) == 0.0
        assert _alias_overlap_score([], []) == 0.0

    def test_exact_match(self) -> None:
        """Exact alias match scores 1.0."""
        score = _alias_overlap_score(["Dr. A", "Andy"], ["Andy", "Andreas"])
        assert score == 1.0

    def test_case_insensitive_alias(self) -> None:
        """Alias match is case-insensitive."""
        score = _alias_overlap_score(["Andy"], ["ANDY"])
        assert score == 1.0

    def test_no_overlap(self) -> None:
        """No shared aliases return 0.0."""
        score = _alias_overlap_score(["Andy"], ["Bobby"])
        assert score == 0.0

    def test_multiple_aliases(self) -> None:
        """Match on any alias returns 1.0."""
        score = _alias_overlap_score(
            ["Dr. Andrés", "Andy"],
            ["Andreas", "Andy"],
        )
        assert score == 1.0


class TestThresholdDecision:
    """Result classification for auto-merge, queue, or ignore."""

    def test_auto_merge_decision(self) -> None:
        """Score >= 0.95 is auto-merge."""
        result = apply_thresholds(0.98)
        assert result.action == "auto_merge"
        assert result.score == 0.98

    def test_review_queue_decision(self) -> None:
        """Score in [0.7, 0.95) is queue."""
        result = apply_thresholds(0.80)
        assert result.action == "queue"
        assert result.score == 0.80

    def test_ignore_decision(self) -> None:
        """Score < 0.7 is ignore."""
        result = apply_thresholds(0.60)
        assert result.action == "ignore"
        assert result.score == 0.60

    def test_boundary_auto_merge(self) -> None:
        """Exactly at auto-merge threshold."""
        result = apply_thresholds(0.95)
        assert result.action == "auto_merge"

    def test_boundary_review_queue(self) -> None:
        """Exactly at review-queue threshold."""
        result = apply_thresholds(0.70)
        assert result.action == "queue"

    def test_custom_thresholds(self) -> None:
        """Custom threshold values."""
        result = apply_thresholds(0.85, auto_merge_threshold=0.90, review_queue_threshold_min=0.75)
        assert result.action == "queue"


class TestComputeEntityPairScore:
    """Integration: canonical + alias + vector signals."""

    def test_perfect_match_identical_names_and_aliases(self, db) -> None:
        """Identical names + matching alias → high score."""
        ent_a = KnowledgeEntity(
            id="e-a",
            canonical_name="Andrés Restrepo",
            aliases=["Andy", "A.R."],
            entity_type=EntityType.person,
        )
        ent_b = KnowledgeEntity(
            id="e-b",
            canonical_name="Andrés Restrepo",
            aliases=["Andy", "Andreas"],
            entity_type=EntityType.person,
        )
        score = compute_entity_pair_score(db, ent_a, ent_b)
        # 0.40 * 1.0 (canon) + 0.40 * 1.0 (alias) + 0.20 * 0 (no vec) = 0.80
        assert score == 0.80

    def test_cross_type_entities_rejected(self, db) -> None:
        """Person vs location (cross-type) = 0.0 regardless of names."""
        ent_a = KnowledgeEntity(
            id="e-a",
            canonical_name="Andrés",
            entity_type=EntityType.person,
        )
        ent_b = KnowledgeEntity(
            id="e-b",
            canonical_name="Andrés",
            entity_type=EntityType.location,
        )
        score = compute_entity_pair_score(db, ent_a, ent_b)
        assert score == 0.0

    def test_no_similarity(self, db) -> None:
        """Very different names and no aliases → low score."""
        ent_a = KnowledgeEntity(
            id="e-a",
            canonical_name="Smith",
            entity_type=EntityType.person,
        )
        ent_b = KnowledgeEntity(
            id="e-b",
            canonical_name="Jones",
            entity_type=EntityType.person,
        )
        score = compute_entity_pair_score(db, ent_a, ent_b)
        # ~0.40 * 0.15 (very different) + 0.40 * 0.0 + 0.20 * 0.0 ≈ 0.06
        assert score < 0.2

    def test_partial_match(self, db) -> None:
        """Name similarity without aliases."""
        ent_a = KnowledgeEntity(
            id="e-a",
            canonical_name="Andrés Restrepo",
            entity_type=EntityType.person,
        )
        ent_b = KnowledgeEntity(
            id="e-b",
            canonical_name="Andrés",
            entity_type=EntityType.person,
        )
        score = compute_entity_pair_score(db, ent_a, ent_b)
        # 0.40 * ~0.6 (prefix match) + 0.40 * 0.0 + 0.20 * 0.0 ≈ 0.24
        assert 0.15 < score < 0.35

    def test_alias_only_match(self, db) -> None:
        """Names differ but aliases match exactly."""
        ent_a = KnowledgeEntity(
            id="e-a",
            canonical_name="Andrew",
            aliases=["Andy"],
            entity_type=EntityType.person,
        )
        ent_b = KnowledgeEntity(
            id="e-b",
            canonical_name="Anderson",
            aliases=["Andy"],
            entity_type=EntityType.person,
        )
        score = compute_entity_pair_score(db, ent_a, ent_b)
        # 0.40 * ~0.5 (different) + 0.40 * 1.0 (alias match) + 0.20 * 0.0
        # ≈ 0.20 + 0.40 = 0.60
        assert 0.55 < score < 0.70
