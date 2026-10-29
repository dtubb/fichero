"""#6238 residue: after Database.close(), a statement through a helper (execute_fetchall and the rest) took DuckDB's
"connection closed" for an invalidated connection and opened a new one, so a closed library came back open behind
whoever still held it (an embed carrying on past the close). A closed Database stays closed and says so."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import duckdb
import pytest

from fichero_server.db import Database


def test_a_statement_after_close_is_refused_and_opens_nothing(tmp_path):
    db = Database(tmp_path / "lib" / "fichero.duckdb")
    db.close()
    closed_conn = db.conn
    with pytest.raises(duckdb.ConnectionException, match="closed"):
        db.execute_fetchall("SELECT 1")
    assert db.conn is closed_conn, "a closed library opened a new connection"


@pytest.mark.parametrize("which", ["batch", "schedule", "file_trigger"])
def test_a_library_closed_inside_a_transaction_opens_no_second_database(tmp_path, which):
    """A store's delete runs several statements in one transaction. The library closing between them must refuse the
    next statement, not look `db` up again and write through a second Database outside the transaction."""
    from fichero_server.db.manager import db_manager
    from fichero_server.execution.batch import BatchManager
    from fichero_server.workflows.file_watcher import FileWatcherManager
    from fichero_server.workflows.scheduler import WorkflowScheduler

    library = tmp_path / "lib.fichero"
    db_manager.get_database(library, create=True)
    path = str(library / "fichero.duckdb")
    db = db_manager.get_database(library)
    make, remove = {
        "batch": (lambda: BatchManager(path), lambda s: s.delete_batch("b")),
        "schedule": (lambda: WorkflowScheduler(path, MagicMock()), lambda s: s.delete_schedule("s")),
        "file_trigger": (lambda: FileWatcherManager(path, MagicMock()), lambda s: s.delete_trigger("t")),
    }[which]
    store = make()
    real_query = db.query

    def query_then_close(*args, **kwargs):
        rows = real_query(*args, **kwargs)
        db_manager.close_database(library)
        return rows

    db.query = query_then_close
    try:
        with pytest.raises(duckdb.Error):
            asyncio.run(remove(store))
        assert not db_manager._databases, "a close inside the transaction let the store open a second Database"
    finally:
        db_manager.close_all()
