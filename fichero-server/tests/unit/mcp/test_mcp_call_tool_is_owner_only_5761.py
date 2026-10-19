"""Review 157 (#5761): `mcp.call_tool` is the owner's. An editor, a paired device or an unsigned local client cannot
reach it through `POST /api/actions/invoke`, and a chat whose actor is not the owner is never offered MCP tools."""
from __future__ import annotations

import pytest

from fichero_server.security import accounts, authz
from tests.unit.transport.test_two_macs_end_to_end_to_spec import _bearer, two_macs  # noqa: F401

CALL = {"name": "mcp.call_tool", "params": {"server": "echoer", "tool": "echo", "arguments": {"text": "hi"}}}


def test_the_action_is_declared_owner_only():
    import fichero_server.api.main  # noqa: F401
    from fichero_server.actions.registry import registry

    assert registry.get("mcp.call_tool").owner_only is True


def _login(client, username):
    return client.post("/api/auth/login", json={"username": username, "password": "password"}).json()["session_token"]


def test_an_editor_is_refused_through_actions_invoke(two_macs, app_db, test_package):  # noqa: F811
    user = app_db.create_user(username="ed", display_name="Ed", password_hash=accounts.hash_password("password"),
                              is_owner=False)
    app_db.set_library_role(user_id=user.id, library_path=authz.normalize_library_path(str(test_package)), role="editor")
    a = two_macs["a"]
    response = a.post("/api/actions/invoke", json=CALL, headers=_bearer(_login(a, "ed")))
    assert response.status_code == 403, response.text


def test_a_device_paired_by_an_editor_is_refused_through_actions_invoke(two_macs, app_db, test_package):  # noqa: F811
    # A device acts as the account that paired it (an owner's own Mac is the owner), so this one is the editor's.
    user = app_db.create_user(username="ed", display_name="Ed", password_hash=accounts.hash_password("password"),
                              is_owner=False)
    app_db.set_library_role(user_id=user.id, library_path=authz.normalize_library_path(str(test_package)), role="editor")
    token = accounts.new_session_token()
    app_db.create_device(name="Ed's Mac", user_id=user.id, token_hash=accounts.hash_token(token))
    response = two_macs["b"].post("/api/actions/invoke", json=CALL, headers=_bearer(token))
    assert response.status_code == 403, response.text


def test_a_client_with_no_valid_credential_is_refused_through_actions_invoke(two_macs):  # noqa: F811
    response = two_macs["a"].post("/api/actions/invoke", json=CALL, headers=_bearer("not-a-credential"))
    assert response.status_code in (401, 403), response.text
