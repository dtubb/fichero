from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero.security import accounts
from fichero.security import authz
from fichero.db.manager import db_manager
from fichero.models import AccountUser, Document, DocType


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
    inactive = app_db.create_user(
        username="inactive",
        display_name="Inactive",
        password_hash=accounts.hash_password("password"),
        active=False,
    )
    return SimpleNamespace(
        owner=owner,
        editor=editor,
        viewer=viewer,
        inactive=inactive,
    )


def _library_path(db) -> str:
    return str(db.path.parent)


def _grant(app_db, user: AccountUser, library_path: str, role: str) -> None:
    app_db.set_library_role(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        role=role,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", True),
        (" true ", True),
        ("YES", True),
        ("off", False),
        ("0", False),
        # Empty/unset falls through to the default: multiuser is OPT-IN, so a
        # single-user local launch with no explicit flag and no remote signal
        # stays OFF (fichero/multiuser.py, #2721).
        ("", False),
    ],
)
def test_multiuser_enabled_parses_truthy_and_falsey_values(monkeypatch, raw, expected):
    monkeypatch.setenv("FICHERO_MULTIUSER", raw)
    assert authz.multiuser_enabled() is expected


def test_resolve_user_accepts_id_and_username_but_rejects_blank_system_and_inactive(app_db, users):
    by_id = authz.resolve_user(users.owner.id)
    by_username = authz.resolve_user(" owner ")

    assert by_id is not None
    assert by_id.id == users.owner.id
    assert by_username is not None
    assert by_username.id == users.owner.id
    assert authz.resolve_user("") is None
    assert authz.resolve_user("system") is None
    assert authz.resolve_user(users.inactive.id) is None
    assert authz.resolve_user("missing-user") is None


def test_require_owner_returns_resolved_owner_and_rejects_non_owner_or_missing_library(
    db, app_db, users, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)
    _grant(app_db, users.owner, library_path, "owner")
    _grant(app_db, users.viewer, library_path, "viewer")

    resolved = authz.require_owner("owner", library_path)
    assert resolved.id == users.owner.id
    assert resolved.username == "owner"

    with pytest.raises(authz.AuthorizationError, match="owner access required"):
        authz.require_owner("viewer", library_path)
    with pytest.raises(authz.AuthorizationError, match="owner access required"):
        authz.require_owner("owner", None)


def test_set_role_requires_owner_normalizes_role_and_rejects_invalid_targets(
    db, app_db, users, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)
    _grant(app_db, users.owner, library_path, "owner")
    _grant(app_db, users.viewer, library_path, "viewer")

    updated = authz.set_role(
        actor="owner",
        library=library_path,
        user="viewer",
        role=" EDITOR ",
    )
    assert updated.role == "editor"
    assert app_db.get_library_role(users.viewer.id, authz.normalize_library_path(library_path)).role == "editor"

    with pytest.raises(ValueError, match="invalid library role"):
        authz.set_role(
            actor="owner",
            library=library_path,
            user="viewer",
            role="admin",
        )
    with pytest.raises(ValueError, match="unknown user or library"):
        authz.set_role(
            actor="owner",
            library=library_path,
            user="inactive",
            role="viewer",
        )
    with pytest.raises(authz.AuthorizationError, match="owner access required"):
        authz.set_role(
            actor="viewer",
            library=library_path,
            user="editor",
            role="viewer",
        )


def test_set_override_validates_effect_and_target_and_specific_grant_beats_ancestor_deny(
    db, app_db, users, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = _library_path(db)
    _grant(app_db, users.owner, library_path, "owner")
    _grant(app_db, users.editor, library_path, "editor")
    _grant(app_db, users.viewer, library_path, "viewer")

    folder = Document(name="Parent", doc_type=DocType.folder)
    db.save(folder)
    child = Document(name="Child", parent_id=folder.id)
    db.save(child)
    sibling = Document(name="Sibling", parent_id=folder.id)
    db.save(sibling)

    denied = authz.set_override(
        actor="owner",
        library=library_path,
        user="editor",
        target_id=folder.id,
        effect="DENY",
    )
    granted = authz.set_override(
        actor="owner",
        library=library_path,
        user="editor",
        target_id=child.id,
        effect="grant",
    )

    assert denied.effect == "deny"
    assert granted.effect == "grant"
    assert authz.can_write(users.editor, library_path, child.id) is True
    assert authz.can_read(users.editor, library_path, child.id) is True
    assert authz.can_write(users.editor, library_path, sibling.id) is False
    assert authz.can_read(users.editor, library_path, sibling.id) is False

    authz.set_override(
        actor="owner",
        library=library_path,
        user="viewer",
        target_id=child.id,
        effect="grant",
    )
    assert authz.can_read(users.viewer, library_path, child.id) is True
    assert authz.can_write(users.viewer, library_path, child.id) is False

    with pytest.raises(ValueError, match="invalid ACL override effect"):
        authz.set_override(
            actor="owner",
            library=library_path,
            user="editor",
            target_id=child.id,
            effect="allow",
        )
    with pytest.raises(ValueError, match="unknown user, library, or target"):
        authz.set_override(
            actor="owner",
            library=library_path,
            user="editor",
            target_id="",
            effect="deny",
        )


def test_target_ancestor_ids_fails_closed_to_raw_target_when_lookup_breaks(db, monkeypatch):
    library_path = _library_path(db)
    database = db_manager.get_database(library_path)

    def boom(*_args, **_kwargs):
        raise RuntimeError("lookup failed")

    monkeypatch.setattr(database, "get", boom)
    assert authz._target_ancestor_ids(library_path, "doc-123") == ["doc-123"]
