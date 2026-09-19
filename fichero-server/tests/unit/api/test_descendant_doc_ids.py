"""Tests for the descendant-doc-id BFS that backs the folder KG view (#826).

CONSOLIDATED 2026-09-19 (#4885, kg.tables.folder-recursion-inconsistent-
across-routes): `_descendant_doc_ids` (`api/routes/claim/claims.py`) no
longer runs its own BFS loop — it delegates to
`Database._collect_folder_descendants`, the same batched-SQL walk already
proven correct for `search()`'s folder-scope filter. These tests now run
against a REAL temp-library `Database` (the `db` fixture) instead of a
mocked `db.query`, since mocking `db.query` would no longer exercise the
code path at all post-consolidation.
"""

from __future__ import annotations

from fichero_server.api.routes.claim.claims import _descendant_doc_ids
from fichero_server.models import Document, DocType, FileType


def _folder(db, name: str, parent_id: str | None = None) -> Document:
    doc = Document(name=name, doc_type=DocType.folder, parent_id=parent_id)
    db.save(doc)
    return doc


def _file(db, name: str, parent_id: str | None = None) -> Document:
    doc = Document(name=name, doc_type=DocType.file, parent_id=parent_id)
    db.save(doc, auto_embed=False)
    return doc


class TestDescendantDocIds:
    def test_single_doc_returns_just_itself(self, db):
        alone = _file(db, "alone.txt")
        assert _descendant_doc_ids(db, alone.id) == {alone.id}

    def test_walks_one_level(self, db):
        folder = _folder(db, "folder")
        a = _file(db, "a", parent_id=folder.id)
        b = _file(db, "b", parent_id=folder.id)
        c = _file(db, "c", parent_id=folder.id)
        assert _descendant_doc_ids(db, folder.id) == {folder.id, a.id, b.id, c.id}

    def test_walks_arbitrary_depth_breadth_first(self, db):
        # folder ─ subA ─ leaf1
        #        │       └─ leaf2
        #        └ subB ─ leaf3
        folder = _folder(db, "folder")
        sub_a = _folder(db, "subA", parent_id=folder.id)
        sub_b = _folder(db, "subB", parent_id=folder.id)
        leaf1 = _file(db, "leaf1", parent_id=sub_a.id)
        leaf2 = _file(db, "leaf2", parent_id=sub_a.id)
        leaf3 = _file(db, "leaf3", parent_id=sub_b.id)
        assert _descendant_doc_ids(db, folder.id) == {
            folder.id, sub_a.id, sub_b.id, leaf1.id, leaf2.id, leaf3.id,
        }

    def test_empty_query_result_is_safe(self, db):
        # A document id with no children at all -- just itself.
        alone = _file(db, "x.txt")
        assert _descendant_doc_ids(db, alone.id) == {alone.id}

    def test_a_file_with_page_children_is_walked_the_same_as_a_folder(self, db):
        """Team-lead's explicit ask (#4885): confirm the survivor BFS
        (`Database._collect_folder_descendants`) handles a document id that
        is a FILE with PAGE children, not just a folder -- the walk is
        generic over `parent_id`, indifferent to `doc_type`, so a PDF's
        page children must be found exactly like a folder's files are."""
        pdf = Document(
            name="deed.pdf", doc_type=DocType.file, file_type=FileType.pdf,
        )
        db.save(pdf)
        page1 = Document(name="deed.pdf p.1", doc_type=DocType.page, parent_id=pdf.id, sequence=1)
        db.save(page1)
        page2 = Document(name="deed.pdf p.2", doc_type=DocType.page, parent_id=pdf.id, sequence=2)
        db.save(page2)

        assert _descendant_doc_ids(db, pdf.id) == {pdf.id, page1.id, page2.id}
