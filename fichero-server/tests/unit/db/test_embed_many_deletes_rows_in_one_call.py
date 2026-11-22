"""`embed_many` removes the old vector rows of its whole batch with one Lance delete, not one per page (#6867)."""

from __future__ import annotations

from unittest.mock import patch

from fichero_server.db import Database
from fichero_server.db.embeddings import EMBEDDINGS_TABLE
from fichero_server.models import DocType, Document, FileType


def _pages(n: int) -> list[Document]:
    return [
        Document(
            id=f"p{i}", name=f"P{i}", doc_type=DocType.page, file_type=FileType.image,
            page_content=f"Page number {i} has some words in it.",
        )
        for i in range(n)
    ]


def test_embed_many_deletes_the_batch_in_one_call(tmp_path) -> None:
    db = Database(tmp_path / "d.duckdb")
    pages = _pages(40)
    db.save_many(pages, new=True)
    with patch.object(db, "_embed_texts", side_effect=lambda texts, role="passage": [[1.0, 0.0, 0.0, 0.0]] * len(texts)):
        db.embed_many(pages)  # first write: creates the table
        table = db.lance.open_table(EMBEDDINGS_TABLE)
        calls: list[str] = []
        real_delete = type(table).delete

        def counting_delete(self, where, *a, **k):
            calls.append(where)
            return real_delete(self, where, *a, **k)

        with patch.object(type(table), "delete", counting_delete):
            db.embed_many(pages)  # re-embed: old rows of all 40 pages go

    assert len(calls) == 1
    assert all(f"'p{i}'" in calls[0] for i in range(40))
    ids = db.lance.open_table(EMBEDDINGS_TABLE).to_arrow().column("document_id").to_pylist()
    assert sorted(ids) == sorted(p.id for p in pages)  # one passage a page, no duplicates left by the re-embed
    db.close()
