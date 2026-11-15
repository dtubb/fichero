"""The shared DuckDB connection is used only under `Database._lock` (#6601).

`Database._execute(sql)` with no `fetch=` hands back the raw cursor, which IS the shared connection, so
`db._execute(sql).fetchall()` fetched after the lock was released and, against another thread's statement, raised
`ResourceInUseException: connection is busy with another call`. 32 requests failed with HTTP 500 that way.
"""

from __future__ import annotations

import ast
import threading
import time
from pathlib import Path

import fichero_server
from _scan_files import scan_rglob
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


class _RefusingConnection:
    """The connection as newer DuckDB behaves: a call made while another thread is inside one is REFUSED
    (`ResourceInUseException: connection is busy with another call`), not queued. The installed DuckDB
    serialises instead, so the refusal is modelled here and each call is held open long enough to overlap."""

    def __init__(self, conn):
        self._conn = conn
        self._guard = threading.Lock()

    def _call(self, name, *args, **kwargs):
        if not self._guard.acquire(blocking=False):
            raise RuntimeError("Resource In Use Error: connection is busy with another call")
        try:
            time.sleep(0.001)
            result = getattr(self._conn, name)(*args, **kwargs)
            return self if result is self._conn else result
        finally:
            self._guard.release()

    def __getattr__(self, name):
        target = getattr(self._conn, name)
        if name in {"execute", "executemany", "fetchall", "fetchone", "fetchmany", "cursor"}:
            return lambda *a, **k: self._call(name, *a, **k)
        return target


def test_two_threads_one_connection_never_collide(db):
    db._ensure_table(KnowledgeClaim)
    real = db.conn
    db.conn = _RefusingConnection(real)
    errors: list[BaseException] = []
    stop = threading.Event()

    def reader():
        try:
            while not stop.is_set():
                db.execute_fetchall("SELECT 1")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
            stop.set()

    def culprit():
        try:
            for _ in range(100):
                if stop.is_set():
                    return
                db.keyword_artifact_rows()
                db.knowledge_claim_entity_id_values()
                db.entity_document_link_rows("e", 5)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            stop.set()

    threads = [threading.Thread(target=reader), threading.Thread(target=culprit)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
    finally:
        db.conn = real
    assert not errors, errors[0]
