"""A search reads the entity and claim rows it needs, not every one in the project (#6782,
`search.scale.cost-does-not-grow-with-the-graph`). Rows read are counted where a row becomes a model."""

from __future__ import annotations

from collections import Counter
from unittest.mock import patch

from fichero_server.db import Database
from fichero_server.models import DocType, Document, FileType
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity

N_OTHER = 300


def _seed(db: Database) -> None:
    pages = [
        Document(id="p-hit", name="Letter", doc_type=DocType.page, file_type=FileType.image,
                 page_content="The acequia of San Felipe was cleared."),
        Document(id="p-other", name="Other", doc_type=DocType.page, file_type=FileType.image,
                 page_content="Nothing about the matter here."),
    ]
    db.save_many(pages, new=True)
    db.save_many([KnowledgeEntity(id="e-ace", canonical_name="Acequia", aliases=["Irrigation ditch"])], new=True)
    db.save_many(
        [KnowledgeEntity(id=f"e-{i}", canonical_name=f"Person {i}", aliases=[f"Alias {i}"]) for i in range(N_OTHER)],
        new=True,
    )
    db.save_many(
        [KnowledgeClaim(id="c-hit", text="The acequia was cleared.", source_document_id="p-hit", entity_ids=["e-ace"])]
        + [
            KnowledgeClaim(id=f"c-{i}", text=f"Person {i} signed.", source_document_id="p-other", entity_ids=[f"e-{i}"])
            for i in range(N_OTHER)
        ],
        new=True,
    )


def test_search_reads_only_the_entity_and_claim_rows_it_needs(client, db) -> None:
    _seed(db)
    hydrated: Counter[str] = Counter()
    real = Database._hydrate_row

    def counting(self, model, columns, row):
        hydrated[model.__name__] += 1
        return real(self, model, columns, row)

    with patch.object(Database, "_hydrate_row", counting):
        r = client.post(
            "/api/search",
            json={"query": "acequia", "limit": 10, "include": ["content"], "search_type": "fulltext"},
        )

    assert r.status_code == 200, r.text
    hit = next(x for x in r.json()["results"] if x["document_id"] == "p-hit")
    assert hit["kg_claim_ids"] == ["c-hit"]
    assert hit["kg_entity_ids"] == ["e-ace"]
    assert hydrated["KnowledgeEntity"] <= 5
    assert hydrated["KnowledgeClaim"] <= 5


def test_an_alias_still_widens_the_query_and_reads_only_the_matching_entity(db) -> None:
    _seed(db)
    hydrated: Counter[str] = Counter()
    real = Database._hydrate_row

    def counting(self, model, columns, row):
        hydrated[model.__name__] += 1
        return real(self, model, columns, row)

    with patch.object(Database, "_hydrate_row", counting):
        terms, entity_ids = db._expand_query_with_entity_aliases("irrigation ditch")

    assert entity_ids == {"e-ace"}
    assert "acequia" in terms
    assert hydrated["KnowledgeEntity"] == 1
