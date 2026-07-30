"""#1867 — Share button backend (authz-gated model).

Sharing an object grants the recipient a per-library role via the audited
``acl.set`` action and returns an engine link to the object. These pin the
happy paths, the fail-loud validation, and that only an owner can share.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import fichero_server.api.routes.system.actions_registry  # noqa: F401 - registers acl.set
from fichero_server.security import accounts
from fichero_server.security import authz
from fichero_server.actions.registry import ActionContext
from fichero_server.api.routes.auth.authz import share_library_object
from fichero_server.models import AccountUser, ShareRequest


@pytest.fixture
def users(app_db):
    def mk(username, display, owner=False):
        return app_db.create_user(
            username=username,
            display_name=display,
            password_hash=accounts.hash_password("pw"),
            is_owner=owner,
        )

    return SimpleNamespace(
        owner=mk("owner", "Owner", owner=True),
        alice=mk("alice", "Alice"),
        viewer=mk("viewer", "Viewer"),
    )


def _request(user: AccountUser | None, base_url="https://engine.local:8765/"):
    return SimpleNamespace(state=SimpleNamespace(user=user), base_url=base_url)


def _grant(app_db, user, library_path, role):
    app_db.set_library_role(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        role=role,
    )


@pytest.fixture
def seeded(db, app_db, users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = str(db.path.parent)
    normalized = authz.normalize_library_path(library_path)
    _grant(app_db, users.owner, library_path, authz.ROLE_OWNER)
    return SimpleNamespace(library_path=library_path, normalized=normalized)


def test_share_library_grants_role_and_returns_link(db, app_db, users, seeded):
    ctx = ActionContext(actor=users.owner.id, library_path=seeded.normalized)
    body = ShareRequest(user=users.alice.id, role="viewer", object_type="library")

    resp = share_library_object(body, _request(users.owner), db, ctx, seeded.library_path)

    assert resp.role == "viewer"
    assert resp.object_type == "library"
    assert resp.share_url == "https://engine.local:8765"
    # The recipient now actually has access.
    assert app_db.get_library_role(users.alice.id, seeded.normalized).role == authz.ROLE_VIEWER
    assert authz.can_read(users.alice, seeded.library_path) is True


def test_share_document_links_to_object_and_grants_access(db, app_db, users, seeded):
    ctx = ActionContext(actor=users.owner.id, library_path=seeded.normalized)
    body = ShareRequest(
        user=users.alice.id, role="editor", object_type="document", object_id="doc-42"
    )

    resp = share_library_object(body, _request(users.owner), db, ctx, seeded.library_path)

    assert resp.object_id == "doc-42"
    assert resp.share_url == "https://engine.local:8765/api/documents/doc-42"
    # Sharing a document grants library access (per-library ACL).
    assert authz.can_write(users.alice, seeded.library_path) is True


def test_non_owner_cannot_share(db, app_db, users, seeded):
    _grant(app_db, users.viewer, seeded.library_path, authz.ROLE_VIEWER)
    ctx = ActionContext(actor=users.viewer.id, library_path=seeded.normalized)
    body = ShareRequest(user=users.alice.id, role="viewer")

    with pytest.raises(HTTPException) as exc:
        share_library_object(body, _request(users.viewer), db, ctx, seeded.library_path)
    assert exc.value.status_code == 403
    # No access leaked to the recipient.
    assert app_db.get_library_role(users.alice.id, seeded.normalized) is None


def test_invalid_role_is_rejected(db, app_db, users, seeded):
    ctx = ActionContext(actor=users.owner.id, library_path=seeded.normalized)
    body = ShareRequest(user=users.alice.id, role="superadmin")
    with pytest.raises(HTTPException) as exc:
        share_library_object(body, _request(users.owner), db, ctx, seeded.library_path)
    assert exc.value.status_code == 422
    assert app_db.get_library_role(users.alice.id, seeded.normalized) is None


def test_document_share_requires_object_id(db, app_db, users, seeded):
    ctx = ActionContext(actor=users.owner.id, library_path=seeded.normalized)
    body = ShareRequest(user=users.alice.id, role="viewer", object_type="document")
    with pytest.raises(HTTPException) as exc:
        share_library_object(body, _request(users.owner), db, ctx, seeded.library_path)
    assert exc.value.status_code == 422
    # Validation fails before any grant.
    assert app_db.get_library_role(users.alice.id, seeded.normalized) is None


def test_invalid_object_type_is_rejected(db, app_db, users, seeded):
    ctx = ActionContext(actor=users.owner.id, library_path=seeded.normalized)
    body = ShareRequest(user=users.alice.id, role="viewer", object_type="planet")
    with pytest.raises(HTTPException) as exc:
        share_library_object(body, _request(users.owner), db, ctx, seeded.library_path)
    assert exc.value.status_code == 422
