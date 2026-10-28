"""A Database's deferred embeds are the deferring caller's own (Fable review 2026-10-27, #6236).

WHY: the deferral was one list on the Database, shared by every thread. While a names page deferred its embeds,
another thread's save on the same Database was deferred into that page's list too, and lost if the page rolled back.
"""

from __future__ import annotations

import threading

from fichero_server.db import Database
from fichero_server.models.knowledge import EntityType, KnowledgeEntity


def test_another_threads_save_during_a_deferred_page_is_embedded_not_deferred(tmp_path, monkeypatch):
    db = Database(tmp_path / "test.duckdb")
    embedded: list[str] = []
    monkeypatch.setattr(Database, "embed_entities", lambda self, entities, **k: embedded.extend(
        e.canonical_name for e in entities) or len(entities))
    try:
        with db.defer_embeddings():
            db.save(KnowledgeEntity(canonical_name="On the page", entity_type=EntityType.person))
            other = threading.Thread(target=lambda: db.save(
                KnowledgeEntity(canonical_name="Another thread's", entity_type=EntityType.person)))
            other.start()
            other.join()
            assert "Another thread's" in embedded, "another thread's save was deferred into this page"
            assert "On the page" not in embedded
    finally:
        db.close()
