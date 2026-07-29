"""Regression: a fresh single-user local launch is fully authorized (#2721).

The report described hitting 401 on app-wide routes (registry/providers) and 403 on library
routes (documents/workflows/chat/search) at first launch: the per-user ACL
layer was on by default but a fresh install has no account/role rows, so the
authorizer denied the Mac owner access to its own library.

These tests assert that, under the DEFAULT environment (no FICHERO_MULTIUSER,
no remote signals), the loopback bootstrap token authorizes every route.
"""

from __future__ import annotations

import pytest

from fichero_server.security.multiuser import multiuser_enabled


_APP_WIDE_ROUTES = ["/api/registry", "/api/providers"]
_LIBRARY_ROUTES = [
    "/api/documents",
    "/api/workflows",
    "/api/chat/conversations",
    "/api/search/saved",
]


@pytest.fixture
def fresh_launch(client, test_package):
    # Shared `client` fixture already attaches the bootstrap-token middleware
    # and authenticates over loopback; single-user is the default (#2721).
    client.headers["X-Fichero-Library-Path"] = str(test_package)
    return client


def test_fresh_launch_defaults_to_single_user(monkeypatch):
    for name in (
        "FICHERO_MULTIUSER",
        "FICHERO_PUBLIC_BASE_URL",
        "FICHERO_ENABLE_BONJOUR",
        "FICHERO_BIND_HOST",
        "FICHERO_REMOTE_BACKEND_BIND_HOST",
    ):
        monkeypatch.delenv(name, raising=False)
    assert multiuser_enabled() is False


def test_fresh_launch_app_wide_routes_not_401(fresh_launch):
    for path in _APP_WIDE_ROUTES:
        response = fresh_launch.get(path)
        assert response.status_code != 401, f"401 on {path}: {response.text}"


def test_fresh_launch_library_routes_not_403(fresh_launch):
    for path in _LIBRARY_ROUTES:
        response = fresh_launch.get(path)
        assert response.status_code != 403, f"403 on {path}: {response.text}"


def test_fresh_launch_all_routes_authorized(fresh_launch):
    for path in _APP_WIDE_ROUTES + _LIBRARY_ROUTES:
        response = fresh_launch.get(path)
        assert response.status_code == 200, f"{response.status_code} on {path}: {response.text}"
