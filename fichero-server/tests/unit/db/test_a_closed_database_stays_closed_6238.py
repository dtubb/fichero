"""#6238 residue: after Database.close(), a statement through a helper (execute_fetchall and the rest) took DuckDB's
"connection closed" for an invalidated connection and opened a new one, so a closed library came back open behind
whoever still held it (an embed carrying on past the close). A closed Database stays closed and says so."""

from __future__ import annotations

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
