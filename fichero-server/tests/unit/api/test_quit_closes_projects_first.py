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
        seen["wal"] = Path(test_package, "fichero.duckdb.wal").exists()

    monkeypatch.setattr(api_main, "shutdown_managed_local_inference_services", unload_models)
    with TestClient(api_main.app):
        db = db_manager.get_database(test_package)
        db.execute("CREATE TABLE IF NOT EXISTS quit_probe (x INTEGER)")
        db.execute("INSERT INTO quit_probe VALUES (1)")
    assert seen == {"open": [], "wal": False}, seen
