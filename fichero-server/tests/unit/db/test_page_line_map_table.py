"""The Reader's line map has a DECLARED table (3c part c; the lead's review of c344f5b59).

`pagelinemaps` first appeared the first time a page-text refresh wrote a row. A table that appears
lazily bypasses the schema and migration path that every walker assumes -- the fresh-open guard,
export and snapshot walks. So it is registered in `Database._all_schema_models`, and an existing
library gains it when it OPENS, before anything renders or refreshes.
"""

from __future__ import annotations

import duckdb

from fichero_server.db import Database
from fichero_server.models import PageLineMap


def _tables(conn) -> set[str]:
    return {row[0] for row in conn.execute("SELECT table_name FROM duckdb_tables()").fetchall()}


def test_the_line_map_is_a_declared_table(tmp_path):
    db = Database(tmp_path / "fresh.duckdb")
    try:
        assert PageLineMap in db._all_schema_models()
        assert db._table_name(PageLineMap) in _tables(db.conn)
    finally:
        db.close()


def test_a_library_from_before_gains_the_table_when_it_opens_not_when_a_page_renders(tmp_path):
    path = tmp_path / "old.duckdb"
    Database(path).close()
    conn = duckdb.connect(str(path))
    conn.execute("DROP TABLE IF EXISTS pagelinemaps")      # the library as it was before the map
    assert "pagelinemaps" not in _tables(conn)
    conn.close()

    reopened = Database(path)
    try:
        assert "pagelinemaps" in _tables(reopened.conn)
        # Arrived through the open, with nothing written: no render, no refresh made it.
        assert reopened.conn.execute("SELECT count(*) FROM pagelinemaps").fetchone()[0] == 0
    finally:
        reopened.close()
