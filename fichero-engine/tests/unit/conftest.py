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
