"""Unit tests for local language-coverage scoring."""

import json

from fichero.llm.language_coverage import (
    LanguageFitModelSpec,
    evaluate_language_fit,
    language_spec,
    normalize_model_spec,
    recommend_language_fit,
    score_band,
)


def test_normalize_model_spec_preserves_model_id_case():
    spec = normalize_model_spec(" OpenAI ", " GPT-4o-Mini ")
    assert spec.provider == "openai"
    assert spec.model == "GPT-4o-Mini"


def test_score_band_boundaries():
    assert score_band(0.94) == "excellent"
    assert score_band(0.76) == "good"
    assert score_band(0.50) == "limited"
    assert score_band(0.49) == "poor"
    assert score_band(None) == "unknown"


def test_heuristic_fallback_is_transparent(tmp_path):
    response = recommend_language_fit(
        "es",
        [LanguageFitModelSpec(provider="openai", model="gpt-4o-mini")],
        coverage_dir=tmp_path,
    )

    result = response.results[0]
    assert result.status == "heuristic"
    assert result.coverage_score is not None
    assert result.source.kind == "heuristic_fallback"
    assert "No LOOVE-derived coverage file" in result.warnings[0]
    assert "No cloud calls" in response.privacy_note


def test_derived_loove_json_wins_over_heuristic(tmp_path):
    coverage_file = tmp_path / "openai__gpt-4o-mini.json"
    coverage_file.write_text(
        json.dumps(
            {
                "model_id": "gpt-4o-mini",
                "generated_at": "2026-06-14T00:00:00Z",
                "coverage": {
                    "es": {
                        "language_name": "Spanish",
                        "script": "Latin",
                        "weighted_coverage_score": 0.971,
                        "tier_counts": {
                            "0": 92,
                            "1": 5,
                            "2": 2,
                            "3": 1,
                        },
                        "fertility": {
                            "tokens_per_char": 0.31,
                            "tokens_per_word": 1.42,
                            "sample_chars": 400,
                            "sample_tokens": 124,
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_language_fit(
        LanguageFitModelSpec(provider="openai", model="gpt-4o-mini"),
        language_spec("es"),
        coverage_dir=tmp_path,
    )

    assert result.status == "derived"
    assert result.coverage_score == 0.971
    assert result.score_band == "excellent"
    assert result.source.kind == "loove_derived_json"
    assert result.source.coverage_path == str(coverage_file)
    assert result.tier_counts is not None
    assert result.tier_counts.tier_0_native == 92
    assert result.fertility is not None
    assert result.fertility.tokens_per_word == 1.42


def test_derived_loove_json_can_score_language_outside_builtin_table(tmp_path):
    (tmp_path / "example-model.json").write_text(
        json.dumps(
            {
                "model_id": "example-model",
                "coverage": {
                    "ast": {
                        "language_name": "Asturian",
                        "script": "Latin",
                        "score": 0.88,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_language_fit(
        LanguageFitModelSpec(provider="local", model="example-model"),
        language_spec("ast"),
        coverage_dir=tmp_path,
    )

    assert result.status == "derived"
    assert result.language.name == "Asturian"
    assert result.coverage_score == 0.88


def test_missing_unsupported_language_returns_typed_warning(tmp_path):
    result = evaluate_language_fit(
        LanguageFitModelSpec(provider="unknown", model="mystery-model"),
        language_spec("zz"),
        coverage_dir=tmp_path,
    )

    assert result.status == "unsupported_language"
    assert result.coverage_score is None
    assert result.score_band == "unknown"
    assert result.source.kind == "missing"
    assert "No local language metadata" in result.warnings[0]
