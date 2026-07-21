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

# Attach the enforcing auth middleware to the shared app ONCE, at conftest LOAD —
# before any test module is collected. A module-level `TestClient(app)` (e.g.
# tests/unit/test_api_providers.py) can start the shared app's lifespan during
# collection; if the middleware weren't already attached by then, that first
# `add_middleware` would raise "Cannot add middleware after an application has
# started" and — because it raises before the guard flips True — cascade to
# EVERY later test's setup (the 7941-error storm, #4039). Attaching here, before
# any test module imports, closes that window. The autouse fixture below stays as
# an idempotent safety net.
_UNIT_TEST_AUTH_TOKEN = initialize_token()
attach_auth_middleware(app, _UNIT_TEST_AUTH_TOKEN)
_AUTH_MIDDLEWARE_ATTACHED = True


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
def _unit_test_auth_header():
    """Re-attach the auth middleware bound to the engine bootstrap token.

    Must NOT depend on the ``client`` fixture: ``client`` pulls in
    ``test_package``, which writes ``<tmp_path>/test.fichero/...`` into the
    per-test ``tmp_path``. Tests that scan ``tmp_path`` (ingest discovery) or
    build their own ``Database(tmp_path / "test.fichero")`` (canonical KG routes)
    then collide with that package. The actual token header is injected into
    every TestClient request by ``_unit_test_auth_all_testclients`` below, so the
    shared ``client`` fixture is still authenticated without being force-created
    for tests that never ask for it.
    """
    global _UNIT_TEST_AUTH_TOKEN, _AUTH_MIDDLEWARE_ATTACHED
    if _UNIT_TEST_AUTH_TOKEN is None:
        _UNIT_TEST_AUTH_TOKEN = initialize_token()
    if not _AUTH_MIDDLEWARE_ATTACHED:
        attach_auth_middleware(app, _UNIT_TEST_AUTH_TOKEN)
        _AUTH_MIDDLEWARE_ATTACHED = True
    yield


@pytest.fixture(autouse=True)
def _unit_test_auth_all_testclients(monkeypatch):
    """Inject the bootstrap token into EVERY ``TestClient`` request, not just the
    shared ``client`` fixture.

    ``_unit_test_auth_header`` re-attaches the enforcing auth middleware to the
    shared ``app`` (module-global, persists for the whole session), but many
    route-test modules build their OWN bare ``TestClient(app)`` (e.g.
    ``test_api_providers``, ``test_library_entity_types``, ``test_routes_library``)
    instead of the shared fixture. Those clients carried no Authorization header
    and so 401'd against the re-attached middleware. Inject the token via
    ``setdefault`` so it never clobbers a header a security/negative-auth test set
    deliberately (those tests pass an explicit/empty/wrong header or run their own
    multi-user setup).
    """
    global _UNIT_TEST_AUTH_TOKEN
    if _UNIT_TEST_AUTH_TOKEN is None:
        _UNIT_TEST_AUTH_TOKEN = initialize_token()
    token_header = f"Bearer {_UNIT_TEST_AUTH_TOKEN}"

    from starlette.testclient import TestClient

    original_request = TestClient.request

    def _request_with_default_auth(self, *args, **kwargs):
        self.headers.setdefault("Authorization", token_header)
        return original_request(self, *args, **kwargs)

    monkeypatch.setattr(TestClient, "request", _request_with_default_auth)
    yield
