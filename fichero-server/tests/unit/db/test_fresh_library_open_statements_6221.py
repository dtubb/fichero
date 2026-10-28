"""A fresh library's open does not read back the tables it just created, and seeds its built-ins in batches (#6221).
WHY: verify-all 2026-10-26: the query ratchet's POST /api/library went 197 -> 624. Every table paid CREATE plus two
PRAGMA table_info reads (one to add missing columns, one to widen INT32 columns) even when the CREATE had just made it
from the model, and every built-in link type, reading kind, level, prototype and node class was two statements a row."""
from __future__ import annotations

import collections

from fichero_server.core import duckdb_session
from fichero_server.db import Database


def _statements_while(monkeypatch, fn) -> collections.Counter:
    seen: collections.Counter = collections.Counter()
    orig = duckdb_session._QueryCountingConnection.execute

    def execute(self, *args, **kwargs):
        seen[" ".join(str(args[0]).split())[:40] if args else "?"] += 1
        return orig(self, *args, **kwargs)

    monkeypatch.setenv("FICHERO_PERF_RATCHET", "1")  # the counting wrapper is on, as under the ratchet
    monkeypatch.setattr(duckdb_session._QueryCountingConnection, "execute", execute)
    fn()
    return seen


def test_a_fresh_library_reads_back_none_of_the_tables_it_created(tmp_path, monkeypatch):
    seen = _statements_while(monkeypatch, lambda: Database(tmp_path / "fresh.duckdb"))
    assert sum(seen.values()) > 50, "the counting wrapper saw nothing: this test measures nothing"
    pragmas = sum(n for sql, n in seen.items() if sql.startswith("PRAGMA table_info"))
    assert pragmas <= 10, f"{pragmas} column reads on a library whose tables were all just created"
    link_type_writes = sum(n for sql, n in seen.items() if '"librarylinktypes"' in sql)
    assert 1 <= link_type_writes <= 2, f"{link_type_writes} statements seeding the built-in link types"


def test_a_library_opened_again_still_reconciles_its_columns(tmp_path, monkeypatch):
    Database(tmp_path / "lib.duckdb")
    seen = _statements_while(monkeypatch, lambda: Database(tmp_path / "lib.duckdb"))
    assert sum(n for sql, n in seen.items() if sql.startswith("PRAGMA table_info")) > 50  # one read a table, not two
