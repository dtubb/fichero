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
from fichero.api.main import get_library_database
from fichero.models import AccountUser, Document, DocType


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

    result = registry.invoke(
        db,
        acl_action,
        {},
        ActionContext(actor="stranger", library_path=library_path),
    )
    assert result.ok is True


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
