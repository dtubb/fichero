"""`embed_process._cached` finds the real cache folders: the pinned e5 is fetched from qdrant/multilingual-e5-large-onnx
(the M4's cache: models--qdrant--multilingual-e5-large-onnx/snapshots/...), and bge-m3 from BAAI/bge-m3."""
from __future__ import annotations

import pytest

from fichero_server.db import embed_process, embeddings


@pytest.mark.parametrize("name, folder", [
    (embeddings.PINNED_EMBEDDING_SPACE.fastembed_model_name, "models--qdrant--multilingual-e5-large-onnx"),
    (embeddings.PINNED_EMBEDDING_SPACE.source_model_name, "models--qdrant--multilingual-e5-large-onnx"),
    (embeddings.BGE_M3_MODEL, "models--BAAI--bge-m3"),
])
def test_the_real_cache_folder_is_found(tmp_path, name, folder):
    assert not embed_process._cached(name, str(tmp_path))
    (tmp_path / folder / "snapshots" / "66076b8dc6e3").mkdir(parents=True)
    assert embed_process._cached(name, str(tmp_path))


def test_a_folder_without_snapshots_is_not_a_cached_model(tmp_path):
    (tmp_path / "models--qdrant--multilingual-e5-large-onnx" / "blobs").mkdir(parents=True)
    assert not embed_process._cached(embeddings.BGE_M3_MODEL, str(tmp_path))
    assert not embed_process._cached(embeddings.PINNED_EMBEDDING_SPACE.source_model_name, str(tmp_path))


@pytest.mark.parametrize("sibling", [
    "models--intfloat--multilingual-e5-large-instruct",
    "models--qdrant--multilingual-e5-large-instruct-onnx",
    "models--BAAI--bge-m3-unsupervised",
])
def test_a_sibling_model_is_not_the_cached_one(tmp_path, sibling):
    (tmp_path / sibling / "snapshots" / "abc").mkdir(parents=True)
    assert not embed_process._cached(embeddings.PINNED_EMBEDDING_SPACE.fastembed_model_name, str(tmp_path))
    assert not embed_process._cached(embeddings.BGE_M3_MODEL, str(tmp_path))
