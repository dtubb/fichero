"""Tests for the descendant-doc-id BFS helper that backs the folder
KG view (#826)."""

from __future__ import annotations

from unittest.mock import MagicMock

from fichero.api.routes.claim.claims import _descendant_doc_ids


def _make_db(tree: dict[str, list[str]]) -> MagicMock:
    """Build a mock Database whose query(Document, parent_id=...) returns
    the children declared in `tree`. Each child is a tiny stand-in object
    with a `.id` attribute."""
    db = MagicMock()

    def _query(_model, parent_id: str = ""):
        children: list = []
        for child_id in tree.get(parent_id, []):
            stub = MagicMock()
            stub.id = child_id
            children.append(stub)
        return children

    db.query.side_effect = _query
    return db


class TestDescendantDocIds:
    def test_single_doc_returns_just_itself(self):
        db = _make_db({})
        assert _descendant_doc_ids(db, "alone") == {"alone"}

    def test_walks_one_level(self):
        db = _make_db({"folder": ["a", "b", "c"]})
        assert _descendant_doc_ids(db, "folder") == {"folder", "a", "b", "c"}

    def test_walks_arbitrary_depth_breadth_first(self):
        # folder ─ subA ─ leaf1
        #        │       └─ leaf2
        #        └ subB ─ leaf3
        db = _make_db({
            "folder": ["subA", "subB"],
            "subA": ["leaf1", "leaf2"],
            "subB": ["leaf3"],
        })
        assert _descendant_doc_ids(db, "folder") == {
            "folder", "subA", "subB", "leaf1", "leaf2", "leaf3",
        }

    def test_handles_cycles_without_infinite_loop(self):
        # Pathological: child claims parent as a child too. Should
        # terminate via the seen-set.
        db = _make_db({
            "folder": ["sub"],
            "sub": ["folder", "leaf"],
        })
        assert _descendant_doc_ids(db, "folder") == {"folder", "sub", "leaf"}

    def test_empty_query_result_is_safe(self):
        db = MagicMock()
        db.query.return_value = None  # query returns None instead of []
        assert _descendant_doc_ids(db, "x") == {"x"}
