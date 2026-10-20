"""`activity.engine.embedder-model-missing-says-so` (P2): a search model that is not in the cache and could not be fetched
is said in words as the embed job's reason, never as fastembed's "Could not find the model tar.gz"."""
from __future__ import annotations

from fichero_server.db.embed_process import load_failure_words

RAW = "ValueError: Could not find the model tar.gz file for BAAI/bge-small-en-v1.5"


def test_a_model_that_is_not_downloaded_says_so_in_words():
    words = load_failure_words(RAW, cached=False)
    assert words.startswith("Search can't index yet: its model isn't downloaded")
    assert "tar.gz" not in words and "ValueError" not in words


def test_a_cached_model_that_still_fails_keeps_the_engine_text():
    assert load_failure_words("RuntimeError: onnx runtime failed", cached=True).endswith("onnx runtime failed")
    assert load_failure_words(RAW, cached=True).endswith(RAW)  # cached: not a download problem, so not blamed on one
