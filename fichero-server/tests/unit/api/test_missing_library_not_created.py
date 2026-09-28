"""A request naming a library that does not exist must never create it (#5136).

WHY: every request the app, CLI or MCP sends carries
``X-Fichero-Library-Path``. Before this fix, resolving that header opened the
library with ``db_manager.get_database``, and ``Database.__init__`` ran
``path.parent.mkdir(parents=True)`` — so a mistyped path, a library moved in
Finder, or even a health probe (``GET /api/health``, the acceptance run's
first call, 2026-09-27) silently CREATED an empty ``.fichero`` package and
every missing parent folder. The person then "opens" an empty library that
looks like theirs, and imports land in it. If this regresses, these tests see
the package appear on disk.

Only ``POST /api/library`` may create a library; the last test pins that it
still does.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fichero_server.api.auth import initialize_token
from fichero_server.api.main import app
from fichero_server.db import db_manager
from fichero_server.db.manager import LibraryNotFoundError

_TOKEN: str | None = None


def _client() -> TestClient:
    # Same bootstrap-token client as test_routes_library.py: the unit
    # conftest already attached the auth middleware.
    global _TOKEN
    if _TOKEN is None:
        _TOKEN = initialize_token()
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {_TOKEN}"
    return client


def _missing(tmp_path: Path) -> Path:
    # A missing parent folder too: the old code created the whole chain.
    target = tmp_path / "not-yet" / "Nowhere.fichero"
    assert not target.parent.exists()
    return target


def test_health_with_missing_library_header_creates_nothing(tmp_path: Path) -> None:
    """A health probe naming a missing library reports it and creates nothing."""
    target = _missing(tmp_path)

    response = _client().get(
        "/api/health", headers={"X-Fichero-Library-Path": str(target)}
    )

    assert not target.exists(), "health check created the library package"
    assert not target.parent.exists(), "health check created the parent folder"
    body = response.json()
    assert body["status"] != "healthy"
    assert "does not exist" in (body.get("error") or "")


def test_library_route_with_missing_library_is_refused_and_creates_nothing(
    tmp_path: Path,
) -> None:
    """A library-scoped route answers 404 with a clear reason, never creates."""
    target = _missing(tmp_path)

    response = _client().get(
        "/api/documents", headers={"X-Fichero-Library-Path": str(target)}
    )

    assert not target.exists(), "a library route created the library package"
    assert not target.parent.exists()
    assert response.status_code == 404, response.text
    assert "does not exist" in response.json()["detail"]


def test_manager_refuses_missing_package_unless_create_is_explicit(
    tmp_path: Path,
) -> None:
    """The one place a library is opened refuses a missing package by default."""
    target = _missing(tmp_path)

    with pytest.raises(LibraryNotFoundError):
        db_manager.get_database(target)
    assert not target.parent.exists()

    try:
        db = db_manager.get_database(target, create=True)
        assert db is not None
        assert (target / "fichero.duckdb").exists()
    finally:
        db_manager.close_database(target)


def test_post_library_still_creates(tmp_path: Path) -> None:
    """``POST /api/library`` is the one request allowed to create a library."""
    target = _missing(tmp_path)

    response = _client().post("/api/library", json={"path": str(target)})

    try:
        assert response.status_code == 200, response.text
        assert response.json()["created"] is True
        assert (target / "fichero.duckdb").exists()
    finally:
        db_manager.close_database(target)


def test_health_never_opens_a_library_it_names(tmp_path: Path) -> None:
    """#5257: the app's readiness probe and heartbeat carry the library header on every call. Health
    opened the library (~6 s for a large one; the whole launch waited on it) and loaded every
    document to count them, on each poll. A library that isn't open yet is reported healthy and
    left closed; it is opened by the first request that actually uses it."""
    from fichero_server.db.manager import db_manager

    library = tmp_path / "Present.fichero"
    library.mkdir()
    assert not db_manager.is_open(library)

    response = _client().get("/api/health", headers={"X-Fichero-Library-Path": str(library)})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "healthy"
    assert not db_manager.is_open(library), "a health check opened the library"


def test_health_never_walks_the_mlx_runtime(monkeypatch) -> None:
    """#5228: each health call cost ~1.1 s -- `status()` adds up the MLX runtime's disk usage by
    walking every file (22,869 on the maintainer's Mac) -- and health is the app's heartbeat. It reads
    the recorded versions only."""
    from fichero_server.llm import mlx_runtime

    def walked(self):  # pragma: no cover - the assertion is that this never runs
        raise AssertionError("health walked the MLX runtime for its disk usage")

    monkeypatch.setattr(mlx_runtime.MLXRuntime, "_disk_usage_bytes", walked, raising=False)
    response = _client().get("/api/health")
    assert response.status_code == 200, response.text
