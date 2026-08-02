"""#3355 — the sidebar could not tell "no children" from "children not loaded".

`SidebarItem.isExpandable` decides whether to draw a disclosure triangle from
`document.childCount > 0`. The Swift client already reads `child_count` off the
response (`DocumentService` takes it from `additionalProperties`). The backend
never sent it on `/roots` or `/{id}/children`, so every unexpanded node decoded
0 and rendered childless: you could not see that a folder had sub-folders, or a
PDF had pages, until you clicked it and the children happened to load.

An absence rendered as an answer — the same shape as a guardrail passing against
an empty tree.

These tests cover both halves: the counts are right, and the count is NEVER
persisted. The second half matters more than it looks: `Document` is both the
API response shape and the stored row, so a naive field would have created a
real column holding a number that goes stale the moment any child moves, and it
would have done so against the Marshall Diaries.
"""

from __future__ import annotations

import pytest

from fichero_server.db import Database, transient_field_names
from fichero_server.models import Document


@pytest.fixture
def db(tmp_path) -> Database:
    return Database(str(tmp_path / "library.duckdb"))


def _save(db: Database, name: str, *, parent_id: str | None = None) -> Document:
    doc = Document(name=name, parent_id=parent_id)
    db.save(doc)
    return doc


# ---------------------------------------------------------------------------
# child_count must never become a column
# ---------------------------------------------------------------------------


def test_child_count_is_declared_transient():
    assert "child_count" in Document.model_fields
    assert "child_count" in transient_field_names(Document)


def test_child_count_is_not_a_database_column(db):
    _save(db, "Diaries")

    columns = {
        row[0]
        for row in db.execute_fetchall(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'documents'"
        )
    }

    assert "child_count" not in columns, (
        "a stored child_count goes stale the moment a child is added or moved"
    )
    # The guard must not have gone blind: if the table were empty of columns
    # entirely, the assertion above would pass while measuring nothing.
    assert "id" in columns and "parent_id" in columns


def test_saving_a_document_with_a_child_count_does_not_fail_or_store_it(db):
    doc = Document(name="Diaries")
    doc.child_count = 7
    db.save(doc)

    reloaded = db.get(Document, doc.id)
    assert reloaded is not None
    assert reloaded.child_count == 0, "the count must come from the route, not the row"


def test_transient_fields_classvar_is_not_itself_a_field():
    # A ClassVar is invisible to Pydantic, so declaring the convention cannot
    # accidentally create a `TRANSIENT_FIELDS` column.
    assert "TRANSIENT_FIELDS" not in Document.model_fields


def test_child_count_still_serialises_to_clients():
    doc = Document(name="Diaries")
    doc.child_count = 3
    assert doc.model_dump()["child_count"] == 3


# ---------------------------------------------------------------------------
# the counts themselves
# ---------------------------------------------------------------------------


def _with_counts(db: Database, items):
    from fichero_server.api.routes.document.documents import _with_child_counts

    return _with_child_counts(db, items)


def test_a_folder_with_children_reports_them(db):
    parent = _save(db, "1893")
    _save(db, "Jan", parent_id=parent.id)
    _save(db, "Feb", parent_id=parent.id)

    (counted,) = _with_counts(db, [db.get(Document, parent.id)])

    assert counted.child_count == 2


def test_an_empty_folder_reports_zero(db):
    empty = _save(db, "Empty")

    (counted,) = _with_counts(db, [db.get(Document, empty.id)])

    assert counted.child_count == 0


def test_a_folder_of_folders_is_distinguishable_from_an_empty_one(db):
    """The whole point: these two rendered identically before this change."""
    full = _save(db, "Has subfolders")
    _save(db, "Sub", parent_id=full.id)
    empty = _save(db, "Has nothing")

    counted = _with_counts(db, [db.get(Document, full.id), db.get(Document, empty.id)])
    by_name = {doc.name: doc.child_count for doc in counted}

    assert by_name["Has subfolders"] > 0
    assert by_name["Has nothing"] == 0


def test_soft_deleted_children_are_not_counted(db):
    """The count must match what the same endpoint would actually return.

    Counting a trashed child gives a folder a disclosure triangle that expands
    to nothing — a different way of lying about what is there.
    """
    parent = _save(db, "1893")
    kept = _save(db, "Jan", parent_id=parent.id)
    trashed = _save(db, "Feb", parent_id=parent.id)

    db.execute("UPDATE documents SET deleted_at = now() WHERE id = ?", [trashed.id])

    (counted,) = _with_counts(db, [db.get(Document, parent.id)])

    assert counted.child_count == 1, f"only {kept.name} should count"


def test_counts_are_one_query_for_the_whole_page_not_one_per_row(db):
    """An N+1 here is on the sidebar's hot path.

    Counted structurally rather than by timing: the helper issues exactly one
    statement regardless of how many rows it is given.
    """
    parents = [_save(db, f"Folder {index}") for index in range(12)]
    for parent in parents:
        _save(db, "child", parent_id=parent.id)

    calls: list[str] = []
    original = db.execute_fetchall

    def counting(sql, params=None):
        calls.append(sql)
        return original(sql, params)

    db.execute_fetchall = counting  # type: ignore[method-assign]
    try:
        counted = _with_counts(db, [db.get(Document, parent.id) for parent in parents])
    finally:
        db.execute_fetchall = original  # type: ignore[method-assign]

    assert len(calls) == 1, f"expected one grouped query, got {len(calls)}"
    assert all(doc.child_count == 1 for doc in counted)


def test_an_empty_page_issues_no_query_at_all(db):
    calls: list[str] = []
    original = db.execute_fetchall
    db.execute_fetchall = lambda sql, params=None: (  # type: ignore[method-assign]
        calls.append(sql),
        original(sql, params),
    )[1]
    try:
        assert _with_counts(db, []) == []
    finally:
        db.execute_fetchall = original  # type: ignore[method-assign]

    assert calls == []
