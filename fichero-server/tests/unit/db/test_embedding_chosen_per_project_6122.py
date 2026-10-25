"""#6122 (`search.embedding.chosen-at-project-creation`): a project's embedding model is chosen when it is created and kept
in its package; that project's embeds and its recipe's search step use it; a project that holds vectors is not switched."""
from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.db import embeddings
from fichero_server.db.embedding_choice import read_choice, write_choice


def test_a_project_without_a_choice_uses_the_engines_default(tmp_path, monkeypatch):
    monkeypatch.delenv(embeddings.EMBED_MODEL_ENV, raising=False)
    assert embeddings.library_embedding_space(tmp_path) is embeddings.BGE_M3_EMBEDDING_SPACE
    assert embeddings.search_embedder(tmp_path) == "BAAI/bge-m3"


def test_the_projects_own_choice_wins_over_the_default_and_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(embeddings.EMBED_MODEL_ENV, "BAAI/bge-m3")
    write_choice(tmp_path, "intfloat/multilingual-e5-large")
    assert read_choice(tmp_path) == "intfloat/multilingual-e5-large"
    assert embeddings.library_embedding_space(tmp_path) is embeddings.PINNED_EMBEDDING_SPACE
    assert embeddings.search_embedder(tmp_path) == "intfloat/multilingual-e5-large"


@pytest.mark.parametrize("content", ["not json", "[]", '{"model": ""}', '{"model": "no/such-model"}'])
def test_an_unreadable_or_unsupported_choice_falls_back_to_the_default(tmp_path, monkeypatch, content):
    monkeypatch.delenv(embeddings.EMBED_MODEL_ENV, raising=False)
    (tmp_path / "embedding.json").write_text(content, encoding="utf-8")
    assert embeddings.library_embedding_space(tmp_path) is embeddings.BGE_M3_EMBEDDING_SPACE


def test_create_library_keeps_the_choice_and_refuses_an_unsupported_model(client, tmp_path, monkeypatch):
    monkeypatch.delenv(embeddings.EMBED_MODEL_ENV, raising=False)
    package = tmp_path / "Chosen.fichero"
    bad = client.post("/api/library", json={"path": str(package), "embedding_model": "no/such-model"})
    assert bad.status_code == 422 and not package.exists()
    ok = client.post("/api/library", json={"path": str(package), "embedding_model": "intfloat/multilingual-e5-large"})
    assert ok.status_code == 200, ok.text
    assert read_choice(Path(package)) == "intfloat/multilingual-e5-large"
    # An existing project keeps its own choice when asked to be created again.
    again = client.post("/api/library", json={"path": str(package), "embedding_model": "BAAI/bge-m3"})
    assert again.status_code == 200 and read_choice(Path(package)) == "intfloat/multilingual-e5-large"


def test_the_choice_route_changes_an_empty_project_and_refuses_one_that_holds_vectors(client, monkeypatch):
    from fichero_server.db import Database

    monkeypatch.delenv(embeddings.EMBED_MODEL_ENV, raising=False)
    got = client.get("/api/search/embedding")
    assert got.status_code == 200, got.text
    assert got.json()["model"] == "BAAI/bge-m3" and got.json()["changeable"] is True
    assert "intfloat/multilingual-e5-large" in got.json()["models"]

    put = client.put("/api/search/embedding", json={"model": "intfloat/multilingual-e5-large"})
    assert put.status_code == 200 and put.json()["model"] == "intfloat/multilingual-e5-large"
    assert client.put("/api/search/embedding", json={"model": "no/such-model"}).status_code == 422

    monkeypatch.setattr(Database, "_vector_table_stats", lambda self, name: {"indexed_count": 5, "table_exists": True})
    held = client.get("/api/search/embedding").json()
    assert held["vectors"] == 5 and held["changeable"] is False
    refused = client.put("/api/search/embedding", json={"model": "BAAI/bge-m3"})
    assert refused.status_code == 409 and "re-embed" in refused.json()["detail"]
    same = client.put("/api/search/embedding", json={"model": "intfloat/multilingual-e5-large"})
    assert same.status_code == 200  # choosing what it already uses changes nothing
