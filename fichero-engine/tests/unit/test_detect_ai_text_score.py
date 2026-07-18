from fichero.workflows.tools.detect_ai_text import _score_text


def test_ai_text_score_records_empty_and_repetitive_text_features() -> None:
    empty_score, empty_features = _score_text("")
    repeated_score, repeated_features = _score_text("In conclusion, word word word word word word word word.")

    assert (empty_score, empty_features) == (0.0, {"word_count": 0, "char_count": 0})
    assert repeated_score >= 0.45
    assert repeated_features["repeated_bigrams"] >= 3
