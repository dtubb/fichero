"""Coverage for knowledge-graph inclusion rule routes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from fichero_server.api.routes import kg_inclusion as routes
from fichero_server.models.knowledge import InclusionScopeType, KnowledgeGraphInclusion


class FakeDB:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.saved = []

    def query(self, _model, **filters):
        return [row for row in self.rows if all(getattr(row, key) == value for key, value in filters.items())]

    def all(self, _model):
        return list(self.rows)

    def save(self, row):
        self.saved.append(row)


def _row(scope, target, updated_at):
    return KnowledgeGraphInclusion(
        scope_type=scope,
        target_id=target,
        included=True,
        updated_at=updated_at,
    )


def test_upsert_creates_and_saves_new_rule():
    db = FakeDB()
    request = routes.InclusionUpsertRequest(
        scope_type=InclusionScopeType.library,
        target_id="lib-1",
        included=False,
        reason="exclude archive",
        updated_by="reviewer",
    )

    result = asyncio.run(routes.upsert_inclusion(request, db=db))

    assert result.scope_type is InclusionScopeType.library
    assert result.included is False
    assert result.reason == "exclude archive"
    assert db.saved == [result]


def test_upsert_updates_most_recent_matching_rule():
    old = _row(InclusionScopeType.folder, "folder-1", datetime(2024, 1, 1))
    newest = _row(InclusionScopeType.folder, "folder-1", datetime(2024, 2, 1))
    db = FakeDB([old, newest])
    request = routes.InclusionUpsertRequest(
        scope_type=InclusionScopeType.folder,
        target_id="folder-1",
        included=False,
    )

    result = asyncio.run(routes.upsert_inclusion(request, db=db))

    assert result is newest
    assert newest.included is False
    assert old.included is True
    assert db.saved == [newest]


def test_list_filters_each_supported_parameter_and_sorts_newest_first():
    now = datetime.now()
    rows = [
        _row(InclusionScopeType.library, "lib-1", now - timedelta(days=1)),
        _row(InclusionScopeType.folder, "folder-1", now),
        _row(InclusionScopeType.folder, "folder-2", now - timedelta(days=2)),
    ]
    db = FakeDB(rows)

    all_rows = asyncio.run(routes.list_inclusion(scope_type=None, target_id=None, db=db))
    by_scope = asyncio.run(
        routes.list_inclusion(scope_type=InclusionScopeType.folder, target_id=None, db=db)
    )
    by_target = asyncio.run(
        routes.list_inclusion(scope_type=None, target_id="folder-1", db=db)
    )
    exact = asyncio.run(
        routes.list_inclusion(
            scope_type=InclusionScopeType.folder,
            target_id="folder-2",
            db=db,
        )
    )

    assert [row.target_id for row in all_rows.items] == ["folder-1", "lib-1", "folder-2"]
    assert [row.target_id for row in by_scope.items] == ["folder-1", "folder-2"]
    assert [row.target_id for row in by_target.items] == ["folder-1"]
    assert [row.target_id for row in exact.items] == ["folder-2"]
    assert all_rows.count == 3
