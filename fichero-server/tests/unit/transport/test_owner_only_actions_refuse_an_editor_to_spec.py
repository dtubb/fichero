"""library-sharing: an owner-only action refuses an editor wherever it is reached (review 58).

`sharing.set_multiuser` and `acl.set` are owner-only. The route-level check is not enough: the generic
`POST /api/actions/invoke` (and so MCP and chat) needs only library WRITE, so an editor could switch
Multi-user off and become owner of everything. The action asserts the owner itself.
"""

from __future__ import annotations

import pytest

from fichero_server.actions import ActionContext, registry
from fichero_server.db import db_manager
from fichero_server.security import accounts, authz
from tests.unit.transport.test_two_macs_end_to_end_to_spec import _bearer, two_macs  # noqa: F401


@pytest.fixture
def editor(two_macs, app_db, test_package):  # noqa: F811
    user = app_db.create_user(
        username="ed", display_name="Ed", password_hash=accounts.hash_password("password"), is_owner=False
    )
    app_db.set_library_role(
        user_id=user.id, library_path=authz.normalize_library_path(str(test_package)), role="editor"
    )
    return user


def _session(client, username):
    return client.post("/api/auth/login", json={"username": username, "password": "password"}).json()["session_token"]


@pytest.mark.parametrize(
    ("name", "params"),
    [
        ("sharing.set_multiuser", {"enabled": False}),
        ("acl.set", {"user": "owner", "role": "viewer"}),
    ],
)
def test_an_editor_is_refused_through_actions_invoke(two_macs, editor, name, params):  # noqa: F811
    a = two_macs["a"]
    response = a.post("/api/actions/invoke", json={"name": name, "params": params}, headers=_bearer(_session(a, "ed")))
    assert response.status_code == 403, response.text


def test_an_editor_is_refused_at_the_registry_the_mcp_tools_share(editor, test_package, app_db, monkeypatch):
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    library_db = db_manager.get_database(test_package)
    ctx = ActionContext(actor="ed", library_path=str(test_package))
    with pytest.raises(authz.AuthorizationError):
        registry.invoke(library_db, "sharing.set_multiuser", {"enabled": False}, ctx)
    assert app_db.get_setting("multiuser.enabled") is None
