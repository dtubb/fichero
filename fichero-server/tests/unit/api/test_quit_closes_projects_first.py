"""On quit the engine closes its projects first (#5644 follow-up, 2026-10-10).

The app gives the engine about two seconds after SIGTERM before SIGKILL. Closing the projects last -- after
unloading local models -- meant most quits never reached it, and every project kept a WAL to replay at the next
open. By the time the slow steps run, every project is closed and its WAL is gone.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_projects_are_closed_before_local_models_are_unloaded(test_package, monkeypatch):
    from fichero_server.api import main as api_main
    from fichero_server.db.manager import db_manager

    seen: dict[str, object] = {}

    async def unload_models():
        seen["open"] = list(db_manager.open_library_paths())
        seen.setdefault("wal", Path(test_package, "fichero.duckdb.wal").exists())  # the quit's call, not teardown's

    monkeypatch.setattr(api_main, "shutdown_managed_local_inference_services", unload_models)
    with TestClient(api_main.app):
        db = db_manager.get_database(test_package)
        db.execute("CREATE TABLE IF NOT EXISTS quit_probe (x INTEGER)")
        db.execute("INSERT INTO quit_probe VALUES (1)")
    assert seen == {"open": [], "wal": False}, seen


def test_the_app_database_is_checkpointed_with_the_projects(tmp_path, monkeypatch):
    from fichero_server.api import main as api_main
    from fichero_server.db import app as app_db_module

    app_db = app_db_module.AppDatabase(tmp_path / "app.duckdb")
    monkeypatch.setattr(app_db_module, "_app_db", app_db)
    app_db.conn.execute("CREATE TABLE IF NOT EXISTS quit_probe (x INTEGER)")
    app_db.conn.execute("INSERT INTO quit_probe VALUES (1)")
    assert Path(f"{tmp_path / 'app.duckdb'}.wal").exists()

    seen = {}

    async def unload_models():
        seen["wal"] = Path(f"{tmp_path / 'app.duckdb'}.wal").exists()

    monkeypatch.setattr(api_main, "shutdown_managed_local_inference_services", unload_models)
    with TestClient(api_main.app):
        pass
    assert seen == {"wal": False}
    assert app_db.conn.execute("SELECT count(*) FROM quit_probe").fetchone()[0] == 1, "still usable after quit"


def test_idle_projects_are_checkpointed_before_runs_in_flight_are_stopped(test_package, monkeypatch):
    """Stopping runs can outlast the app's two seconds; every idle project's WAL is gone before that starts."""
    from fichero_server.api import main as api_main
    from fichero_server.db import manager as manager_module
    from fichero_server.db.manager import db_manager

    seen = {}
    real_stop = manager_module._stop_jobs

    def slow_stop(package_path):
        seen.setdefault("wal", Path(test_package, "fichero.duckdb.wal").exists())  # the quit's call, not teardown's
        return real_stop(package_path)

    monkeypatch.setattr(manager_module, "_stop_jobs", slow_stop)
    with TestClient(api_main.app):
        db = db_manager.get_database(test_package)
        db.execute("CREATE TABLE IF NOT EXISTS quit_probe (x INTEGER)")
        db.execute("INSERT INTO quit_probe VALUES (1)")
    assert seen.get("wal") is False, seen
