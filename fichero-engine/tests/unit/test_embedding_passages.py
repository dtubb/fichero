"""Embedding model formatting and passage-level indexing tests."""

from __future__ import annotations

import sys
import types
from unittest.mock import patch

import pytest

from fichero import db_embeddings
from fichero.db import Database
from fichero.db_embeddings import (
    EMBEDDING_MODEL_ID_FIELD,
    PINNED_EMBEDDING_MODEL_ID,
    PINNED_EMBEDDING_POOLING,
    EmbeddingSpaceMismatchError,
    format_for_model,
    split_text_passages,
)
from fichero.models import DocType, Document


def test_format_for_model_e5_adds_role_prefixes() -> None:
    assert (
        format_for_model("intfloat/multilingual-e5-large", "Leidy", "query")
        == "query: Leidy"
    )
    assert (
        format_for_model("intfloat/multilingual-e5-base", "Leidy", "passage")
        == "passage: Leidy"
    )


def test_format_for_model_bge_m3_has_no_prefix() -> None:
    assert format_for_model("BAAI/bge-m3", "Leidy", "query") == "Leidy"
    assert format_for_model("BAAI/bge-m3", "Leidy", "passage") == "Leidy"


def test_default_model_and_env_override(monkeypatch) -> None:
    class _Dummy(db_embeddings.DatabaseEmbeddingMixin):
        pass

    dummy = _Dummy()
    monkeypatch.setenv("FICHERO_EMBED_MODEL", "BAAI/bge-m3")
    assert db_embeddings.DEFAULT_MODEL == "intfloat/multilingual-e5-large"
    assert dummy._get_embedding_model_name() == "intfloat/multilingual-e5-large"
    assert dummy._get_embedding_model_id() == PINNED_EMBEDDING_MODEL_ID
    assert dummy._get_embedding_space().pooling == PINNED_EMBEDDING_POOLING


def test_pinned_embedding_space_ignores_mutable_app_setting(monkeypatch) -> None:
    class _Dummy(db_embeddings.DatabaseEmbeddingMixin):
        pass

    class FakeAppDB:
        @staticmethod
        def get_setting(key: str):
            if key == "default_embeddings_model":
                return "BAAI/bge-m3"
            return None

    monkeypatch.setitem(
        sys.modules,
        "fichero.app_db",
        types.SimpleNamespace(get_app_db=lambda: FakeAppDB()),
    )
    dummy = _Dummy()
    assert dummy._get_embedding_model_name() == db_embeddings.DEFAULT_MODEL
    assert dummy._get_embedding_space().pooling == PINNED_EMBEDDING_POOLING


def test_split_text_passages_offsets_overlap_and_reconstruct() -> None:
    text = (
        "First paragraph has enough prose to exceed a tiny test window. "
        "It keeps going for another sentence.\n\n"
        "Second paragraph carries the target sentence. "
        "The final sentence closes the page."
    )

    passages = split_text_passages(
        text,
        document_id="page-1",
        page_id="page-1",
        max_chars=96,
        overlap_chars=18,
    )

    assert len(passages) >= 2
    for passage in passages:
        start = passage.anchor.char_start
        end = passage.anchor.char_end
        assert start is not None
        assert end is not None
        assert passage.text == text[start:end]

    for left, right in zip(passages, passages[1:]):
        assert right.anchor.char_start is not None
        assert left.anchor.char_end is not None
        assert right.anchor.char_start < left.anchor.char_end

    rebuilt = passages[0].text
    prior_end = passages[0].anchor.char_end
    for passage in passages[1:]:
        assert passage.anchor.char_start is not None
        assert passage.anchor.char_end is not None
        rebuilt += text[prior_end : passage.anchor.char_end]
        prior_end = passage.anchor.char_end
    assert rebuilt == text[passages[0].anchor.char_start : passages[-1].anchor.char_end]


def test_passage_vectors_store_anchor_and_search_returns_matching_passage(
    tmp_path,
) -> None:
    db = Database(tmp_path / "passages.duckdb")
    doc = Document(
        id="page-needle",
        name="archive.pdf - Page 7",
        doc_type=DocType.page,
        sequence=7,
        page_content=(
            "Alpha correspondence about unrelated household accounts. " * 10
            + "\n\n"
            + "The exact target passage says Camilo found the mining ledger. "
            + "This sentence supplies retrieval context."
        ),
    )
    db.save(doc)

    def _vectors(texts: list[str], *, role: str = "passage") -> list[list[float]]:
        assert role == "passage"
        return [[1.0, 0.0] if "Camilo" in text else [0.0, 1.0] for text in texts]

    with patch.object(db, "_embed_texts", side_effect=_vectors):
        assert db.embed(doc) is True

    table = db.lance.open_table("embeddings")
    rows = table.search().limit(100).to_list()
    camilo_rows = [row for row in rows if "Camilo" in row["text"]]
    assert camilo_rows
    assert camilo_rows[0]["document_id"] == doc.id
    assert camilo_rows[0]["page_id"] == doc.id
    assert camilo_rows[0]["char_start"] < camilo_rows[0]["char_end"]
    assert doc.page_content[
        camilo_rows[0]["char_start"] : camilo_rows[0]["char_end"]
    ] == camilo_rows[0]["text"]

    with patch.object(db, "_embed_text", return_value=[1.0, 0.0]):
        results, total_count, _stats = db.search(
            "Camilo mining ledger",
            search_type="semantic",
            min_score=0.55,
        )

    assert total_count == 1
    assert results[0].document_id == doc.id
    assert "Camilo found the mining ledger" in results[0].content_preview
    assert results[0].metadata["embedding_scope"] == "passage"
    assert results[0].metadata["passage_id"]
    assert results[0].metadata["page_id"] == doc.id
    assert results[0].metadata["char_start"] < results[0].metadata["char_end"]
    row = db.lance.open_table("embeddings").search().limit(1).to_list()[0]
    assert row[EMBEDDING_MODEL_ID_FIELD] == PINNED_EMBEDDING_MODEL_ID
    db.close()


def test_semantic_search_refuses_mismatched_known_embedding_model_id(tmp_path) -> None:
    db = Database(tmp_path / "mismatch.duckdb")
    doc = Document(
        id="page-mismatch",
        name="mismatch.txt",
        doc_type=DocType.page,
        page_content="Camilo found the ledger with enough text for semantic search.",
    )
    db.save(doc)

    with patch.object(db, "_embed_text", return_value=[1.0, 0.0]):
        db.save_embedding(doc, [1.0, 0.0], doc.page_content)

    row = db.lance.open_table("embeddings").search().limit(1).to_list()[0]
    row[EMBEDDING_MODEL_ID_FIELD] = "BAAI/bge-m3|pooling=mean|normalization=l2"
    db._delete_embedding_rows("document_id", doc.id)
    db.save_vectors("embeddings", [row], replace=True)

    with patch.object(db, "_embed_text", return_value=[1.0, 0.0]):
        with patch.object(db, "_is_active_document_id", return_value=True):
            with pytest.raises(EmbeddingSpaceMismatchError, match="Embedding model mismatch"):
                db.search("Camilo ledger", search_type="semantic", min_score=0.0)

    db.close()


def test_semantic_search_accepts_matching_known_embedding_model_id(tmp_path) -> None:
    db = Database(tmp_path / "match.duckdb")
    doc = Document(
        id="page-match",
        name="match.txt",
        doc_type=DocType.page,
        page_content="Camilo found the ledger with enough text for semantic search.",
    )
    db.save(doc)

    with patch.object(db, "_embed_text", return_value=[1.0, 0.0]):
        db.save_embedding(doc, [1.0, 0.0], doc.page_content)
        with patch.object(db, "_is_active_document_id", return_value=True):
            results, total_count, _stats = db.search(
                "Camilo ledger",
                search_type="semantic",
                min_score=0.0,
            )

    assert total_count == 1
    assert results[0].document_id == doc.id
    db.close()


def test_local_embeddings_still_work_when_local_only_enabled(tmp_path, monkeypatch) -> None:
    db = Database(tmp_path / "local-only.duckdb")
    doc = Document(
        id="page-local",
        name="local.txt",
        doc_type=DocType.page,
        page_content="Enough local text to create a pinned FastEmbed passage vector.",
    )
    db.save(doc)
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")

    with patch.object(db, "_embed_text", return_value=[1.0, 0.0]):
        assert db.embed(doc) is True

    row = db.lance.open_table("embeddings").search().limit(1).to_list()[0]
    assert row[EMBEDDING_MODEL_ID_FIELD] == PINNED_EMBEDDING_MODEL_ID
    db.close()


def test_non_latin_passages_store_and_embed_without_error(tmp_path) -> None:
    db = Database(tmp_path / "unicode.duckdb")
    text = (
        "Дѣло і архивъ сохраняют старую орфографію.\n\n"
        "中文段落保留在同一个页面中。\n\n"
        "देवनागरी पाठ भी उसी मार्ग से संग्रहित होता है।"
    )
    doc = Document(id="unicode-page", name="unicode.txt", page_content=text)
    db.save(doc)

    with patch.object(db, "_embed_text", return_value=[1.0, 0.0]):
        assert db.embed(doc) is True

    rows = db.lance.open_table("embeddings").search().limit(10).to_list()
    assert len(rows) == 1
    assert rows[0]["text"] == text
    assert rows[0]["char_start"] == 0
    assert rows[0]["char_end"] == len(text)
    db.close()


def test_reindex_all_batches_documents_without_changing_vector_count(tmp_path) -> None:
    db = Database(tmp_path / "reindex-batch.duckdb")
    docs = [
        Document(
            id=f"doc-{idx}",
            name=f"Doc {idx}",
            doc_type=DocType.page,
            page_content=f"Document {idx} has enough searchable prose for embedding.",
        )
        for idx in range(3)
    ]
    for doc in docs:
        db.save(doc)

    embed_batches: list[list[str]] = []

    def _vectors(texts: list[str], *, role: str = "passage") -> list[list[float]]:
        assert role == "passage"
        embed_batches.append(list(texts))
        return [[float(len(embed_batches)), float(i)] for i, _text in enumerate(texts)]

    with patch.object(db, "_embed_texts", side_effect=_vectors):
        indexed = db.reindex_all(batch_size=2)

    assert indexed == 3
    assert [len(batch) for batch in embed_batches] == [2, 1]

    rows = db.lance.open_table("embeddings").search().limit(10).to_list()
    assert len(rows) == 3
    assert {row["document_id"] for row in rows} == {doc.id for doc in docs}
    db.close()
