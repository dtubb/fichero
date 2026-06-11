from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import BaseModel

import fichero.api.routes.actions_registry  # noqa: F401 - registers acl.set
from fichero import accounts, authz
from fichero.actions.registry import (
    ActionContext,
    ActionRegistration,
    ChangeSpec,
    registry,
)
from fichero.api.change_stream import _change_hub
from fichero.api.main import get_library_database
from fichero.api.routes.changes import stream_library_changes
from fichero.api.routes.entities import _digest_library_database
from fichero.api.routes.library_registry import add_known_library
from fichero.api.routes.schedules import get_library_database as get_schedule_database
from fichero.api.routes.triggers import get_library_database as get_trigger_database
from fichero.db import Database
from fichero.models import AccountUser, Document, DocType
from fichero.workflows.tools._workflow_change_emit import emit_workflow_artifact_changes


class _TargetParams(BaseModel):
    document_id: str | None = None
    document_ids: list[str] = []


@pytest.fixture
def acl_action():
    name = "test.acl_mutation"

    def _execute(_db, params: _TargetParams, _ctx: ActionContext):
        target_ids = list(params.document_ids)
        if params.document_id:
            target_ids.append(params.document_id)
        return (
            {"document_id": params.document_id},
            ChangeSpec(
                domains=["test"],
                target_ids=target_ids,
            ),
        )

    registry.register(
        ActionRegistration(
            name=name,
            params_model=_TargetParams,
            execute=_execute,
            domains=["test"],
        )
    )
    yield name
    registry._actions.pop(name, None)


@pytest.fixture
def users(app_db):
    owner = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    editor = app_db.create_user(
        username="editor",
        display_name="Editor",
        password_hash=accounts.hash_password("password"),
    )
    viewer = app_db.create_user(
        username="viewer",
        display_name="Viewer",
        password_hash=accounts.hash_password("password"),
    )
    stranger = app_db.create_user(
        username="stranger",
        display_name="Stranger",
        password_hash=accounts.hash_password("password"),
    )
    return SimpleNamespace(
        owner=owner,
        editor=editor,
        viewer=viewer,
        stranger=stranger,
    )


def _library_path(db) -> str:
    return str(db.path.parent)


def _grant(app_db, user: AccountUser, library_path: str, role: str) -> None:
    app_db.set_library_role(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        role=role,
    )


def _request(user: AccountUser | None, **target):
    return SimpleNamespace(
        state=SimpleNamespace(user=user),
        path_params=target,
        query_params={},
    )


def test_editor_can_invoke_mutating_action_viewer_cannot(
    db, app_db, users, acl_action, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)
    _grant(app_db, users.editor, library_path, "editor")
    _grant(app_db, users.viewer, library_path, "viewer")

    editor_ctx = ActionContext(actor="editor", library_path=library_path)
    result = registry.invoke(db, acl_action, {}, editor_ctx)
    assert result.ok is True

    viewer_ctx = ActionContext(actor="viewer", library_path=library_path)
    with pytest.raises(authz.AuthorizationError):
        registry.invoke(db, acl_action, {}, viewer_ctx)


@pytest.mark.anyio
async def test_folder_deny_blocks_read_dependency_and_registry_write(
    db, app_db, users, acl_action, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)
    _grant(app_db, users.editor, library_path, "editor")

    folder = Document(name="Denied Folder", doc_type=DocType.folder)
    db.save(folder)
    child = Document(name="Child", parent_id=folder.id)
    db.save(child)
    app_db.set_library_acl_override(
        user_id=users.editor.id,
        library_path=authz.normalize_library_path(library_path),
        target_id=folder.id,
        effect="deny",
    )

    with pytest.raises(HTTPException) as read_exc:
        await get_library_database(
            _request(users.editor, doc_id=child.id),
            x_fichero_library_path=library_path,
        )
    assert read_exc.value.status_code == 403

    ctx = ActionContext(actor="editor", library_path=library_path)
    with pytest.raises(authz.AuthorizationError):
        registry.invoke(db, acl_action, {"document_id": child.id}, ctx)

    allowed = Document(name="Allowed")
    db.save(allowed)
    with pytest.raises(authz.AuthorizationError):
        registry.invoke(
            db,
            acl_action,
            {"document_ids": [allowed.id, child.id]},
            ctx,
        )


@pytest.mark.anyio
async def test_no_role_fails_closed_for_read_and_write(
    db, users, acl_action, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)

    with pytest.raises(HTTPException) as read_exc:
        await get_library_database(
            _request(users.stranger),
            x_fichero_library_path=library_path,
        )
    assert read_exc.value.status_code == 403

    with pytest.raises(authz.AuthorizationError):
        registry.invoke(
            db,
            acl_action,
            {},
            ActionContext(actor="stranger", library_path=library_path),
        )


@pytest.mark.anyio
async def test_bootstrap_secret_without_user_fails_closed_for_read_and_write(
    db, acl_action, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)

    with pytest.raises(HTTPException) as read_exc:
        await get_library_database(
            _request(None),
            x_fichero_library_path=library_path,
        )
    assert read_exc.value.status_code == 403

    with pytest.raises(authz.AuthorizationError):
        registry.invoke(
            db,
            acl_action,
            {},
            ActionContext(actor="system", library_path=library_path),
        )


@pytest.mark.anyio
async def test_schedule_and_trigger_dependencies_use_read_acl(
    db, users, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)

    with pytest.raises(HTTPException) as schedule_exc:
        await get_schedule_database(
            _request(users.stranger),
            x_fichero_library_path=library_path,
        )
    assert schedule_exc.value.status_code == 403

    with pytest.raises(HTTPException) as trigger_exc:
        await get_trigger_database(
            _request(users.stranger),
            x_fichero_library_path=library_path,
        )
    assert trigger_exc.value.status_code == 403

    with pytest.raises(HTTPException) as entity_exc:
        await _digest_library_database(
            _request(users.stranger),
            x_fichero_library_path=library_path,
        )
    assert entity_exc.value.status_code == 403

    with pytest.raises(HTTPException) as stream_exc:
        await stream_library_changes(
            _request(users.stranger),
            x_fichero_library_path=library_path,
        )
    assert stream_exc.value.status_code == 403


def test_owner_can_grant_role_and_it_takes_effect(
    db, app_db, users, acl_action, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)
    _grant(app_db, users.owner, library_path, "owner")
    _grant(app_db, users.viewer, library_path, "viewer")

    with pytest.raises(authz.AuthorizationError):
        registry.invoke(
            db,
            acl_action,
            {},
            ActionContext(actor="viewer", library_path=library_path),
        )

    registry.invoke(
        db,
        "acl.set",
        {"user": "viewer", "role": "editor"},
        ActionContext(actor="owner", library_path=library_path),
    )

    result = registry.invoke(
        db,
        acl_action,
        {},
        ActionContext(actor="viewer", library_path=library_path),
    )
    assert result.ok is True


@pytest.mark.anyio
async def test_multiuser_off_leaves_registry_and_read_dependency_unchanged(
    db, users, acl_action, monkeypatch
):
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    library_path = _library_path(db)

    assert (
        await get_library_database(
            _request(users.stranger),
            x_fichero_library_path=library_path,
        )
    ) is db
    assert (
        await get_schedule_database(
            _request(users.stranger),
            x_fichero_library_path=library_path,
        )
    ) is db
    assert (
        await get_trigger_database(
            _request(users.stranger),
            x_fichero_library_path=library_path,
        )
    ) is db

    result = registry.invoke(
        db,
        acl_action,
        {},
        ActionContext(actor="stranger", library_path=library_path),
    )
    assert result.ok is True


def test_registry_add_does_not_auto_adopt_library_under_multiuser(
    app_db, users, monkeypatch, tmp_path
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = tmp_path / "Reachable.fichero"
    library_path.mkdir()
    global_package = tmp_path / "global.fichero"
    global_package.mkdir()
    global_db = Database(path=global_package / "fichero.duckdb")

    try:
        added = add_known_library(
            _request(users.owner),
            path=str(library_path),
            db=global_db,
        )
    finally:
        global_db.conn.close()

    normalized = authz.normalize_library_path(library_path)
    assert added.path == normalized
    assert app_db.get_library_role(users.owner.id, normalized) is None
    assert authz.can_read(users.owner, library_path) is False


def test_workflow_emission_still_functions_under_multiuser(monkeypatch, tmp_path):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = str(tmp_path / "Workflow.fichero")
    queue = _change_hub.subscribe(library_path)
    try:
        emit_workflow_artifact_changes(
            library_path,
            artifact_ids=["artifact-1"],
            document_ids=["doc-1"],
        )
        event = queue.get_nowait()
    finally:
        _change_hub.unsubscribe(library_path, queue)

    assert event.type == "artifact.created"
    assert event.actor == "workflow"
    assert event.artifact_ids == ["artifact-1"]


def test_library_creator_is_bootstrapped_as_owner(app_db, users, monkeypatch, tmp_path):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = tmp_path / "Created.fichero"
    library_path.mkdir()

    assert authz.ensure_owner_role(users.owner, library_path) is True
    role = app_db.get_library_role(
        users.owner.id,
        authz.normalize_library_path(library_path),
    )
    assert role is not None
    assert role.role == "owner"
    assert authz.ensure_owner_role(users.viewer, library_path) is False


def test_acl_enforcement_stays_at_two_choke_points():
    root = "fichero-engine/src/fichero"
    with open(f"{root}/actions/registry.py", encoding="utf-8") as handle:
        registry_source = handle.read()
    with open(f"{root}/api/main.py", encoding="utf-8") as handle:
        api_source = handle.read()

    assert "class ActionRegistry" in registry_source
    assert "def invoke(" in registry_source
    assert "authz.assert_can_write(" in registry_source
    assert api_source.count("authz.assert_can_read(") == 1
