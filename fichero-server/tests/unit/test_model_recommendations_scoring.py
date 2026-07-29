"""Unit coverage for the pure scoring functions in
``fichero_server.llm.model_recommendations``. The existing ``test_model_recommendations.py``
covers a few end-to-end ranking scenarios; this file locks the individual score
components (weights, thresholds, directions) and the rank assignment. No network
— the recommender composes local catalog metadata only.
"""

from __future__ import annotations


from fichero_server.llm.model_recommendations import (
    ModelRecommendationCandidate as Candidate,
    ModelRecommendationCost as Cost,
    ModelRecommendationRequest as Request,
    _availability_status,
    _capability_score,
    _cost_metadata,
    _cost_score,
    _privacy_posture,
    _privacy_score,
    _total_score,
    build_model_recommendations,
)


def _req(**kw) -> Request:
    kw.setdefault("language", "en")
    return Request(**kw)


# ===========================================================================
# _capability_score
# ===========================================================================


def test_capability_no_requirement_is_full():
    assert _capability_score(None, []) == (1.0, None)


def test_capability_unknown_metadata_is_partial_with_warning():
    score, warning = _capability_score("text", [])
    assert score == 0.8
    assert warning and "unknown" in warning


def test_capability_match_and_mismatch():
    assert _capability_score("text", ["text", "vision"]) == (1.0, None)
    score, warning = _capability_score("vision", ["text"])
    assert score == 0.0
    assert warning and "does not advertise" in warning


def test_capability_match_is_case_insensitive():
    assert _capability_score("vision", ["Vision", "TEXT"])[0] == 1.0


# ===========================================================================
# _cost_score — direction + thresholds
# ===========================================================================


def _cost(status, total=0.0):
    return Cost(status=status, note="", input_price_per_million=total, output_price_per_million=0.0)


def test_cost_score_free_and_unknown():
    assert _cost_score(_cost("free")) == 1.0
    assert _cost_score(_cost("unknown")) == 0.35


def test_cost_score_known_zero_is_high():
    assert _cost_score(_cost("known", 0.0)) == 0.9


def test_cost_score_decreases_with_price():
    cheap = _cost_score(_cost("known", 5.0))
    mid = _cost_score(_cost("known", 25.0))
    expensive = _cost_score(_cost("known", 100.0))
    assert cheap > mid > expensive
    assert mid == 0.5
    assert expensive == 0.05  # clamped floor


# ===========================================================================
# _privacy_score
# ===========================================================================


def test_privacy_score_local_postures_high():
    assert _privacy_score("builtin_local", _req()) == 1.0
    assert _privacy_score("local", _req()) == 0.95


def test_privacy_score_cloud_penalised_when_private():
    assert _privacy_score("cloud", _req()) == 0.55
    assert _privacy_score("cloud", _req(private=True)) == 0.0
    assert _privacy_score("cloud", _req(local_only=True)) == 0.0


def test_privacy_score_unknown_posture():
    assert _privacy_score("unknown", _req()) == 0.65
    assert _privacy_score("unknown", _req(private=True)) == 0.4


# ===========================================================================
# _total_score — weight invariant
# ===========================================================================


def test_total_score_all_perfect_is_one():
    # The component weights sum to 1.0, so an all-perfect candidate scores 1.0.
    assert _total_score(
        language_score=1.0, cost_score=1.0, privacy_score=1.0,
        availability_score=1.0, capability_score=1.0,
    ) == 1.0


def test_total_score_none_language_uses_default_weight():
    # None language fit -> treated as 0.3; only the language term contributes.
    assert _total_score(
        language_score=None, cost_score=0.0, privacy_score=0.0,
        availability_score=0.0, capability_score=0.0,
    ) == 0.135  # 0.3 * 0.45


def test_total_score_weighted_combo():
    # 0.5*0.45 + 1*0.20 + 1*0.20 + 1*0.10 + 1*0.05 = 0.775
    assert _total_score(
        language_score=0.5, cost_score=1.0, privacy_score=1.0,
        availability_score=1.0, capability_score=1.0,
    ) == 0.775


# ===========================================================================
# _cost_metadata / _availability_status / _privacy_posture (real catalog)
# ===========================================================================


def test_cost_metadata_local_missing_price_is_free():
    assert _cost_metadata(Candidate(provider="ollama", model="x"), "local").status == "free"


def test_cost_metadata_cloud_missing_price_is_unknown():
    assert _cost_metadata(Candidate(provider="openai", model="x"), "cloud").status == "unknown"


def test_cost_metadata_cloud_with_price_is_known():
    cand = Candidate(provider="openai", model="x", input_price_per_million=1.0, output_price_per_million=2.0)
    assert _cost_metadata(cand, "cloud").status == "known"


def test_availability_status_transitions():
    assert _availability_status(Candidate(provider="openai", model="x", enabled=False), "cloud", _req())[0] == "disabled"
    assert _availability_status(Candidate(provider="openai", model="x"), "cloud", _req(private=True))[0] == "refused"
    assert _availability_status(Candidate(provider="ollama", model="x"), "local", _req())[0] == "enabled"


def test_privacy_posture_from_catalog():
    assert _privacy_posture("ollama") == "local"
    assert _privacy_posture("openai") == "cloud"
    assert _privacy_posture("definitely-not-a-provider") == "unknown"


# ===========================================================================
# build_model_recommendations — ranking + rank assignment
# ===========================================================================


def test_build_assigns_sequential_ranks():
    req = _req(candidates=[
        Candidate(provider="ollama", model="a"),
        Candidate(provider="openai", model="b", input_price_per_million=5.0, output_price_per_million=5.0),
    ])
    resp = build_model_recommendations(req)
    assert [item.rank for item in resp.items] == [1, 2]


def test_build_enabled_outranks_disabled():
    req = _req(candidates=[
        Candidate(provider="openai", model="disabled", enabled=False),
        Candidate(provider="ollama", model="enabled"),
    ])
    resp = build_model_recommendations(req)
    # Available candidates sort ahead of unavailable ones.
    assert resp.items[0].available is True
    assert resp.items[0].model == "enabled"
    assert resp.items[-1].available is False


def test_build_refused_cloud_scores_zero_in_private_mode():
    req = _req(private=True, candidates=[Candidate(provider="openai", model="cloudy")])
    resp = build_model_recommendations(req)
    item = resp.items[0]
    assert item.availability_status == "refused"
    assert item.total_score == 0.0
    assert item.available is False


def test_build_empty_candidates():
    resp = build_model_recommendations(_req(candidates=[]))
    assert resp.items == []
