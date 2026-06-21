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
    from fichero.db_manager import db_manager

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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "#2508 Phase 0: get_database is keyed by thread_ident today, so each "
        "thread gets a distinct Database + connection. Phase 2 collapses to one "
        "shared instance per package; when it lands this XPASSes and the xfail "
        "marker is removed to guard the single-connection invariant permanently."
    ),
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
