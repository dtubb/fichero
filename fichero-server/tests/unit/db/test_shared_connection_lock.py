"""The shared DuckDB connection is used only under `Database._lock` (#6601).

`Database._execute(sql)` with no `fetch=` hands back the raw cursor, which IS the shared connection, so
`db._execute(sql).fetchall()` fetched after the lock was released and, against another thread's statement, raised
`ResourceInUseException: connection is busy with another call`. 32 requests failed with HTTP 500 that way.
"""

from __future__ import annotations

import ast
from pathlib import Path

import fichero_server
from _scan_files import scan_rglob
from fichero_server.db import Database
from fichero_server.models.knowledge import KnowledgeClaim

_SRC = Path(fichero_server.__file__).parent
_CURSOR_METHODS = {"fetchall", "fetchone", "fetchmany", "fetchnumpy", "fetchdf", "df", "arrow", "pl", "fetch_arrow_table"}


def _is_raw_db_call(node: ast.AST) -> bool:
    """`self._execute(...)` / `db.execute(...)` with no `fetch=`: a locked helper that returns the cursor."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return False
    if node.func.attr not in {"_execute", "execute"} or any(k.arg == "fetch" for k in node.keywords):
        return False
    owner = node.func.value
    name = owner.attr if isinstance(owner, ast.Attribute) else getattr(owner, "id", "")
    return name in {"self", "db", "_db", "database"}


def test_no_fetch_off_the_cursor_a_locked_helper_returned():
    offenders = []
    for path in sorted(scan_rglob(_SRC, "*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            chained = isinstance(node.func, ast.Attribute) and node.func.attr in _CURSOR_METHODS and _is_raw_db_call(node.func.value)
            wrapped = getattr(node.func, "id", "") == "fetch_one" and bool(node.args) and _is_raw_db_call(node.args[0])
            if chained or wrapped:
                offenders.append(f"{path.relative_to(_SRC)}:{node.lineno}")
    assert not offenders, (
        "fetched after the lock was released; pass fetch='all'/'one' to the helper or use "
        f"execute_fetchall/execute_fetchone: {offenders}"
    )


class _LockCheckingConnection:
    """The shared connection as newer DuckDB treats it: a call made while another thread is inside one is REFUSED
    (`ResourceInUseException: connection is busy with another call`), not queued. A thread that holds `Database._lock`
    cannot be overlapped, so the rule is checked directly and deterministically: every statement and every fetch on the
    connection must happen with the calling thread holding the lock. A fetch made after `_execute` released it fails."""

    def __init__(self, conn, lock):
        self._conn = conn
        self._lock = lock
        self.unlocked: list[str] = []

    def __getattr__(self, name):
        target = getattr(self._conn, name)
        if name not in {"execute", "executemany", "fetchall", "fetchone", "fetchmany"}:
            return target

        def call(*args, **kwargs):
            if not self._lock._is_owned():
                self.unlocked.append(name)
            result = target(*args, **kwargs)
            return self if result is self._conn else result

        return call


def test_every_statement_and_fetch_on_the_shared_connection_holds_the_lock(tmp_path):
    """A private Database on a file of its own: no db_manager entry, no app-DB singleton, no env, so nothing outlives it."""
    db = Database(path=tmp_path / "lock.duckdb")
    try:
        db._ensure_table(KnowledgeClaim)
        real = db.conn
        spy = _LockCheckingConnection(real, db._lock)
        db.conn = spy
        try:
            db.execute_fetchall("SELECT 1")
            db.keyword_artifact_rows()
            db.knowledge_claim_entity_id_values()
            db.knowledge_claim_entity_id_values(source_document_id="d", entity_id="e")
            db.entity_document_link_rows("e", 5)
        finally:
            db.conn = real
        assert not spy.unlocked, f"used the shared connection outside Database._lock (#6601): {spy.unlocked}"
    finally:
        db.close()
