"""Releasing a project keeps it registered (#5563).

WHY: applying dates to the real Marshall project through the CLI, the only close the CLI/MCP
offered (`fichero library close`, the registry DELETE) UNREGISTERED the project -- it would vanish
from the app's sidebar. An agent or operator needs "release this project": the engine closes its
connection and stops its background work for it, and the project stays registered; opening it
again works as before. And a release must never START work (#5562): no conversion, no snapshot.

Through the real route, `POST /api/registry/release`, with the real database manager.
"""

from __future__ import annotations

import threading
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

import fichero_server.api.routes.library.registry as registry
from fichero_server.api.main import app
from fichero_server.api.routes.library.registry import get_global_database
from fichero_server.db import Database
from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs
from fichero_server.maintenance import conversion_on_open
from fichero_server.models import ActionAudit, KnownLibrary


@pytest.fixture
def project(tmp_path, monkeypatch, app_db):
    """A registered project, open in the engine, with the global registry in tmp."""
    package = tmp_path / "Marshall Release.fichero"
    global_db = Database(path=tmp_path / "global.fichero" / "fichero.duckdb")
    app.dependency_overrides[get_global_database] = lambda: global_db
    monkeypatch.setattr(registry, "get_global_database", lambda: global_db)
    monkeypatch.setattr(registry, "_OWNER_OPENED_LOADED", False)
    db_manager.get_database(package, create=True)
    stored = str(Path(package).resolve())
    global_db.save(KnownLibrary(path=stored, name=package.stem))
    try:
        yield package, global_db
    finally:
        app.dependency_overrides.pop(get_global_database, None)
        db_manager.close_all()
        global_db.conn.close()


def _release(client: TestClient, package: Path):
    return client.post("/api/registry/release", json={"path": str(package)})


def _no_start_spies(monkeypatch) -> list[str]:
    """Record any conversion start or snapshot a release makes, with conversion switched ON."""
    calls: list[str] = []
    monkeypatch.delenv("FICHERO_SKIP_PROJECT_CONVERSION", raising=False)
    real_start = conversion_on_open.start
    monkeypatch.setattr(conversion_on_open, "start", lambda *a, **k: calls.append("conversion") or real_start(*a, **k))
    import fichero_server.db.storage_snapshots as snapshots

    real_snapshot = snapshots.snapshot_library
    monkeypatch.setattr(snapshots, "snapshot_library",
                        lambda *a, **k: calls.append("snapshot") or real_snapshot(*a, **k))
    return calls


def test_release_closes_the_connection_and_keeps_the_project_registered(project, monkeypatch):
    package, global_db = project
    calls = _no_start_spies(monkeypatch)
    assert db_manager.is_open(package)

    response = _release(TestClient(app), package)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "released"
    assert body["registered"] is True
    assert not db_manager.is_open(package), "the engine still holds the project's connection"
    assert [lib.path for lib in global_db.all(KnownLibrary)] == [str(package.resolve())], \
        "a release must leave the project registered (the sidebar keeps it)"
    listed = TestClient(app).get("/api/registry").json()
    assert [lib["path"] for lib in listed["libraries"]] == [str(package.resolve())]
    assert calls == [], f"a release started work: {calls}"
    audits = [a for a in global_db.all(ActionAudit) if a.action_name == "library.release"]
    assert len(audits) == 1 and audits[0].target_ids == [str(package.resolve())]


def test_a_released_project_opens_again_as_before(project):
    package, _ = project
    client = TestClient(app)
    db_manager.get_database(package).execute("CREATE TABLE kept (v INTEGER)")
    db_manager.get_database(package).execute("INSERT INTO kept VALUES (7)")
    assert _release(client, package).json()["status"] == "released"

    reopened = client.get(
        "/api/activity/jobs", headers={"X-Fichero-Library-Path": quote(str(package), safe="/")}
    )

    assert reopened.status_code == 200, reopened.text
    assert db_manager.is_open(package)
    assert db_manager.get_database(package).execute_fetchone("SELECT v FROM kept") == (7,)


def test_releasing_a_project_with_no_connection_never_opens_it(project, monkeypatch):
    package, _ = project
    client = TestClient(app)
    assert _release(client, package).json()["status"] == "released"
    calls = _no_start_spies(monkeypatch)

    again = _release(client, package)

    assert again.status_code == 200, again.text
    assert again.json()["status"] == "not_open"
    assert not db_manager.is_open(package), "releasing a closed project opened it"
    assert calls == []


def test_release_refuses_while_a_workflow_run_is_going(project):
    package, global_db = project
    db = db_manager.get_database(package)
    jobs._record(db, "run-1", kind="workflow", subject="run-1", parent_id=None, state="running",
                 reason=None, name="Read the diary")

    response = _release(TestClient(app), package)

    assert response.status_code == 409, response.text
    assert "Read the diary" in response.json()["detail"]
    assert db_manager.is_open(package), "a refused release closed the project"
    assert not [a for a in global_db.all(ActionAudit) if a.action_name == "library.release"]


def test_release_stops_page_jobs_which_carry_on_when_it_opens_again(project, monkeypatch):
    package, _ = project
    db = db_manager.get_database(package)
    jobs._ensure(db)
    db.execute(
        "INSERT INTO jobs (id, kind, subject, state, attempts, started_by, created_at) VALUES "
        "('j1', 'embed', 'doc-1', 'running', 1, 'automatic', now()), "
        "('j2', 'embed', 'doc-2', 'waiting', 0, 'automatic', now())"
    )
    stopped: list[str | None] = []
    real_stop = jobs.stop
    monkeypatch.setattr(jobs, "stop", lambda key, *a, **k: stopped.append(key) or real_stop(key, *a, **k))

    body = _release(TestClient(app), package).json()

    assert body["status"] == "released"
    assert (body["jobs_stopped"], body["jobs_waiting"]) == (1, 1)
    assert stopped == [db_manager._cache_key(package)], "the project's job threads were not stopped"
    states = dict(db_manager.get_database(package).execute_fetchall("SELECT id, state FROM jobs"))
    assert states == {"j1": "waiting", "j2": "waiting"}, "jobs must carry on at the next open"


def test_release_stops_a_waiting_conversion_without_a_snapshot(project, monkeypatch):
    package, _ = project
    monkeypatch.setenv("FICHERO_CONVERSION_START_DELAY_SECONDS", "60")
    calls = _no_start_spies(monkeypatch)
    key = db_manager._cache_key(package)
    thread = conversion_on_open.start(db_manager.get_database(package), key)
    calls.clear()
    assert isinstance(thread, threading.Thread) and conversion_on_open.running(key)

    body = _release(TestClient(app), package).json()

    assert body["status"] == "released"
    assert body["conversion_stopped"] is True
    thread.join(5)
    assert not thread.is_alive(), "the conversion is still running after the release"
    assert calls == [], f"a release started work: {calls}"


def test_the_global_library_is_never_released(project):
    from fichero_server.db.storage import settings

    response = _release(TestClient(app), Path(settings.global_library_path))

    assert response.status_code == 409
