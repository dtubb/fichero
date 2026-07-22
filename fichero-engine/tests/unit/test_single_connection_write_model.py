"""
#2508 — write-model proof harness (Phase 0).

The engine currently hands EACH THREAD its own Database + DuckDB connection +
RLock (``DatabaseManager.get_database`` keys its pool by
``(package, threading.get_ident())`` — db_manager.py). So the per-method
``with self._lock`` serialization is silently per-thread and never serializes
across threads; cross-thread correctness rests entirely on DuckDB MVCC. That is
the systemic root of #2430 (per-page artifact loss) and #2462 (GET
/documents/{id} 404s while /children 200s): a row committed on a workflow
pool-thread connection can be transiently invisible on the event-loop
connection's snapshot.

Phase 2 of #2508 collapses this to ONE connection + ONE lock per package. After
that flip the *existing* locks become globally effective and read-after-write is
deterministic — phantom-404 / transient-None become structurally impossible.

This module is the RED→GREEN proof:
  * ``test_get_database_returns_same_instance_across_threads`` is xfail(strict)
    TODAY (per-thread instancing → distinct objects) and will XPASS the moment
    Phase 2 lands — at which point the xfail marker is removed so it guards the
    invariant permanently.
  * the concurrent write/read soak asserts robustness (no lost writes, no
    crashes) under both models.

Real threads + a real temp DuckDB library throughout — no DB mocks (a mock can't
exhibit the connection-topology bug; memory: prefer-raise / test the real path).
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest


@pytest.fixture
def temp_library(tmp_path, monkeypatch):
    """A real .fichero package backed by a real DuckDB file.

    Yields ``(library_path, db_manager)`` and tears down every connection the
    test opened across all threads so connections don't leak between tests.
    """
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    from fichero.db.manager import db_manager

    lib = tmp_path / "WriteModel.fichero"
    lib.mkdir(parents=True, exist_ok=True)
    yield str(lib), db_manager
    try:
        db_manager.close_all()
    except Exception:
        pass


def _make_doc(doc_id: str):
    from fichero.models import Document, DocType, Status

    now = datetime.now()
    return Document(
        id=doc_id,
        name=f"doc {doc_id}",
        doc_type=DocType.file,
        path=None,
        status=Status.pending,
        metadata={},
        created_at=now,
        updated_at=now,
    )


def test_get_database_returns_same_instance_across_threads(temp_library):
    """The single-connection invariant: one Database (and one DuckDB conn) per
    package, shared across every thread. RED today (per-thread), GREEN at Phase 2.
    """
    library_path, db_manager = temp_library

    main = db_manager.get_database(library_path)
    results: dict[int, object] = {}

    def worker():
        results[threading.get_ident()] = db_manager.get_database(library_path)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results, "no worker threads ran"
    for db in results.values():
        # Same Database object AND same underlying DuckDB connection.
        assert db is main, "get_database must return the same instance on every thread"
        assert db.conn is main.conn, "all threads must share one DuckDB connection"


def test_concurrent_writes_have_no_lost_rows(temp_library):
    """Robustness soak (green under both models): N threads each write a unique
    document; after all commit, every row must be present. Guards against lost
    writes / crashes under concurrent access.
    """
    library_path, db_manager = temp_library
    from fichero.models import Document

    n = 60
    errors: list[str] = []

    def worker(i: int):
        try:
            db = db_manager.get_database(library_path)
            db.save(_make_doc(f"d-{i}"))
            # Read-back on this thread's own connection must always succeed.
            if db.get(Document, f"d-{i}") is None:
                errors.append(f"same-connection read-back lost d-{i}")
        except Exception as exc:  # noqa: BLE001 - surface any concurrency error
            errors.append(f"d-{i}: {exc!r}")

    with ThreadPoolExecutor(max_workers=12) as ex:
        list(ex.map(worker, range(n)))

    assert not errors, f"concurrent write/read errors: {errors[:5]} (+{max(0, len(errors) - 5)} more)"

    # After every writer has committed + joined, a fresh read sees all rows.
    verify = db_manager.get_database(library_path)
    present = {d.id for d in verify.all(Document)}
    missing = [f"d-{i}" for i in range(n) if f"d-{i}" not in present]
    assert not missing, f"committed rows missing on fresh read: {missing[:5]}"


def test_cross_thread_read_after_write_is_immediately_visible_under_load(temp_library):
    """THE #2462/#2430 guarantee, deterministic: a row written on one thread is
    visible to a DIFFERENT thread the instant the write returns — because they
    share one connection. Looped 100x with a handoff so a regression to
    per-thread connections (MVCC snapshot lag) would surface as misses.
    """
    library_path, db_manager = temp_library
    import queue as _queue

    from fichero.models import Document

    handoff: _queue.Queue = _queue.Queue()
    misses: list[str] = []
    errors: list[str] = []
    rounds = 100

    def writer():
        try:
            db = db_manager.get_database(library_path)
            for i in range(rounds):
                db.save(_make_doc(f"x-{i}"))
                handoff.put(f"x-{i}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"writer: {exc!r}")
        finally:
            handoff.put(None)  # sentinel

    def reader():
        db = db_manager.get_database(library_path)
        while True:
            try:
                doc_id = handoff.get(timeout=10)
            except Exception:  # noqa: BLE001
                errors.append("reader: handoff timed out")
                return
            if doc_id is None:
                return
            try:
                if db.get(Document, doc_id) is None:
                    misses.append(doc_id)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"reader {doc_id}: {exc!r}")

    wt = threading.Thread(target=writer)
    rt = threading.Thread(target=reader)
    rt.start()
    wt.start()
    wt.join(timeout=30)
    rt.join(timeout=30)

    assert not errors, f"errors: {errors[:5]}"
    assert not misses, (
        f"{len(misses)}/{rounds} cross-thread read-after-write MISSES — the "
        f"#2462/#2430 phantom miss is back: {misses[:5]}"
    )


def test_no_deadlock_under_concurrent_mixed_ops(temp_library):
    """One RLock per package serializes save/get/query/all across threads.
    16 threads hammering mixed ops must all finish (no deadlock / lock
    starvation) and every row must land — re-entrant RLock, no cross-package
    nesting, so no lock-order cycle."""
    library_path, db_manager = temp_library
    from fichero.models import Document

    errors: list[str] = []
    n_threads, per = 16, 25

    def worker(t: int):
        try:
            db = db_manager.get_database(library_path)
            for i in range(per):
                db.save(_make_doc(f"m-{t}-{i}"))
                db.get(Document, f"m-{t}-{i}")
                _ = list(db.query(Document))
                _ = list(db.all(Document))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"t{t}: {exc!r}")

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not any(t.is_alive() for t in threads), "deadlock/hang: threads did not finish in 60s"
    assert not errors, f"concurrent mixed-op errors: {errors[:5]}"

    present = {d.id for d in db_manager.get_database(library_path).all(Document)}
    expected = {f"m-{t}-{i}" for t in range(n_threads) for i in range(per)}
    missing = expected - present
    assert not missing, f"rows lost under concurrent mixed ops: {list(missing)[:5]}"
