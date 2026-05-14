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


def test_get_db_writer_is_per_thread(tmp_path):
    """get_db_writer hands each thread its own DBWriter (bound to that
    thread's connection); the same thread asking twice gets the cached
    one. (#1000 Phase 2)"""
    pkg = tmp_path / "lib.fichero"
    pkg.mkdir()
    mgr = DatabaseManager()
    try:
        main_writer = mgr.get_db_writer(pkg)
        assert mgr.get_db_writer(pkg) is main_writer  # cached per thread

        worker_holder: dict[str, object] = {}

        def worker() -> None:
            worker_holder["writer"] = mgr.get_db_writer(pkg)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        assert worker_holder["writer"] is not main_writer
    finally:
        mgr.close_all()


def test_db_writer_persists_through_the_pool(tmp_path):
    """A row saved via the manager's DBWriter lands in the package's
    database. (#1000 Phase 2)"""
    pkg = tmp_path / "lib.fichero"
    pkg.mkdir()
    mgr = DatabaseManager()
    try:
        writer = mgr.get_db_writer(pkg)
        writer.save(Document(name="via-writer", doc_type=DocType.file))
        writer.flush()
        names = {d.name for d in mgr.get_database(pkg).query(Document)}
        assert "via-writer" in names
    finally:
        mgr.close_all()


def test_close_current_thread_releases_this_threads_resources(tmp_path):
    """close_current_thread drops this thread's connection + writer but
    leaves other threads' untouched — so a finished workflow worker
    doesn't leak. (#1000)"""
    pkg = tmp_path / "lib.fichero"
    pkg.mkdir()
    mgr = DatabaseManager()
    try:
        # A connection owned by some *other* thread must survive.
        survivor: dict[str, object] = {}

        def other_thread() -> None:
            survivor["db"] = mgr.get_database(pkg)

        t = threading.Thread(target=other_thread)
        t.start()
        t.join()

        # This thread's resources, then release them.
        mgr.get_database(pkg)
        mgr.get_db_writer(pkg)
        assert mgr.active_count == 1

        mgr.close_current_thread()

        # This thread's entries are gone; the other thread's remain.
        import threading as _t

        tid = _t.get_ident()
        assert not any(k[1] == tid for k in mgr._databases)
        assert not any(k[1] == tid for k in mgr._db_writers)
        assert mgr.active_count == 1  # the other thread's connection survived
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
