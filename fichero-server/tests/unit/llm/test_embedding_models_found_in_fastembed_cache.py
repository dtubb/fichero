"""An embedding model FastEmbed cached under its source repo lists as downloaded (2026-10-10).

The demo app listed the default search model (multilingual-e5-large) and bge-m3 as not downloaded while
both were on disk: FastEmbed caches e5-large as `models--qdrant--multilingual-e5-large-onnx`, the repo it
really downloads from, and the listing looked only for `intfloat--multilingual-e5-large`.
"""

from __future__ import annotations

from fichero_server.llm.local_models import LocalModelManager


def _manager(tmp_path) -> LocalModelManager:
    manager = LocalModelManager.__new__(LocalModelManager)
    manager.embeddings_path = tmp_path
    return manager


def test_a_model_cached_under_its_source_repo_lists_as_downloaded(tmp_path) -> None:
    for folder in ("models--qdrant--multilingual-e5-large-onnx", "models--BAAI--bge-m3"):
        (tmp_path / folder / "snapshots").mkdir(parents=True)
        (tmp_path / folder / "snapshots" / "model.onnx").write_bytes(b"x")
    listed = {m.model_id: m for m in _manager(tmp_path).list_embeddings_models()}
    assert listed["intfloat/multilingual-e5-large"].is_downloaded
    assert listed["BAAI/bge-m3"].is_downloaded
    assert listed["intfloat/multilingual-e5-large"].download_state == "installed"
    assert not listed["BAAI/bge-small-en-v1.5"].is_downloaded
