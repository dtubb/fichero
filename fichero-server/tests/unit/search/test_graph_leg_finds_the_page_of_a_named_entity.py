"""The graph leg of `/api/search` turns an entity hit into the pages of its statements (#6786,
`search.graph.names-lead-to-their-pages`). The entity hit has the shape the entity search returns: a plain record."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fichero_server.models import DocType, Document, FileType
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity


@pytest.fixture(autouse=True)
def _models_dir_in_tmp(tmp_path, monkeypatch):
    """Saving an entity tries to embed it; where the model is absent that makes its cache folder, kept under tmp_path."""
    from fichero_server.llm import local_models

    monkeypatch.setattr(local_models, "MODELS_BASE", tmp_path / "models")


def test_a_page_whose_text_never_has_the_word_is_found_through_the_entity_it_is_about(client, db, caplog) -> None:
    doc = Document(
        id="ledger", name="Ledger 1948", page_content="Weekly accounts and rainfall notes.",
        doc_type=DocType.file, file_type=FileType.text,
    )
    db.save(doc)
    entity = KnowledgeEntity(id="ent-asprilla", canonical_name="Asprilla")
    db.save(entity)
    db.save(
        KnowledgeClaim(
            id="claim-asprilla-ledger", text="Asprilla kept the ledger.",
            source_document_id=doc.id, entity_ids=[entity.id],
        )
    )
    hit = {**entity.model_dump(), "similarity_score": 0.9}

    with patch("fichero_server.api.routes.search.core._run_entity_semantic_queries", return_value=[hit]):
        r = client.post(
            "/api/search",
            json={"query": "Asprilla", "search_type": "fulltext", "min_score": 0.0, "include": ["content", "entities"]},
        )

    assert r.status_code == 200, r.text
    by_id = {row["document_id"]: row for row in r.json()["results"]}
    assert by_id[doc.id]["metadata"]["via"] == "graph"
    assert by_id[doc.id]["metadata"]["entity_name"] == "Asprilla"
    assert by_id[doc.id]["kg_entity_ids"] == ["ent-asprilla"]
    assert "graph-leg claim lookup failed" not in caplog.text
