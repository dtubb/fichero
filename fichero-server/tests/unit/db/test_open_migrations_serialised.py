"""Opens of one library in one process run their migrations one at a time (#6220).

The M4 run (2026-10-26) logged `migrate_document_table` rolled back on a catalog write-write
conflict on idx_documents_parent_id: two embedding threads each opened the library's worker
Database at once, and both migration suites created the index in the same moment.
"""

from __future__ import annotations

import threading

from fichero_server.db import Database


def _open_together(path, n: int = 4) -> list[Database]:
    barrier = threading.Barrier(n)
    opened: list[Database] = []
    errors: list[BaseException] = []

    def _open() -> None:
        barrier.wait()
        try:
            opened.append(Database(path))
        except BaseException as exc:  # noqa: BLE001 - the test reports it
            errors.append(exc)

    threads = [threading.Thread(target=_open) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not errors, errors
    return opened


def test_opens_at_once_on_a_fresh_library_record_no_migration_failure(tmp_path):
    path = tmp_path / "fichero.duckdb"
    # A fresh library: its first open makes the documents table after the document migration
    # ran, so the parent_id index is first made by the NEXT open: here, four at once.
    Database(path)
    for db in _open_together(path):
        assert db.migration_failures == [], [f.message for f in db.migration_failures]


def test_two_embed_threads_share_one_worker_database(tmp_path):
    db = Database(tmp_path / "fichero.duckdb")
    barrier = threading.Barrier(4)
    workers: list[Database] = []

    def _take() -> None:
        barrier.wait()
        workers.append(db._embed_worker())

    threads = [threading.Thread(target=_take) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert len({id(w) for w in workers}) == 1


def test_an_open_inside_an_open_of_the_same_library_does_not_hang(tmp_path):
    # Review LOW on ce8b274c0: the lock was a plain Lock, so an open-time step that opened the same library again on its
    # own thread would wait on itself forever. Re-entry on one thread goes through; other threads still wait.
    from fichero_server.db import _open_migrations_lock

    path = tmp_path / "lib.duckdb"
    Database(path)
    done = threading.Event()

    def _nested() -> None:
        with _open_migrations_lock(path):
            Database(path)
        done.set()

    threading.Thread(target=_nested, daemon=True).start()
    assert done.wait(30), "an open inside an open of the same library waited on itself"
