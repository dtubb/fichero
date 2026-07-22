"""Tests for merge_dedup_only's claim-suppression target-state logic
(#1810 / #1804 dedup gap).

`_claim_target_state` decides the curation state + confidence a claim gets when
a persisted suppression rule fires. The conservative contract: every action
rejects the claim, but only `disable` keeps the original confidence — `demote`
and `prune` cap it at 0.2 so a re-run can't resurrect a suppressed claim at full
strength.
"""

from __future__ import annotations

from fichero.models.knowledge import ClaimCurationState, KnowledgeClaim
from fichero.workflows.tools.merge_dedup_only import (
    ClaimSuppressionRuleAction,
    _claim_target_state,
    _empty_summary,
)


def _claim(confidence: float) -> KnowledgeClaim:
    return KnowledgeClaim(text="subject relates object", confidence=confidence)


def test_disable_rejects_but_preserves_confidence() -> None:
    state, confidence = _claim_target_state(_claim(0.9), ClaimSuppressionRuleAction.disable)
    assert state == ClaimCurationState.rejected
    assert confidence == 0.9


def test_demote_rejects_and_caps_confidence_at_point_two() -> None:
    state, confidence = _claim_target_state(_claim(0.9), ClaimSuppressionRuleAction.demote)
    assert state == ClaimCurationState.rejected
    assert confidence == 0.2


def test_demote_leaves_already_low_confidence_unchanged() -> None:
    # min(0.1, 0.2) == 0.1 — capping never raises a low score.
    _, confidence = _claim_target_state(_claim(0.1), ClaimSuppressionRuleAction.demote)
    assert confidence == 0.1


def test_prune_uses_the_same_cap_as_demote() -> None:
    # Only `disable` is special-cased; prune must also cap (not preserve) so the
    # contract can't silently widen to "prune keeps full confidence".
    state, confidence = _claim_target_state(_claim(0.95), ClaimSuppressionRuleAction.prune)
    assert state == ClaimCurationState.rejected
    assert confidence == 0.2


def test_empty_summary_is_all_zero_with_expected_keys() -> None:
    summary = _empty_summary()
    expected_keys = {
        "documents_scoped",
        "entities_examined",
        "entities_merged",
        "entities_reclassified",
        "entities_suppressed",
        "claims_examined",
        "claims_suppressed",
        "claims_pruned_trivial",
        "claim_merges",
    }
    assert set(summary) == expected_keys
    assert all(value == 0 for value in summary.values())
