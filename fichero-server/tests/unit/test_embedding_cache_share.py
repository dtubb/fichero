"""The test base's embedding cache links each real cached model, never the whole real dir (2026-11-28)."""

from tests._real_state_guard import embedding_model_cached, share_real_embedding_cache


def test_a_new_entry_in_the_shared_embedding_cache_lands_in_the_test_base_and_the_models_stay_linked(tmp_path):
    real = tmp_path / "real" / "embeddings"
    snap = real / "models--qdrant--multilingual-e5-large-onnx" / "snapshots" / "abc"
    snap.mkdir(parents=True)
    (real / "CACHEDIR.TAG").write_text("tag")
    cache = share_real_embedding_cache(tmp_path / "base" / "models", real)
    assert cache is not None and cache.is_dir() and not cache.is_symlink()
    assert (cache / "models--qdrant--multilingual-e5-large-onnx").is_symlink()
    assert embedding_model_cached(cache, "intfloat/multilingual-e5-large")
    (cache / "tmp").mkdir()  # fastembed's fallback download dir
    assert not (real / "tmp").exists(), "a new entry stays in the test base"
    assert share_real_embedding_cache(tmp_path / "base" / "models", real) == cache, "a second call keeps it"
    assert share_real_embedding_cache(tmp_path / "x", tmp_path / "none") is None
