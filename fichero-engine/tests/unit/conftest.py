"""Unit-test fixtures that authenticate route-test TestClient requests.

The parent conftest disables the shared-secret middleware via
FICHERO_DISABLE_AUTH=1 so legacy route tests can focus on response shape.
The engine now runs with multi-user auth by default, so route requests also
need a valid bearer token. This conftest re-attaches the auth middleware
using the engine's current bootstrap token and injects the matching
Authorization header into every TestClient created by the shared client
fixture.
"""

import pytest

from fichero.api.auth import attach_auth_middleware, initialize_token
from fichero.api.main import app

_UNIT_TEST_AUTH_TOKEN: str | None = None
_AUTH_MIDDLEWARE_ATTACHED = False


@pytest.fixture(autouse=True)
def _unit_test_single_user_env(monkeypatch):
    """Force single-user mode for unit tests that drive the action registry directly.

    The engine ships with multi-user auth ON by default (``fichero/multiuser.py``),
    so ``authz.assert_can_write`` denies an unresolved actor like ``"ui"`` /
    ``"workflow"`` unless a library role row exists. The action-mechanics tests
    (``test_action_*``, ``test_*_actions``, ``test_canvas_*``) call
    ``registry.invoke(ActionContext(actor="ui", ...))`` directly — no HTTP, no
    authenticated user, no role — so they need the single-user bypass that
    ``FICHERO_MULTIUSER=0`` restores. This is the centralized sweep of the per-file
    fix landed in 6be649fd (#2642).

    Tests that exercise multi-user behaviour (``test_authz_*``, ``test_multiuser``,
    ``test_api_auth*``, ``test_auth_accounts``) explicitly ``monkeypatch.setenv`` the
    flag themselves; because ``monkeypatch`` is per-test and autouse fixtures run
    before the test body, a test's own ``setenv`` always wins over this default.
    """
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    yield


@pytest.fixture(autouse=True)
def _unit_test_auth_header(client):
    """Add the engine bootstrap bearer token to every route TestClient request."""
    global _UNIT_TEST_AUTH_TOKEN, _AUTH_MIDDLEWARE_ATTACHED
    if _UNIT_TEST_AUTH_TOKEN is None:
        _UNIT_TEST_AUTH_TOKEN = initialize_token()
    if not _AUTH_MIDDLEWARE_ATTACHED:
        attach_auth_middleware(app, _UNIT_TEST_AUTH_TOKEN)
        _AUTH_MIDDLEWARE_ATTACHED = True
    client.headers["Authorization"] = f"Bearer {_UNIT_TEST_AUTH_TOKEN}"
    yield
