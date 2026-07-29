"""Catalog guards for locally downloadable embedding models."""

from __future__ import annotations


def test_embedding_catalog_preserves_current_default() -> None:
    from fichero_server.db.embeddings import DEFAULT_MODEL
    from fichero_server.llm.local_models import EMBEDDINGS_MODELS

    assert DEFAULT_MODEL == "intfloat/multilingual-e5-large"

    default = EMBEDDINGS_MODELS[DEFAULT_MODEL]
    assert default["is_current_default"] is True
    assert default["embedding_space_status"] == "current_default"
    assert default["is_supported_embedding_space"] is True
    assert default["requires_explicit_migration"] is False


def test_lighter_english_embedding_option_lists_ram_and_quality_note() -> None:
    from fichero_server.llm.local_models import EMBEDDINGS_MODELS

    bge_small = EMBEDDINGS_MODELS["BAAI/bge-small-en-v1.5"]

    assert bge_small["languages"] == "English"
    assert bge_small["disk_mb"] == 130
    assert bge_small["ram_mb"] == 130
    assert "English" in bge_small["quality"]
    assert "low-RAM" in bge_small["speed"]


def test_download_only_embedding_models_are_not_silent_search_spaces() -> None:
    from fichero_server.llm.local_models import EMBEDDINGS_MODELS

    bge_small = EMBEDDINGS_MODELS["BAAI/bge-small-en-v1.5"]

    assert bge_small["is_current_default"] is False
    assert bge_small["is_supported_embedding_space"] is False
    assert bge_small["embedding_space_status"] == "download_only"
    assert bge_small["requires_explicit_migration"] is True
    assert "not currently wired" in bge_small["activation_note"]


def test_catalog_marks_supported_opt_in_embedding_spaces_only() -> None:
    from fichero_server.db.embeddings import BGE_M3_MODEL
    from fichero_server.llm.local_models import EMBEDDINGS_MODELS

    bge_m3 = EMBEDDINGS_MODELS[BGE_M3_MODEL]
    bge_small = EMBEDDINGS_MODELS["BAAI/bge-small-en-v1.5"]
    e5_small = EMBEDDINGS_MODELS["intfloat/multilingual-e5-small"]

    assert bge_m3["is_supported_embedding_space"] is True
    assert bge_m3["embedding_space_status"] == "supported_opt_in"
    assert bge_m3["requires_explicit_migration"] is True
    assert bge_small["is_supported_embedding_space"] is False
    assert e5_small["is_supported_embedding_space"] is False


def test_manager_lists_embedding_metadata_without_download(tmp_path, monkeypatch) -> None:
    from fichero_server.llm import local_models

    monkeypatch.setattr(local_models, "MODELS_BASE", tmp_path / "models")

    listed = {
        model.model_id: model
        for model in local_models.LocalModelManager().list_embeddings_models()
    }

    bge_small = listed["BAAI/bge-small-en-v1.5"]
    assert bge_small.is_downloaded is False
    assert bge_small.expected_size_mb == 130
    assert bge_small.metadata["ram_mb"] == 130
    assert bge_small.metadata["embedding_space_status"] == "download_only"
