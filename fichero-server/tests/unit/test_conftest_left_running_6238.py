"""The session's end names every Database a test left open (#6238): a wide run deadlocked on the Databases and lane
threads tests made and never closed. A closed one is not listed."""
from __future__ import annotations

from fichero_server.db import Database


def test_a_database_left_open_is_named_by_the_test_that_opened_it_and_a_closed_one_is_not(request, tmp_path):
    conftest = next(p for p in request.config.pluginmanager.get_plugins()
                    if str(getattr(p, "__file__", "")).endswith("fichero-server/tests/conftest.py"))
    db = Database(tmp_path / "left.duckdb")
    try:
        assert f"{request.node.nodeid}: {db.path}" in conftest._left_running()[0]
    finally:
        db.close()
    assert not [line for line in conftest._left_running()[0] if line.startswith(request.node.nodeid)]
