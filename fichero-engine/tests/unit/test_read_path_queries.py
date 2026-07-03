from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from fichero.db import Database
from fichero.models import Document, DocType, KnowledgeClaim, KnowledgeEntity


SMALL_N = 5
LARGE_N = 100


def _install_query_counter(monkeypatch) -> Counter[str]:
    counts: Counter[str] = Counter()
    original_all = Database.all
    original_query = Database.query
    original_query_in = Database.query_in
    original_get = Database.get
    original_scoped_entities = Database.knowledge_entity_ids_scoped_to_documents

    def counting_all(self, model_class):
        counts["all"] += 1
        return original_all(self, model_class)

    def counting_query(self, model_class, **filters):
        counts["query"] += 1
        return original_query(self, model_class, **filters)

    def counting_query_in(self, model_class, field_name, values):
        counts["query_in"] += 1
        return original_query_in(self, model_class, field_name, values)

    def counting_get(self, model_class, record_id):
        counts["get"] += 1
        return original_get(self, model_class, record_id)

    def counting_scoped_entities(self, doc_ids):
        counts["knowledge_entity_ids_scoped_to_documents"] += 1
        return original_scoped_entities(self, doc_ids)

    monkeypatch.setattr(Database, "all", counting_all)
    monkeypatch.setattr(Database, "query", counting_query)
    monkeypatch.setattr(Database, "query_in", counting_query_in)
    monkeypatch.setattr(Database, "get", counting_get)
    monkeypatch.setattr(
        Database,
        "knowledge_entity_ids_scoped_to_documents",
        counting_scoped_entities,
    )
    return counts


def _counts_for_request(
    counts: Counter[str],
    request: Callable[[], object],
) -> tuple[object, Counter[str]]:
    before = counts.copy()
    response = request()
    after = counts.copy()
    delta = Counter()
    for key in set(after) | set(before):
        diff = after[key] - before[key]
        if diff:
            delta[key] = diff
    return response, delta


def _seed_documents(db, start: int, stop: int, *, parent_id: str | None = None) -> None:
    for idx in range(start, stop):
        db.save(
            Document(
                id=f"doc-{parent_id or 'root'}-{idx}",
                name=f"Doc {idx}",
                parent_id=parent_id,
                doc_type=DocType.file,
            )
        )


def _seed_entities(db, start: int, stop: int) -> None:
    for idx in range(start, stop):
        db.save(
            KnowledgeEntity(
                id=f"entity-{idx}",
                canonical_name=f"Entity {idx}",
                entity_type="person",
            )
        )


def _seed_claims(db, start: int, stop: int) -> None:
    for idx in range(start, stop):
        db.save(
            KnowledgeClaim(
                id=f"claim-{idx}",
                text=f"Claim {idx}",
            )
        )


def test_documents_list_query_count_does_not_scale_with_row_count(client, db, monkeypatch):
    _seed_documents(db, 0, SMALL_N)
    counts = _install_query_counter(monkeypatch)

    small_response, small_delta = _counts_for_request(
        counts, lambda: client.get("/api/documents")
    )
    assert small_response.status_code == 200

    _seed_documents(db, SMALL_N, LARGE_N)
    large_response, large_delta = _counts_for_request(
        counts, lambda: client.get("/api/documents")
    )
    assert large_response.status_code == 200

    assert small_delta == Counter({"all": 1})
    assert large_delta == small_delta


def test_entities_list_query_count_does_not_scale_with_row_count(client, db, monkeypatch):
    _seed_entities(db, 0, SMALL_N)
    counts = _install_query_counter(monkeypatch)

    small_response, small_delta = _counts_for_request(
        counts, lambda: client.get("/api/entities")
    )
    assert small_response.status_code == 200

    _seed_entities(db, SMALL_N, LARGE_N)
    large_response, large_delta = _counts_for_request(
        counts, lambda: client.get("/api/entities")
    )
    assert large_response.status_code == 200

    assert small_delta == Counter({"all": 1})
    assert large_delta == small_delta


def test_claims_list_query_count_does_not_scale_with_row_count(client, db, monkeypatch):
    _seed_claims(db, 0, SMALL_N)
    counts = _install_query_counter(monkeypatch)

    small_response, small_delta = _counts_for_request(
        counts, lambda: client.get("/api/claims")
    )
    assert small_response.status_code == 200

    _seed_claims(db, SMALL_N, LARGE_N)
    large_response, large_delta = _counts_for_request(
        counts, lambda: client.get("/api/claims")
    )
    assert large_response.status_code == 200

    assert small_delta == Counter({"all": 1})
    assert large_delta == small_delta


def test_library_tree_children_query_count_does_not_scale_with_row_count(
    client, db, monkeypatch
):
    parent = Document(id="tree-parent", name="Tree Parent", doc_type=DocType.folder)
    db.save(parent)
    _seed_documents(db, 0, SMALL_N, parent_id=parent.id)
    counts = _install_query_counter(monkeypatch)

    small_response, small_delta = _counts_for_request(
        counts, lambda: client.get(f"/api/documents/{parent.id}/children")
    )
    assert small_response.status_code == 200

    _seed_documents(db, SMALL_N, LARGE_N, parent_id=parent.id)
    large_response, large_delta = _counts_for_request(
        counts, lambda: client.get(f"/api/documents/{parent.id}/children")
    )
    assert large_response.status_code == 200

    assert small_delta == Counter({"query": 1, "query_in": 1})
    assert large_delta == small_delta
