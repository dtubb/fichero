"""Coverage for knowledge-graph inclusion rule routes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes import kg_inclusion as routes
from fichero_server.models import ActionAudit
from fichero_server.models.knowledge import InclusionScopeType, KnowledgeGraphInclusion


def _ctx(actor: str = "reviewer") -> ActionContext:
    return ActionContext(actor=actor, library_path="/lib/test.fichero")


def _row(db, scope, target, updated_at):
    row = KnowledgeGraphInclusion(
        scope_type=scope,
        target_id=target,
        included=True,
        updated_at=updated_at,
    )
    db.save(row)
    return row


def test_upsert_creates_and_saves_new_rule(db):
    # #4831: the route now goes through `registry.invoke`, which needs a real
    # Database (transaction + ActionAudit write) -- a bare stub can no
    # longer stand in for it.
    request = routes.InclusionUpsertRequest(
        scope_type=InclusionScopeType.library,
        target_id="lib-1",
        included=False,
        reason="exclude archive",
        updated_by="reviewer",
    )

    result = asyncio.run(routes.upsert_inclusion(request, db=db, actor="reviewer"))

    assert result.scope_type is InclusionScopeType.library
    assert result.included is False
    assert result.reason == "exclude archive"
    persisted = db.get(KnowledgeGraphInclusion, result.id)
    assert persisted is not None
    assert persisted.included is False


def test_upsert_updates_most_recent_matching_rule(db):
    old = _row(db, InclusionScopeType.folder, "folder-1", datetime(2024, 1, 1))
    newest = _row(db, InclusionScopeType.folder, "folder-1", datetime(2024, 2, 1))
    request = routes.InclusionUpsertRequest(
        scope_type=InclusionScopeType.folder,
        target_id="folder-1",
        included=False,
    )

    result = asyncio.run(routes.upsert_inclusion(request, db=db, actor="reviewer"))

    assert result.id == newest.id
    assert db.get(KnowledgeGraphInclusion, newest.id).included is False
    assert db.get(KnowledgeGraphInclusion, old.id).included is True


def test_forged_updated_by_is_ignored(db):
    """#4843: a client-supplied `updated_by` must never reach the stored
    row -- the REAL actor (from `ctx.actor`, threaded through as `actor`
    here) always wins."""
    request = routes.InclusionUpsertRequest(
        scope_type=InclusionScopeType.library,
        target_id="lib-2",
        included=True,
        updated_by="totally-forged-name",
    )

    result = asyncio.run(routes.upsert_inclusion(request, db=db, actor="real-actor"))

    assert result.updated_by == "real-actor"
    assert db.get(KnowledgeGraphInclusion, result.id).updated_by == "real-actor"


def test_upsert_action_writes_audit_with_real_actor_and_undoes(db):
    """Drives `inclusion.upsert` through the registry directly (the same
    path chat tools / App Intents / `POST /api/actions/invoke` use)."""
    result = registry.invoke(
        db,
        "inclusion.upsert",
        {
            "scope_type": "library",
            "target_id": "lib-3",
            "included": False,
            "reason": "first",
            "updated_by": "forged",
        },
        _ctx(actor="alice"),
    )
    record_id = result.result["id"]
    assert db.get(KnowledgeGraphInclusion, record_id).updated_by == "alice"

    audit = db.get(ActionAudit, result.audit_id)
    assert audit.action_name == "inclusion.upsert"
    assert audit.actor == "alice"
    assert audit.before is None  # fresh insert, nothing to restore
    assert audit.after["included"] is False

    # Update it again — now `before` is populated and undo can replay it.
    result2 = registry.invoke(
        db,
        "inclusion.upsert",
        {
            "scope_type": "library",
            "target_id": "lib-3",
            "included": True,
            "reason": "second",
        },
        _ctx(actor="bob"),
    )
    assert db.get(KnowledgeGraphInclusion, record_id).included is True
    assert db.get(KnowledgeGraphInclusion, record_id).updated_by == "bob"

    audit2 = db.get(ActionAudit, result2.audit_id)
    reg = registry.get("inclusion.upsert")
    inverse = reg.invert(audit2.before, audit2.after, _ctx())
    assert inverse is not None
    inv_name, inv_params = inverse
    registry.invoke(db, inv_name, inv_params, _ctx(actor="carol"))

    restored = db.get(KnowledgeGraphInclusion, record_id)
    assert restored.included is False
    assert restored.reason == "first"
    assert restored.updated_by == "carol"


class FakeDB:
    """`list_inclusion` (read-only, untouched by #4831) stays fine with a
    bare stub -- only `upsert_inclusion` needed a real `Database` above."""

    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def query(self, _model, **filters):
        return [row for row in self.rows if all(getattr(row, key) == value for key, value in filters.items())]

    def all(self, _model):
        return list(self.rows)


def _fake_row(scope, target, updated_at):
    return KnowledgeGraphInclusion(
        scope_type=scope,
        target_id=target,
        included=True,
        updated_at=updated_at,
    )


def test_list_filters_each_supported_parameter_and_sorts_newest_first():
    now = datetime.now()
    rows = [
        _fake_row(InclusionScopeType.library, "lib-1", now - timedelta(days=1)),
        _fake_row(InclusionScopeType.folder, "folder-1", now),
        _fake_row(InclusionScopeType.folder, "folder-2", now - timedelta(days=2)),
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
