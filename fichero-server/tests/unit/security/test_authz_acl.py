from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

import fichero_server.api.routes.actions_registry  # noqa: F401 - registers acl.set
from fichero_server.security import accounts
from fichero_server.security import authz
from fichero_server.actions.registry import (
    ActionContext,
    ActionRegistration,
    ChangeSpec,
    registry,
)
from fichero_server.api.change_stream import _change_hub
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.api.routes.auth.accounts import (
    _require_authenticated_or_bootstrap,
    _require_owner_or_bootstrap,
)
from fichero_server.api.routes.library_entity_types import (
    _get_db_manager,
    _get_library_db,
    add_library_entity_type,
    list_library_entity_types,
)
from fichero_server.api.routes.changes import stream_library_changes
from fichero_server.api.routes.entities import _digest_library_database
from fichero_server.api.routes.library_registry import add_known_library
from fichero_server.api.routes.schedules import get_library_database as get_schedule_database
from fichero_server.api.routes.triggers import get_library_database as get_trigger_database
from fichero_server.db import Database
from fichero_server.models import AccountUser, ActionAudit, Document, DocType
from fichero_server.workflows.tools._workflow_change_emit import emit_workflow_artifact_changes


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


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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
async def test_write_dependency_denies_viewer_and_allows_editor(
    db, app_db, users, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)
    _grant(app_db, users.viewer, library_path, "viewer")
    _grant(app_db, users.editor, library_path, "editor")

    with pytest.raises(HTTPException) as viewer_exc:
        await get_library_database_for_write(
            _request(users.viewer),
            x_fichero_library_path=library_path,
        )
    assert viewer_exc.value.status_code == 403

    assert (
        await get_library_database_for_write(
            _request(users.editor),
            x_fichero_library_path=library_path,
        )
    ) is db


def test_viewer_can_search_but_cannot_save_search_route(
    test_package, app_db, users, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    library_path = str(test_package)
    _grant(app_db, users.viewer, library_path, "viewer")

    import fichero_server.api.main as api_main

    api_main = importlib.reload(api_main)
    try:
        with TestClient(
            api_main.app,
            headers={"X-Fichero-Library-Path": library_path},
        ) as client:
            login = client.post(
                "/api/auth/login",
                json={"username": "viewer", "password": "password"},
            )
            assert login.status_code == 200
            auth_headers = _bearer(login.json()["session_token"])

            read_response = client.post(
                "/api/search",
                headers=auth_headers,
                json={"query": "", "limit": 1},
            )
            assert read_response.status_code != 403
            assert read_response.status_code == 200

            write_response = client.post(
                "/api/search/saved",
                headers=auth_headers,
                json={"query": "viewer should not save this"},
            )
            assert write_response.status_code == 403
            assert write_response.json() == {
                "detail": "write access denied",
                "code": "library_access_denied",
                "library_path": authz.normalize_library_path(library_path) or library_path,
                "auth_kind": "session",
                "username": "viewer",
                "required": "write",
            }
    finally:
        api_main.app.dependency_overrides.clear()
        monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
        importlib.reload(api_main)


def test_paired_viewer_gets_structured_library_denial_on_write_route(
    test_package, app_db, users, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    library_path = str(test_package)
    _grant(app_db, users.viewer, library_path, "viewer")
    raw_device_token = accounts.new_session_token()
    app_db.create_device(
        name="Viewer iPad",
        user_id=users.viewer.id,
        token_hash=accounts.hash_token(raw_device_token),
    )

    import fichero_server.api.main as api_main

    api_main = importlib.reload(api_main)
    try:
        with TestClient(
            api_main.app,
            headers={"X-Fichero-Library-Path": library_path},
        ) as client:
            write_response = client.post(
                "/api/search/saved",
                headers=_bearer(raw_device_token),
                json={"query": "paired viewer should not save this"},
            )
            assert write_response.status_code == 403
            assert write_response.json() == {
                "detail": "write access denied",
                "code": "library_access_denied",
                "library_path": authz.normalize_library_path(library_path) or library_path,
                "auth_kind": "device",
                "username": "viewer",
                "required": "write",
            }
    finally:
        api_main.app.dependency_overrides.clear()
        monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
        importlib.reload(api_main)


def test_activity_stream_denies_user_without_library_role(
    test_package, app_db, users, monkeypatch, tmp_path
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    allowed_library = str(test_package)
    denied_package = tmp_path / "denied.fichero"
    denied_package.mkdir()
    denied_db = Database(path=denied_package / "fichero.duckdb")
    denied_db.conn.close()
    denied_library = str(denied_package)
    _grant(app_db, users.viewer, allowed_library, "viewer")

    import fichero_server.api.main as api_main

    api_main = importlib.reload(api_main)
    try:
        with TestClient(
            api_main.app,
            headers={"X-Fichero-Library-Path": allowed_library},
        ) as client:
            login = client.post(
                "/api/auth/login",
                json={"username": "viewer", "password": "password"},
            )
            assert login.status_code == 200
            auth_headers = _bearer(login.json()["session_token"])

            denied = client.get(
                "/api/activity/stream",
                headers={
                    **auth_headers,
                    "X-Fichero-Library-Path": denied_library,
                },
            )
            assert denied.status_code == 403
            assert denied.json() == {
                "detail": "read access denied",
                "code": "library_access_denied",
                "library_path": authz.normalize_library_path(denied_library) or denied_library,
                "auth_kind": "session",
                "username": "viewer",
                "required": "read",
            }
    finally:
        api_main.app.dependency_overrides.clear()
        monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
        importlib.reload(api_main)


@pytest.mark.anyio
async def test_multiuser_off_leaves_write_dependency_unchanged(
    db, users, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    library_path = _library_path(db)

    assert (
        await get_library_database_for_write(
            _request(users.stranger),
            x_fichero_library_path=library_path,
        )
    ) is db


@pytest.mark.anyio
async def test_generic_id_extraction_enforces_subtree_denies(
    db, app_db, users, acl_action, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)
    _grant(app_db, users.editor, library_path, "editor")

    note = Document(name="Denied note")
    db.save(note)
    app_db.set_library_acl_override(
        user_id=users.editor.id,
        library_path=authz.normalize_library_path(library_path),
        target_id=note.id,
        effect="deny",
    )

    assert authz.target_id_from_request(_request(users.editor, note_id=note.id)) == note.id
    with pytest.raises(HTTPException) as read_exc:
        await get_library_database(
            _request(users.editor, note_id=note.id),
            x_fichero_library_path=library_path,
        )
    assert read_exc.value.status_code == 403

    class Params(BaseModel):
        note_id: str

    assert authz.target_ids_from_params(Params(note_id=note.id)) == [note.id]
    with pytest.raises(authz.AuthorizationError):
        registry.invoke(
            db,
            acl_action,
            {"document_id": note.id},
            ActionContext(actor="editor", library_path=library_path),
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


def test_bootstrap_registry_write_bypasses_acl_but_keeps_system_actor(
    db, acl_action, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)

    result = registry.invoke(
        db,
        acl_action,
        {},
        ActionContext(actor="system", library_path=library_path, is_bootstrap=True),
    )

    audit = db.get(ActionAudit, result.audit_id)
    assert result.ok is True
    assert audit is not None
    assert audit.actor == "system"


def test_library_entity_types_validate_path_and_acl(db, app_db, users, monkeypatch, tmp_path):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)
    _grant(app_db, users.viewer, library_path, "viewer")
    _grant(app_db, users.editor, library_path, "editor")

    result = list_library_entity_types(
        _request(users.viewer),
        library_path,
        _get_db_manager(),
    )
    assert result.count == 0

    with pytest.raises(HTTPException) as viewer_write_exc:
        add_library_entity_type(
            _request(users.viewer),
            library_path,
            "person",
            True,
            _get_db_manager(),
        )
    assert viewer_write_exc.value.status_code == 403

    created = add_library_entity_type(
        _request(users.editor),
        library_path,
        "person",
        True,
        _get_db_manager(),
    )
    assert created.entity_type_key == "person"

    with pytest.raises(HTTPException) as stranger_exc:
        list_library_entity_types(
            _request(users.stranger),
            library_path,
            _get_db_manager(),
        )
    assert stranger_exc.value.status_code == 403

    outside = tmp_path / "not-a-library"
    outside.mkdir()
    with pytest.raises(HTTPException) as path_exc:
        _get_library_db(
            _request(users.editor),
            str(outside),
            _get_db_manager(),
            write=False,
        )
    assert path_exc.value.status_code == 403


def test_app_wide_config_gates_require_authenticated_owner(users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")

    _require_authenticated_or_bootstrap(_request(users.viewer))
    with pytest.raises(HTTPException) as anon_exc:
        _require_authenticated_or_bootstrap(_request(None))
    assert anon_exc.value.status_code == 401

    _require_owner_or_bootstrap(_request(users.owner))
    with pytest.raises(HTTPException) as viewer_exc:
        _require_owner_or_bootstrap(_request(users.viewer))
    assert viewer_exc.value.status_code == 403

    bootstrap_request = SimpleNamespace(state=SimpleNamespace(bootstrap_auth=True, user=None))
    _require_authenticated_or_bootstrap(bootstrap_request)
    _require_owner_or_bootstrap(bootstrap_request)


def test_app_wide_config_gates_short_circuit_when_multiuser_off(users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")

    # Flag OFF → both gates allow everyone (return None, no HTTPException), even
    # an unauthenticated request and a viewer who would be rejected by the owner
    # gate once FICHERO_MULTIUSER is enabled.
    assert _require_authenticated_or_bootstrap(_request(None)) is None
    assert _require_owner_or_bootstrap(_request(users.viewer)) is None


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


def test_owner_can_revoke_role_and_access_is_lost(
    db, app_db, users, acl_action, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)
    normalized = authz.normalize_library_path(library_path)
    _grant(app_db, users.owner, library_path, "owner")
    _grant(app_db, users.editor, library_path, "editor")

    # Precondition: editor can invoke the mutating action.
    assert registry.invoke(
        db, acl_action, {}, ActionContext(actor="editor", library_path=library_path)
    ).ok is True

    registry.invoke(
        db,
        "acl.set",
        {"user": "editor", "remove": True},
        ActionContext(actor="owner", library_path=library_path),
    )

    # Role row is gone and the now role-less editor is denied (fail-closed).
    assert app_db.get_library_role(users.editor.id, normalized) is None
    with pytest.raises(authz.AuthorizationError):
        registry.invoke(
            db, acl_action, {}, ActionContext(actor="editor", library_path=library_path)
        )


def test_owner_cannot_revoke_their_own_role(db, app_db, users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)
    normalized = authz.normalize_library_path(library_path)
    _grant(app_db, users.owner, library_path, "owner")

    with pytest.raises(authz.AuthorizationError):
        registry.invoke(
            db,
            "acl.set",
            {"user": "owner", "remove": True},
            ActionContext(actor="owner", library_path=library_path),
        )
    # The sole owner keeps their role — no self-lockout.
    assert app_db.get_library_role(users.owner.id, normalized) is not None


def test_non_owner_cannot_revoke(db, app_db, users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)
    normalized = authz.normalize_library_path(library_path)
    _grant(app_db, users.owner, library_path, "owner")
    _grant(app_db, users.editor, library_path, "editor")
    _grant(app_db, users.viewer, library_path, "viewer")

    with pytest.raises(authz.AuthorizationError):
        registry.invoke(
            db,
            "acl.set",
            {"user": "editor", "remove": True},
            ActionContext(actor="viewer", library_path=library_path),
        )
    # Editor's role is untouched.
    assert app_db.get_library_role(users.editor.id, normalized) is not None


@pytest.mark.anyio
async def test_multiuser_off_leaves_registry_and_read_dependency_unchanged(
    db, users, acl_action, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
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


def test_assert_can_write_bypasses_single_user_but_denies_multiuser_without_role(
    db, users, monkeypatch
):
    library_path = _library_path(db)

    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    authz.assert_can_write("ui", library_path)

    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    with pytest.raises(authz.AuthorizationError):
        authz.assert_can_write(users.stranger, library_path)


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


def test_acl_enforcement_stays_at_shared_choke_points():
    # Resolve from this file, not the cwd: the documented gate runs pytest from
    # fichero-server/, where a repo-root-relative path raised FileNotFoundError
    # and turned this ACL check red for a reason that has nothing to do with
    # ACLs. A security test that fails for a false reason gets ignored.
    root = Path(__file__).resolve().parents[3] / "src" / "fichero_server"
    registry_source = (root / "actions" / "registry.py").read_text(encoding="utf-8")
    api_source = (root / "api" / "main.py").read_text(encoding="utf-8")

    assert "class ActionRegistry" in registry_source
    assert "def invoke(" in registry_source
    assert "authz.assert_can_write(" in registry_source
    assert api_source.count("authz.assert_can_read(") == 1
    assert api_source.count("authz.assert_can_write(") == 1
