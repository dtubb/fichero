"""Unit tests for deterministic model recommendations."""

import json

from fichero.llm.model_recommendations import (
    ModelRecommendationCandidate,
    ModelRecommendationRequest,
    build_model_recommendations,
)


def test_local_private_candidate_wins_and_cloud_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_LANGUAGE_COVERAGE_DIR", str(tmp_path))
    (tmp_path / "apple__apple-foundation.json").write_text(
        json.dumps({"coverage": {"es": {"score": 0.94}}}),
        encoding="utf-8",
    )
    (tmp_path / "openai__gpt-4o.json").write_text(
        json.dumps({"coverage": {"es": {"score": 0.99}}}),
        encoding="utf-8",
    )

    response = build_model_recommendations(
        ModelRecommendationRequest(
            language="es",
            task="paleography",
            capability="text",
            private=True,
            candidates=[
                ModelRecommendationCandidate(
                    provider="openai",
                    model="gpt-4o",
                    capabilities=["text"],
                    input_price_per_million=5.0,
                    output_price_per_million=15.0,
                ),
                ModelRecommendationCandidate(
                    provider="apple",
                    model="apple-foundation",
                    capabilities=["text"],
                    input_price_per_million=0.0,
                    output_price_per_million=0.0,
                ),
            ],
        )
    )

    assert response.items[0].provider == "apple"
    assert response.items[0].privacy_posture == "builtin_local"
    assert response.items[0].cost.status == "free"
    refused = response.items[1]
    assert refused.provider == "openai"
    assert refused.availability_status == "refused"
    assert not refused.available
    assert any("local_only/private mode" in warning for warning in refused.warnings)


def test_unknown_cloud_cost_is_typed_unknown_and_not_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_LANGUAGE_COVERAGE_DIR", str(tmp_path))

    response = build_model_recommendations(
        ModelRecommendationRequest(
            language="fr",
            candidates=[
                ModelRecommendationCandidate(
                    provider="anthropic",
                    model="claude-unknown-price",
                    capabilities=["text"],
                )
            ],
        )
    )

    item = response.items[0]
    assert item.cost.status == "unknown"
    assert item.cost.input_price_per_million is None
    assert item.cost.output_price_per_million is None
    assert item.component_scores.cost == 0.35
    assert any("not treated as free" in warning for warning in item.warnings)


def test_loove_env_coverage_influences_ranking(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_LANGUAGE_COVERAGE_DIR", str(tmp_path))
    (tmp_path / "openai__gpt-4o-mini.json").write_text(
        json.dumps({"coverage": {"ja": {"score": 0.98}}}),
        encoding="utf-8",
    )
    (tmp_path / "apple__apple-foundation.json").write_text(
        json.dumps({"coverage": {"ja": {"score": 0.55}}}),
        encoding="utf-8",
    )

    response = build_model_recommendations(
        ModelRecommendationRequest(
            language="ja",
            candidates=[
                ModelRecommendationCandidate(
                    provider="apple",
                    model="apple-foundation",
                    capabilities=["text"],
                    input_price_per_million=0.0,
                    output_price_per_million=0.0,
                ),
                ModelRecommendationCandidate(
                    provider="openai",
                    model="gpt-4o-mini",
                    capabilities=["text"],
                    input_price_per_million=0.15,
                    output_price_per_million=0.60,
                ),
            ],
        )
    )

    assert response.items[0].provider == "openai"
    assert response.items[0].language_fit.status == "derived"
    assert response.items[0].language_fit.coverage_score == 0.98
    assert response.items[1].language_fit.coverage_score == 0.55
