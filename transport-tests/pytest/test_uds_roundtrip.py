"""Live UDS round-trip integration test for the Fichero engine.

This exercises the engine END-TO-END over a real Unix-domain socket — not URL
construction, an actual bound uvicorn process + a real httpx UDS connection:

    1. GET /api/health              -> 200   (unauthenticated path works over UDS)
    2. GET <auth endpoint> no token -> 401   (auth IS enforced over UDS)
    3. GET <auth endpoint> + token  -> 200   (loopback-owner bootstrap grant works
                                              over UDS — the CRITICAL-1 regression
                                              at the engine level)

Run:
    PYTHONPATH=<engine>/src \
    /Users/danieltubb/code/fichero/.venv/bin/python -m pytest \
        transport-tests/pytest/test_uds_roundtrip.py -v

The harness binds `fichero.api.uds_transport:app` on a temp UDS in /tmp (short
path — mind the ~104-byte sun_path limit), with FICHERO_BASE_PATH pointed at a
fresh temp dir so it never fights a live engine for the app.duckdb lock.
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _engine_harness import start_engine  # noqa: E402

# Authenticated endpoint that needs neither a library path nor request params —
# it just requires a valid bootstrap token (see auth middleware in
# fichero/api/auth.py; not in _UNAUTHENTICATED_PATHS).
AUTH_ENDPOINT = "/api/actions/registry"


@pytest.fixture(scope="module")
def uds_engine():
    ep = start_engine(transport="uds")
    try:
        yield ep
    finally:
        ep.stop()


def test_health_unauthenticated_over_uds(uds_engine):
    with httpx.Client(timeout=10, **uds_engine.httpx_kwargs()) as client:
        r = client.get("/api/health")
    assert r.status_code == 200, r.text
    assert r.json().get("status") in {"healthy", "ok"}, r.text


def test_authenticated_endpoint_without_token_is_401(uds_engine):
    with httpx.Client(timeout=10, **uds_engine.httpx_kwargs()) as client:
        r = client.get(AUTH_ENDPOINT)
    assert r.status_code == 401, f"expected 401 without token, got {r.status_code}: {r.text}"


def test_authenticated_endpoint_with_bootstrap_token_is_200(uds_engine):
    # CRITICAL-1: the loopback-owner grant must work over the UDS marker path.
    headers = {"Authorization": f"Bearer {uds_engine.token}"}
    with httpx.Client(timeout=10, **uds_engine.httpx_kwargs()) as client:
        r = client.get(AUTH_ENDPOINT, headers=headers)
    assert r.status_code == 200, f"expected 200 with bootstrap token, got {r.status_code}: {r.text}"
    body = r.json()
    assert "items" in body and "count" in body, body


def test_wrong_token_is_401(uds_engine):
    headers = {"Authorization": "Bearer definitely-not-the-token"}
    with httpx.Client(timeout=10, **uds_engine.httpx_kwargs()) as client:
        r = client.get(AUTH_ENDPOINT, headers=headers)
    assert r.status_code == 401, f"expected 401 for a wrong token, got {r.status_code}: {r.text}"
