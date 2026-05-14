"""DatabaseManager thread-scoped connection pooling.

Workflow execution runs on a dedicated worker thread (#1000). A DuckDB
Connection is not thread-safe, so DatabaseManager hands each
(package, thread) its own connection to the same file.
"""

from __future__ import annotations

import os
import threading

os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")

from fichero.db_manager import DatabaseManager  # noqa: E402
from fichero.models import Document, DocType  # noqa: E402


def test_distinct_connection_per_thread(tmp_path):
    """Two threads asking for the same package get different Database
    objects (different DuckDB connections); the same thread asking
    twice gets the cached instance back. (#1000)"""
    pkg = tmp_path / "lib.fichero"
    pkg.mkdir()
    mgr = DatabaseManager()
    try:
        main_db = mgr.get_database(pkg)
        assert mgr.get_database(pkg) is main_db  # same thread → cached

        worker_holder: dict[str, object] = {}

        def worker() -> None:
            worker_holder["db"] = mgr.get_database(pkg)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        assert worker_holder["db"] is not main_db  # worker thread → its own
    finally:
        mgr.close_all()


def test_active_count_counts_packages_not_connections(tmp_path):
    """active_count reflects distinct packages, not the raw per-thread
    connection count — so a 2-thread, 1-library setup reports 1. (#1000)"""
    pkg = tmp_path / "lib.fichero"
    pkg.mkdir()
    mgr = DatabaseManager()
    try:
        mgr.get_database(pkg)

        def worker() -> None:
            mgr.get_database(pkg)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        assert mgr.active_count == 1
    finally:
        mgr.close_all()


def test_cross_thread_writes_are_visible(tmp_path):
    """A row written through the worker thread's connection is visible
    to the main thread's connection — DuckDB serialises writes across
    in-process connections. (#1000)"""
    pkg = tmp_path / "lib.fichero"
    pkg.mkdir()
    mgr = DatabaseManager()
    try:
        main_db = mgr.get_database(pkg)

        def worker() -> None:
            worker_db = mgr.get_database(pkg)
            worker_db.save(Document(name="from-worker", doc_type=DocType.file))

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        names = {d.name for d in main_db.query(Document)}
        assert "from-worker" in names
    finally:
        mgr.close_all()
