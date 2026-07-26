"""DatabaseManager single-connection-per-package model (#2508).

A DuckDB Connection is not safe for *concurrent* use but is safe serialized by
a lock. DatabaseManager keeps exactly ONE Database (one connection, one RLock)
per package, shared across every thread; Database's per-method ``with self._lock``
then serializes all access globally, making read-after-write deterministic across
threads. (Previously each (package, thread) got its own connection — the locking
never serialized cross-thread and correctness rode on MVCC, the root of #2430 /
#2462.)
"""

from __future__ import annotations

import os
import threading

import pytest

os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")

from fichero.db.manager import DatabaseManager  # noqa: E402
from fichero.models import Document, DocType  # noqa: E402


def test_shared_connection_across_threads(tmp_path):
    """All threads asking for the same package get the SAME Database object and
    the SAME DuckDB connection; asking twice on one thread is also cached. (#2508)"""
    pkg = tmp_path / "lib.fichero"
    pkg.mkdir()
    mgr = DatabaseManager()
    try:
        main_db = mgr.get_database(pkg)
        assert mgr.get_database(pkg) is main_db  # cached

        worker_holder: dict[str, object] = {}

        def worker() -> None:
            worker_holder["db"] = mgr.get_database(pkg)

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        # The worker thread gets the very same shared instance + connection.
        assert worker_holder["db"] is main_db
        assert worker_holder["db"].conn is main_db.conn
    finally:
        mgr.close_all()


def test_active_count_counts_packages(tmp_path):
    """active_count reflects distinct packages — a 2-thread, 1-library setup
    reports 1 (now trivially, since there is one shared connection). (#2508)"""
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


def test_initialization_failure_is_loud_and_does_not_leave_a_cached_handle(
    tmp_path, monkeypatch
):
    """A failed default-workflow seed must not leave a partial library open."""
    # Must be the GLOBAL package: default workflows only seed there (#4102),
    # so a plain library never reaches the seeder this test is failing.
    pkg = tmp_path / "global.fichero"
    pkg.mkdir()
    mgr = DatabaseManager()
    monkeypatch.delenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", raising=False)

    def fail_seed(_db):
        raise RuntimeError("seed failed")

    monkeypatch.setattr(
        "fichero.workflows.default_workflows.seed_default_workflows", fail_seed
    )
    try:
        with pytest.raises(RuntimeError, match="Failed to initialize library database") as exc:
            mgr.get_database(pkg)

        assert isinstance(exc.value.__cause__, RuntimeError)
        assert str(exc.value.__cause__) == "seed failed"
        assert mgr.active_count == 0
        assert mgr.open_library_paths() == []
    finally:
        mgr.close_all()


# NOTE (#2514): the per-package DBWriter queue was removed — the single shared
# connection lock (#2508) already serializes every write, so the queue was
# redundant. The former test_get_db_writer_is_shared_per_package and
# test_db_writer_persists_through_the_pool tested that removed API. Direct
# db.save persistence is covered by test_cross_thread_writes_are_immediately_visible
# below, and the extract_all/import_artifacts direct-save paths by
# test_workflow_artifact_direct_save.py.


def test_close_current_thread_is_noop_and_keeps_shared_connection(tmp_path):
    """close_current_thread is a NO-OP under the shared-connection model (#2508):
    a worker thread must NOT close the connection the event loop + every other
    thread share. The shared Database survives and stays usable after the call."""
    pkg = tmp_path / "lib.fichero"
    pkg.mkdir()
    mgr = DatabaseManager()
    try:
        db = mgr.get_database(pkg)
        assert mgr.active_count == 1

        # Simulate a finished workflow worker calling its finally hook.
        mgr.close_current_thread()

        # The shared connection is untouched and still works.
        assert mgr.active_count == 1
        assert mgr.get_database(pkg) is db
        db.save(Document(id="still-alive", name="ok", doc_type=DocType.file))
        names = {d.name for d in db.query(Document)}
        assert "ok" in names
    finally:
        mgr.close_all()


def test_cross_thread_writes_are_immediately_visible(tmp_path):
    """A row written on a worker thread is visible to the main thread
    DETERMINISTICALLY — they share one connection, so there is no MVCC
    snapshot lag (the #2430/#2462 class). (#2508)"""
    pkg = tmp_path / "lib.fichero"
    pkg.mkdir()
    mgr = DatabaseManager()
    try:
        main_db = mgr.get_database(pkg)

        def worker() -> None:
            mgr.get_database(pkg).save(
                Document(id="from-worker", name="from-worker", doc_type=DocType.file)
            )

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        # Immediately readable on the main thread by id (same connection).
        assert main_db.get(Document, "from-worker") is not None
        names = {d.name for d in main_db.query(Document)}
        assert "from-worker" in names
    finally:
        mgr.close_all()


def test_default_workflows_seed_only_into_the_global_library(tmp_path, monkeypatch):
    """#4102: presets are app-level. A normal library must not grow its own
    copy (which put a duplicate "Default Workflows" folder under every library
    in the sidebar); the global library still gets them."""
    from fichero.models import Workflow

    monkeypatch.delenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", raising=False)
    mgr = DatabaseManager()
    try:
        plain = tmp_path / "Marshall.fichero"
        plain.mkdir()
        assert list(mgr.get_database(plain).all(Workflow)) == []

        glob = tmp_path / "global.fichero"
        glob.mkdir()
        assert len(list(mgr.get_database(glob).all(Workflow))) > 0
    finally:
        mgr.close_all()


def test_reopening_a_seeded_library_prunes_the_presets(tmp_path, monkeypatch):
    """A library seeded before the global-only rule heals on next open: the
    shipped presets and their locked container go, the user's own stay."""
    from fichero.models import Document, Workflow
    from fichero.workflows.default_workflows import seed_default_workflows

    monkeypatch.delenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", raising=False)
    pkg = tmp_path / "Marshall.fichero"
    pkg.mkdir()

    mgr = DatabaseManager()
    try:
        db = mgr.get_database(pkg)
        seed_default_workflows(db)  # simulate the pre-#4102 per-library seed
        db.save(Workflow(name="My Own Pipeline", is_template=False))
        assert len(list(db.all(Workflow))) > 1
    finally:
        mgr.close_all()

    mgr2 = DatabaseManager()
    try:
        db2 = mgr2.get_database(pkg)
        names = [w.name for w in db2.all(Workflow)]
        assert names == ["My Own Pipeline"]
        containers = db2.query(Document, node_kind="workflow_container")
        assert list(containers) == []
    finally:
        mgr2.close_all()
