"""#1867 hardening — share backend edge cases.

Re-sharing (role upgrade/downgrade), idempotency, share-link shape per object
type, and input normalization (case / whitespace). Complements
test_authz_share_route.py's happy-path + fail-loud coverage.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.security import accounts
from fichero_server.security import authz
from fichero_server.actions.registry import ActionContext
from fichero_server.api.routes.auth.authz import share_library_object
from fichero_server.models import ShareRequest

import fichero_server.api.routes.system.actions_registry  # noqa: F401 - registers acl.set


@pytest.fixture
def users(app_db):
    def mk(username, display, owner=False):
        return app_db.create_user(
            username=username,
            display_name=display,
            password_hash=accounts.hash_password("pw"),
            is_owner=owner,
        )

    return SimpleNamespace(owner=mk("owner", "Owner", owner=True), alice=mk("alice", "Alice"))


def _request(user, base_url="https://engine.local:8765/"):
    return SimpleNamespace(state=SimpleNamespace(user=user), base_url=base_url)


@pytest.fixture
def seeded(db, app_db, users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = str(db.path.parent)
    normalized = authz.normalize_library_path(library_path)
    app_db.set_library_role(user_id=users.owner.id, library_path=normalized, role=authz.ROLE_OWNER)
    return SimpleNamespace(library_path=library_path, normalized=normalized)


def _share(db, users, seeded, **kw):
    ctx = ActionContext(actor=users.owner.id, library_path=seeded.normalized)
    body = ShareRequest(user=users.alice.id, **kw)
    return share_library_object(body, _request(users.owner), db, ctx, seeded.library_path)


def test_reshare_upgrades_then_downgrades_role(db, app_db, users, seeded):
    _share(db, users, seeded, role="viewer")
    assert app_db.get_library_role(users.alice.id, seeded.normalized).role == authz.ROLE_VIEWER

    _share(db, users, seeded, role="editor")
    assert app_db.get_library_role(users.alice.id, seeded.normalized).role == authz.ROLE_EDITOR
    assert authz.can_write(users.alice, seeded.library_path) is True

    _share(db, users, seeded, role="viewer")
    assert app_db.get_library_role(users.alice.id, seeded.normalized).role == authz.ROLE_VIEWER
    assert authz.can_write(users.alice, seeded.library_path) is False


def test_reshare_same_role_is_idempotent(db, app_db, users, seeded):
    _share(db, users, seeded, role="editor")
    _share(db, users, seeded, role="editor")
    rows = [r for r in app_db.list_library_roles(seeded.normalized) if r.user_id == users.alice.id]
    assert len(rows) == 1 and rows[0].role == authz.ROLE_EDITOR


def test_share_url_shape_per_object_type(db, users, seeded):
    lib = _share(db, users, seeded, role="viewer", object_type="library")
    assert lib.share_url == "https://engine.local:8765"

    ent = _share(db, users, seeded, role="viewer", object_type="entity", object_id="ent-7")
    assert ent.share_url == "https://engine.local:8765/api/entities/ent-7"

    doc = _share(db, users, seeded, role="viewer", object_type="document", object_id="doc-9")
    assert doc.share_url == "https://engine.local:8765/api/documents/doc-9"


def test_object_type_is_case_and_whitespace_normalized(db, app_db, users, seeded):
    resp = _share(db, users, seeded, role="viewer", object_type="  DOCUMENT  ", object_id="d1")
    assert resp.object_type == "document"
    assert resp.share_url == "https://engine.local:8765/api/documents/d1"


def test_sharing_owner_with_self_keeps_owner(db, app_db, users, seeded):
    # Owner "shares" the library with themselves — a no-op upgrade, still owner.
    ctx = ActionContext(actor=users.owner.id, library_path=seeded.normalized)
    body = ShareRequest(user=users.owner.id, role="owner")
    share_library_object(body, _request(users.owner), db, ctx, seeded.library_path)
    assert app_db.get_library_role(users.owner.id, seeded.normalized).role == authz.ROLE_OWNER
