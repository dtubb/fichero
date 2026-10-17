"""#5528: a test that embeds for real is skipped, with the reason, where the embedding model is not on
disk -- decided by looking in the cache, not by what this Mac happens to have."""
from __future__ import annotations

from tests._real_state_guard import embedding_model_cached

E5 = "intfloat/multilingual-e5-large"


def test_a_missing_or_empty_cache_has_no_model(tmp_path):
    assert not embedding_model_cached(tmp_path / "nothing", E5)
    assert not embedding_model_cached(tmp_path, E5)


def test_a_model_with_no_downloaded_snapshot_is_not_cached(tmp_path):
    (tmp_path / "models--qdrant--multilingual-e5-large-onnx" / "snapshots").mkdir(parents=True)
    assert not embedding_model_cached(tmp_path, E5)


def test_the_downloaded_model_is_found_by_its_short_name_and_another_is_not(tmp_path):
    snapshot = tmp_path / "models--qdrant--multilingual-e5-large-onnx" / "snapshots" / "abc"
    snapshot.mkdir(parents=True)
    (snapshot / "model.onnx").write_bytes(b"x")
    assert embedding_model_cached(tmp_path, E5)
    assert not embedding_model_cached(tmp_path, "BAAI/bge-m3")
