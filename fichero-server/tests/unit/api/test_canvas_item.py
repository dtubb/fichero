"""Tests for standalone canvas items (#2294 Slice 1).

A ``CanvasItem`` is the CONTENT for non-document placeables — notes, quotes,
work-notes, links/connectors, free text. Its POSITION lives separately in
``canvas_layout`` (#2293). Covered here:
  * CRUD endpoints under ``/folders/{folder_id}/canvas-items`` (envelope on list)
  * the ``canvas.item.create|update|delete`` registry actions (audited + emit)
  * adversarial paths: each kind round-trips, link endpoints, cross-folder
    isolation, 404s, idempotent table creation, empty list.
"""

import asyncio
from types import SimpleNamespace
import pytest

# Importing the route module registers the ``canvas.item.*`` actions.
import fichero_server.api.routes.interpretation.canvas  # noqa: F401
from fichero_server.security import accounts
from fichero_server.security import authz
from fichero_server.api.routes.actions_registry import undo_action
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit
from fichero_server.models.canvas import CanvasItem, CanvasItemKind

BASE = "/api/canvas/folders"
KINDS = ["note", "quote", "work_note", "link", "text"]


def _ctx(db, app_db) -> ActionContext:
    library_path = str(db.path.parent)
    user = app_db.create_user(
        username="canvas-editor",
        display_name="Canvas Editor",
        password_hash=accounts.hash_password("password"),
    )
    app_db.set_library_role(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        role="editor",
    )
    return ActionContext(actor=user.username, library_path=library_path)


def _undo(db, audit_id: str, library_path: str):
    return asyncio.run(
        undo_action(
            audit_id,
            request=SimpleNamespace(state=SimpleNamespace(user=None), base_url="https://engine.local/"),
            db=db,
            x_fichero_library_path=library_path,
            x_fichero_origin_window=None,
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints: CRUD
# ─────────────────────────────────────────────────────────────────────────────


def test_empty_list_is_envelope_not_bare_array(client):
    resp = client.get(f"{BASE}/folder-empty/canvas-items")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # {items, count} envelope (contract walker #1147), not a bare [].
    assert body == {"items": [], "count": 0}


@pytest.mark.parametrize("kind", KINDS)
def test_each_kind_round_trips(client, kind):
    folder = f"folder-{kind}"
    resp = client.post(
        f"{BASE}/{folder}/canvas-items",
        json={"kind": kind, "text": f"hello {kind}"},
    )
    assert resp.status_code == 200, resp.text
    created = resp.json()
    assert created["kind"] == kind
    assert created["text"] == f"hello {kind}"
    assert created["folder_id"] == folder
    assert created["id"]
    assert created["created_at"] and created["updated_at"]

    loaded = client.get(f"{BASE}/{folder}/canvas-items").json()
    assert loaded["count"] == 1
    assert loaded["items"][0]["id"] == created["id"]


def test_unknown_kind_is_422(client):
    resp = client.post(
        f"{BASE}/folder-bad/canvas-items",
        json={"kind": "doodle", "text": "x"},
    )
    assert resp.status_code == 422, resp.text


def test_link_carries_source_and_target(client):
    folder = "folder-link"
    resp = client.post(
        f"{BASE}/{folder}/canvas-items",
        json={
            "kind": "link",
            "text": "connects",
            "source_item_id": "doc-1",
            "target_item_id": "entity-7",
            "payload": {"style": "arrow"},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source_item_id"] == "doc-1"
    assert body["target_item_id"] == "entity-7"
    assert body["payload"] == {"style": "arrow"}

    loaded = client.get(f"{BASE}/{folder}/canvas-items").json()["items"][0]
    assert loaded["source_item_id"] == "doc-1"
    assert loaded["target_item_id"] == "entity-7"
    assert loaded["payload"] == {"style": "arrow"}


def test_default_kind_is_note(client):
    resp = client.post(f"{BASE}/folder-def/canvas-items", json={"text": "untyped"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["kind"] == "note"


def test_list_filters_by_kind(client):
    folder = "folder-mixed"
    client.post(f"{BASE}/{folder}/canvas-items", json={"kind": "note", "text": "n"})
    client.post(f"{BASE}/{folder}/canvas-items", json={"kind": "quote", "text": "q"})
    client.post(f"{BASE}/{folder}/canvas-items", json={"kind": "quote", "text": "q2"})

    all_items = client.get(f"{BASE}/{folder}/canvas-items").json()
    assert all_items["count"] == 3

    quotes = client.get(f"{BASE}/{folder}/canvas-items?kind=quote").json()
    assert quotes["count"] == 2
    assert all(i["kind"] == "quote" for i in quotes["items"])


def test_patch_edits_text_and_payload(client):
    folder = "folder-edit"
    item_id = client.post(
        f"{BASE}/{folder}/canvas-items",
        json={"kind": "note", "text": "before", "payload": {"a": 1}},
    ).json()["id"]

    resp = client.patch(
        f"{BASE}/{folder}/canvas-items/{item_id}",
        json={"text": "after", "payload": {"b": 2}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["text"] == "after"
    assert body["payload"] == {"b": 2}
    # kind untouched by a text-only patch.
    assert body["kind"] == "note"


def test_patch_unset_fields_are_preserved(client):
    folder = "folder-partial"
    created = client.post(
        f"{BASE}/{folder}/canvas-items",
        json={"kind": "quote", "text": "keep me", "source_item_id": "s1"},
    ).json()
    item_id = created["id"]

    # Patch only the kind; text + source_item_id must survive.
    resp = client.patch(
        f"{BASE}/{folder}/canvas-items/{item_id}",
        json={"kind": "work_note"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "work_note"
    assert body["text"] == "keep me"
    assert body["source_item_id"] == "s1"


def test_patch_missing_item_is_404(client):
    resp = client.patch(
        f"{BASE}/folder-x/canvas-items/does-not-exist",
        json={"text": "nope"},
    )
    assert resp.status_code == 404, resp.text


def test_patch_cross_folder_is_404(client):
    item_id = client.post(
        f"{BASE}/owner/canvas-items", json={"kind": "note", "text": "mine"}
    ).json()["id"]
    # Same id, wrong folder in the path — must not edit.
    resp = client.patch(
        f"{BASE}/intruder/canvas-items/{item_id}", json={"text": "stolen"}
    )
    assert resp.status_code == 404, resp.text
    # Original is unchanged.
    still = client.get(f"{BASE}/owner/canvas-items").json()["items"][0]
    assert still["text"] == "mine"


def test_delete_removes_item(client):
    folder = "folder-del"
    item_id = client.post(
        f"{BASE}/{folder}/canvas-items", json={"kind": "text", "text": "bye"}
    ).json()["id"]

    resp = client.delete(f"{BASE}/{folder}/canvas-items/{item_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "deleted"
    assert client.get(f"{BASE}/{folder}/canvas-items").json()["count"] == 0


def test_delete_missing_item_is_404(client):
    resp = client.delete(f"{BASE}/folder-x/canvas-items/ghost")
    assert resp.status_code == 404, resp.text


def test_delete_cross_folder_is_404(client):
    item_id = client.post(
        f"{BASE}/keep/canvas-items", json={"kind": "note", "text": "safe"}
    ).json()["id"]
    resp = client.delete(f"{BASE}/other/canvas-items/{item_id}")
    assert resp.status_code == 404, resp.text
    assert client.get(f"{BASE}/keep/canvas-items").json()["count"] == 1


def test_items_are_folder_scoped(client):
    client.post(f"{BASE}/f1/canvas-items", json={"kind": "note", "text": "one"})
    client.post(f"{BASE}/f2/canvas-items", json={"kind": "note", "text": "two"})
    f1 = client.get(f"{BASE}/f1/canvas-items").json()
    f2 = client.get(f"{BASE}/f2/canvas-items").json()
    assert f1["count"] == 1 and f2["count"] == 1
    assert f1["items"][0]["text"] == "one"
    assert f2["items"][0]["text"] == "two"


def test_canvas_item_routes_write_action_audit(client, db):
    folder = "folder-route-audit"
    created = client.post(
        f"{BASE}/{folder}/canvas-items",
        json={"kind": "note", "text": "created"},
    )
    assert created.status_code == 200, created.text
    item_id = created.json()["id"]
    assert db.all(ActionAudit)[-1].action_name == "canvas.item.create"

    updated = client.patch(
        f"{BASE}/{folder}/canvas-items/{item_id}",
        json={"text": "updated"},
    )
    assert updated.status_code == 200, updated.text
    assert db.all(ActionAudit)[-1].action_name == "canvas.item.update"

    deleted = client.delete(f"{BASE}/{folder}/canvas-items/{item_id}")
    assert deleted.status_code == 200, deleted.text
    assert db.all(ActionAudit)[-1].action_name == "canvas.item.delete"


# ─────────────────────────────────────────────────────────────────────────────
# Idempotent table creation — querying a fresh DB must not raise.
# ─────────────────────────────────────────────────────────────────────────────


def test_table_is_created_idempotently(db):
    # No canvasitems table yet; query must auto-create and return [].
    assert db.query(CanvasItem, folder_id="never-written") == []
    # Saving then querying again works (table already exists — no error).
    db.save(CanvasItem(folder_id="f", kind=CanvasItemKind.note, text="t"))
    assert len(db.query(CanvasItem, folder_id="f")) == 1
    assert db.query(CanvasItem, folder_id="never-written") == []


# ─────────────────────────────────────────────────────────────────────────────
# Action layer: canvas.item.create | update | delete (agent / chat path, #1848)
# ─────────────────────────────────────────────────────────────────────────────


def test_canvas_item_actions_are_registered():
    names = registry.names()
    assert "canvas.item.create" in names
    assert "canvas.item.update" in names
    assert "canvas.item.delete" in names


def test_create_action_persists_and_audits(db, app_db):
    ctx = _ctx(db, app_db)
    result = registry.invoke(
        db,
        "canvas.item.create",
        {"folder_id": "f-act", "kind": "quote", "text": "from the agent"},
        ctx,
    )
    assert result.ok
    assert result.audit_id
    assert "canvas" in result.changed_domains

    rows = db.query(CanvasItem, folder_id="f-act")
    assert len(rows) == 1
    assert rows[0].kind == CanvasItemKind.quote
    assert rows[0].text == "from the agent"


def test_create_action_undo_deletes_item_and_writes_inverse_audit(db, app_db):
    ctx = _ctx(db, app_db)
    created = registry.invoke(
        db,
        "canvas.item.create",
        {"folder_id": "f-undo", "kind": "note", "text": "undo me"},
        ctx,
    )

    item_id = created.result["id"]
    assert db.get(CanvasItem, item_id) is not None

    undone = _undo(db, created.audit_id, ctx.library_path)

    assert db.get(CanvasItem, item_id) is None
    assert db.get(ActionAudit, created.audit_id).undone is True
    inverse_audit = db.get(ActionAudit, undone.audit_id)
    assert inverse_audit is not None
    assert inverse_audit.action_name == "canvas.item.delete"
    assert inverse_audit.inverse_of == created.audit_id


def test_update_action_undo_restores_prior_snapshot(db, app_db):
    ctx = _ctx(db, app_db)
    created = registry.invoke(
        db,
        "canvas.item.create",
        {"folder_id": "f-update-undo", "kind": "note", "text": "v1"},
        ctx,
    )
    item_id = created.result["id"]

    updated = registry.invoke(
        db,
        "canvas.item.update",
        {"folder_id": "f-update-undo", "item_id": item_id, "text": "v2"},
        ctx,
    )

    undone = _undo(db, updated.audit_id, ctx.library_path)

    restored = db.get(CanvasItem, item_id)
    assert restored is not None
    assert restored.text == "v1"
    assert db.get(ActionAudit, updated.audit_id).undone is True
    inverse_audit = db.get(ActionAudit, undone.audit_id)
    assert inverse_audit is not None
    assert inverse_audit.action_name == "canvas.item.restore"
    assert inverse_audit.inverse_of == updated.audit_id


def test_delete_action_undo_restores_deleted_item(db, app_db):
    ctx = _ctx(db, app_db)
    created = registry.invoke(
        db,
        "canvas.item.create",
        {"folder_id": "f-delete-undo", "kind": "quote", "text": "restore me"},
        ctx,
    )
    item_id = created.result["id"]

    deleted = registry.invoke(
        db,
        "canvas.item.delete",
        {"folder_id": "f-delete-undo", "item_id": item_id},
        ctx,
    )
    assert deleted.ok
    assert db.get(CanvasItem, item_id) is None

    undone = _undo(db, deleted.audit_id, ctx.library_path)

    restored = db.get(CanvasItem, item_id)
    assert restored is not None
    assert restored.text == "restore me"
    assert db.get(ActionAudit, deleted.audit_id).undone is True
    inverse_audit = db.get(ActionAudit, undone.audit_id)
    assert inverse_audit is not None
    assert inverse_audit.action_name == "canvas.item.restore"
    assert inverse_audit.inverse_of == deleted.audit_id


def test_create_link_action_round_trips(db, app_db):
    ctx = _ctx(db, app_db)
    result = registry.invoke(
        db,
        "canvas.item.create",
        {
            "folder_id": "f-link",
            "kind": "link",
            "source_item_id": "a",
            "target_item_id": "b",
        },
        ctx,
    )
    assert result.ok
    row = db.query(CanvasItem, folder_id="f-link")[0]
    assert row.kind == CanvasItemKind.link
    assert row.source_item_id == "a" and row.target_item_id == "b"


def test_update_action_changes_text_and_records_before(db, app_db):
    ctx = _ctx(db, app_db)
    created = registry.invoke(
        db,
        "canvas.item.create",
        {"folder_id": "f-u", "kind": "note", "text": "v1"},
        ctx,
    )
    item_id = created.result["id"]

    updated = registry.invoke(
        db,
        "canvas.item.update",
        {"folder_id": "f-u", "item_id": item_id, "text": "v2"},
        ctx,
    )
    assert updated.ok
    assert updated.result["text"] == "v2"
    rows = db.query(CanvasItem, folder_id="f-u")
    assert len(rows) == 1 and rows[0].text == "v2"


def test_update_action_missing_item_raises(db, app_db):
    with pytest.raises(KeyError):
        registry.invoke(
            db,
            "canvas.item.update",
            {"folder_id": "f-u", "item_id": "nope", "text": "x"},
            _ctx(db, app_db),
        )


def test_delete_action_removes_and_records_before(db, app_db):
    ctx = _ctx(db, app_db)
    created = registry.invoke(
        db,
        "canvas.item.create",
        {"folder_id": "f-d", "kind": "text", "text": "doomed"},
        ctx,
    )
    item_id = created.result["id"]

    deleted = registry.invoke(
        db,
        "canvas.item.delete",
        {"folder_id": "f-d", "item_id": item_id},
        ctx,
    )
    assert deleted.ok
    assert deleted.result["text"] == "doomed"  # before-state returned
    assert db.query(CanvasItem, folder_id="f-d") == []


def test_delete_action_missing_item_raises(db, app_db):
    with pytest.raises(KeyError):
        registry.invoke(
            db,
            "canvas.item.delete",
            {"folder_id": "f-d", "item_id": "ghost"},
            _ctx(db, app_db),
        )
