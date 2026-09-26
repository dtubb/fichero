"""A snapshot of a library that is OPEN, which is how production always is (#5070).

**Why this file exists, and why the existing suite missed it.** Every snapshot
test in `test_storage_snapshots.py` closes the database before snapshotting —
`_create_library_with_document` ends with `db.conn.close()`. That is a reasonable
fixture habit and it happens to avoid the exact condition production is in: a
library is open read-write whenever anyone is using the app. So the suite was
green while snapshots did not happen.

Two defects were behind it, both measured rather than reasoned:

1. `snapshot_library` exported Parquet by opening the LIVE file read-only, and
   DuckDB refuses a read-only connection to a file already open read-write.
   `_quiesce_library_database(close=False)` checkpoints the managed connection
   but does not release it. Every snapshot from inside a request failed.
2. Worse: the file copy was taken without flushing connections the manager does
   not own, so the copy could contain **no tables at all** — a valid-looking,
   entirely empty database, with a non-zero size and a snapshot record pointing
   at it. Measured: copy without CHECKPOINT gave `NO TABLES`; copy after
   CHECKPOINT gave the full schema.

And `auto_snapshot_before_risky_operation` swallowed both, returning `None` that
no caller checked — including a recursive hard delete. A safety net nobody
depends on cannot be observed to be missing.

These tests hold the library open the way production holds it. Without them this
returns the moment someone re-introduces a second connection.
"""

from __future__ import annotations

import pathlib

import pytest

from fichero_server.core.duckdb_session import connect_utc
from fichero_server.db import Database, storage_snapshots
from fichero_server.db.storage import StorageSettings
from fichero_server.db.storage_snapshots import SnapshotRefused
from fichero_server.models import Document, KnownLibrary

pytestmark = pytest.mark.source_model


@pytest.fixture
def library(tmp_path, monkeypatch):
    """A registered library with an OPEN read-write connection, left open."""
    monkeypatch.setattr(
        storage_snapshots, "settings", StorageSettings(base_path=tmp_path / "state")
    )
    path = tmp_path / "Open.fichero"
    path.mkdir()

    registry = Database(storage_snapshots.settings.global_library_path / "fichero.duckdb")
    try:
        registry.save(KnownLibrary(path=str(path.resolve()), name=path.name))
    finally:
        registry.conn.close()

    db = Database(path / "fichero.duckdb")
    db.save(Document(id="doc-1", name="Held Open", page_content="the original text"))
    db.save(Document(id="doc-2", name="Also Here", page_content="more text"))
    try:
        # DELIBERATELY NOT CLOSED. That is the whole point of this file.
        yield db, path
    finally:
        db.close()


def _tables_in(path: pathlib.Path) -> list[str]:
    conn = connect_utc(str(path), read_only=True)
    try:
        return sorted(row[0] for row in conn.execute("SHOW TABLES").fetchall())
    finally:
        conn.close()


class TestASnapshotOfAnOpenLibrary:
    def test_a_snapshot_can_be_taken_at_all(self, library):
        db, path = library
        # Flushed first, and that is not a formality. In production a route's
        # database comes from `db_manager`, so `_quiesce_library_database`
        # checkpoints it; a `Database` built directly — as here, and as the
        # conversion runner may be handed — is not in the manager's cache, so it
        # has to flush itself. `convert_project` does exactly this before
        # snapshotting, for this reason.
        db.checkpoint()

        snapshot = storage_snapshots.snapshot_library(str(path), reason="held open")

        assert snapshot is not None
        assert snapshot.id
        # And the connection still works afterwards — a snapshot must not cost
        # the caller its database.
        assert db.get(Document, "doc-1") is not None

    def test_the_restore_source_is_a_real_database_not_an_empty_one(self, library):
        """Defect 2, which is the dangerous one: an empty copy looks like a
        snapshot right up until somebody restores it."""
        db, path = library
        db.checkpoint()

        snapshot = storage_snapshots.snapshot_library(str(path), reason="held open")

        restore_source = pathlib.Path(snapshot.snapshot_path) / "duckdb_file" / "fichero.duckdb"
        assert restore_source.is_file()
        tables = _tables_in(restore_source)
        assert tables, "the restore source has NO TABLES — it would restore an empty library"
        assert "documents" in tables

    def test_the_rows_that_were_open_are_in_the_snapshot(self, library):
        """The reason the checkpoint matters. Unflushed writes are not in the
        FILE, and a snapshot copies the file."""
        db, path = library
        db.checkpoint()

        snapshot = storage_snapshots.snapshot_library(str(path), reason="held open")

        restore_source = pathlib.Path(snapshot.snapshot_path) / "duckdb_file" / "fichero.duckdb"
        conn = connect_utc(str(restore_source), read_only=True)
        try:
            ids = sorted(row[0] for row in conn.execute("SELECT id FROM documents").fetchall())
        finally:
            conn.close()
        assert ids == ["doc-1", "doc-2"]

    def test_an_unflushed_copy_is_refused_rather_than_recorded(self, library, monkeypatch):
        """A copy with no tables must not be called a snapshot.

        Simulated by making the copy step produce an empty database, which is
        exactly what an unflushed copy looked like — rather than by relying on
        WAL timing, which would make this test a race.
        """
        db, path = library

        real_copy = storage_snapshots.shutil.copy2

        def empty_copy(src, dst, *a, **k):
            # A valid DuckDB file with nothing in it: non-zero size, no tables.
            connect_utc(str(dst)).close()
            return dst

        monkeypatch.setattr(storage_snapshots.shutil, "copy2", empty_copy)
        with pytest.raises(RuntimeError, match="NO TABLES"):
            storage_snapshots.snapshot_library(str(path), reason="deliberately empty")

        monkeypatch.setattr(storage_snapshots.shutil, "copy2", real_copy)

    def test_the_parquet_sidecar_is_written_too(self, library):
        """The export reads the COPY now, so it works while the library is open.
        It is a diagnostic sidecar rather than the restore source, but a silently
        empty export is how the original defect hid."""
        db, path = library
        db.checkpoint()

        snapshot = storage_snapshots.snapshot_library(str(path), reason="held open")

        exports = pathlib.Path(snapshot.snapshot_path) / "duckdb_export"
        written = sorted(p.name for p in exports.glob("*.parquet"))
        assert written, "the Parquet export produced nothing at all"
        assert "documents.parquet" in written


class TestTheDestructiveCallersRefuse:
    """`auto_snapshot_before_risky_operation` raises rather than returning a
    `None` nobody checks."""

    def test_it_returns_a_snapshot_on_an_open_library(self, library):
        db, path = library
        db.checkpoint()

        snapshot = storage_snapshots.auto_snapshot_before_risky_operation(
            path, reason="before something destructive"
        )
        assert snapshot is not None

    def test_it_raises_when_no_snapshot_can_be_taken(self, library, monkeypatch):
        db, path = library

        def boom(*_a, **_k):
            raise RuntimeError("disk is full")

        monkeypatch.setattr(storage_snapshots, "snapshot_library", boom)

        with pytest.raises(SnapshotRefused) as excinfo:
            storage_snapshots.auto_snapshot_before_risky_operation(
                path, reason="before something destructive"
            )
        # The message has to say the operation was REFUSED, not that a snapshot
        # was skipped — a caller reading this decides whether data still exists.
        assert "refused" in str(excinfo.value)
        assert "disk is full" in str(excinfo.value)

    def test_best_effort_is_opt_in_and_still_available(self, library, monkeypatch):
        """A scheduled background snapshot genuinely is best-effort: nothing is
        about to be destroyed and the next attempt is minutes away. That caller
        asks for it explicitly."""
        db, path = library

        monkeypatch.setattr(
            storage_snapshots, "snapshot_library",
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("busy")),
        )
        assert (
            storage_snapshots.auto_snapshot_before_risky_operation(
                path, reason="scheduled", required=False
            )
            is None
        )


class TestTheCopyIsTakenUnderTheWriteLock:
    """#5070 review: the checkpoint and the copy are ONE step.

    The old code called `quiesce_database` and then `shutil.copy2` — the write
    lock was released in between, so a managed write could land in the window and
    tear the copy. Survivable while the copy was an unproved spare; not
    survivable now that it is what the export reads and what a restore restores.

    **Asserted by instrumenting the manager, not by racing it.** A test that
    launched a competing writer and hoped to hit the window would pass by timing
    and prove nothing on a quiet machine — and the reviewer asked for the lock,
    not for a race. So these observe WHEN the lock is held and WHEN the copy
    happens, and check the ordering directly.
    """

    def test_the_copy_happens_while_the_connection_lock_is_held(self, library, monkeypatch):
        from fichero_server.db.manager import db_manager

        db, path = library
        db.checkpoint()
        managed = db_manager.get_database(path)
        events: list[str] = []

        real_copy = __import__("shutil").copy2

        def watched_copy(src, dst, *a, **k):
            # Is the write lock held at the moment of the copy? `RLock.acquire`
            # with a zero timeout from this same thread would succeed
            # re-entrantly, so ask the lock object itself.
            events.append("copy-with-lock" if managed._lock._is_owned() else "copy-UNLOCKED")
            return real_copy(src, dst, *a, **k)

        monkeypatch.setattr("shutil.copy2", watched_copy)
        dest = path.parent / "atomic-copy.duckdb"
        db_manager.copy_database_file(path, dest)
        monkeypatch.undo()

        assert events == ["copy-with-lock"], events
        assert dest.is_file()

    def test_the_checkpoint_comes_before_the_copy_and_neither_releases(
        self, library, monkeypatch
    ):
        from fichero_server.db.manager import db_manager

        db, path = library
        managed = db_manager.get_database(path)
        order: list[str] = []

        # DuckDB's own `execute` is read-only and cannot be patched, so the
        # CONNECTION is proxied instead — everything delegates, and only
        # `execute` is observed. Found by trying the simpler thing first.
        class _Watched:
            def __init__(self, inner):
                self._inner = inner

            def execute(self, sql, *a, **k):
                if isinstance(sql, str) and sql.strip().upper().startswith("CHECKPOINT"):
                    order.append(
                        "checkpoint" if managed._lock._is_owned() else "checkpoint-UNLOCKED"
                    )
                return self._inner.execute(sql, *a, **k)

            def __getattr__(self, name):
                return getattr(self._inner, name)

        real_copy = __import__("shutil").copy2

        def watched_copy(src, dst, *a, **k):
            order.append("copy" if managed._lock._is_owned() else "copy-UNLOCKED")
            return real_copy(src, dst, *a, **k)

        monkeypatch.setattr(managed, "conn", _Watched(managed.conn))
        monkeypatch.setattr("shutil.copy2", watched_copy)
        db_manager.copy_database_file(path, path.parent / "ordered-copy.duckdb")
        monkeypatch.undo()

        # Checkpoint first, copy second, the SAME lock held for both — which is
        # the property the old two-call version could not have.
        assert order == ["checkpoint", "copy"], order

    def test_a_library_with_no_managed_connection_is_still_copied(self, tmp_path):
        """A `Database` built outside the manager has no lock to take. Such a
        caller flushes itself (`Database.checkpoint()`), and the copy must still
        happen rather than being skipped for want of a connection to lock."""
        from fichero_server.db.manager import db_manager

        unmanaged_path = tmp_path / "Unmanaged.fichero"
        unmanaged_path.mkdir()
        db = Database(unmanaged_path / "fichero.duckdb")
        try:
            db.save(Document(id="only", name="Unmanaged", page_content="text"))
            db.checkpoint()
        finally:
            db.close()

        dest = tmp_path / "unmanaged-copy.duckdb"
        db_manager.copy_database_file(unmanaged_path, dest)

        assert dest.is_file()
        assert "documents" in _tables_in(dest)

    def test_the_copy_it_makes_is_openable_and_complete(self, library):
        from fichero_server.db.manager import db_manager

        db, path = library
        db.checkpoint()
        managed = db_manager.get_database(path)
        managed.save(Document(id="doc-3", name="Added Through The Manager", page_content="x"))

        dest = path.parent / "complete-copy.duckdb"
        db_manager.copy_database_file(path, dest)

        conn = connect_utc(str(dest), read_only=True)
        try:
            ids = sorted(r[0] for r in conn.execute("SELECT id FROM documents").fetchall())
        finally:
            conn.close()
        # The row written through the manager is in the copy, because the copy
        # was taken after that connection's own checkpoint under the same lock.
        assert "doc-3" in ids
