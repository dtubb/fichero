"""A snapshot taken while another connection is mid-write waits for the write, or refuses by name --
never a 500, never a partial snapshot, never a lost write (#5185).

WHY: snapshots guard real libraries before conversions and migrations (`SnapshotRefused` stops the
destructive step when none can be taken). A write transaction open on another connection to the same
database -- a cursor, which `Database._lock` does not cover -- made DuckDB refuse the CHECKPOINT the
copy needs ("there are other write transactions active"), and the route answered 500. The tempting
fix, FORCE CHECKPOINT, aborts that transaction: the snapshot would succeed by destroying the write it
was meant to protect. So: wait for it (bounded, releasing the locks so it can finish), then copy the
checkpointed file -- or refuse, leaving nothing behind. If this regresses, a busy library cannot be
snapshotted (so a conversion cannot run), or a snapshot eats a write, or a torn half-snapshot is
left on disk looking like a real one.

Reproduced deterministically: the library opened through the manager (as the engine holds it), a
second connection with an UPDATE uncommitted, then a snapshot.
"""

from __future__ import annotations

import threading
import time

import pytest

from fichero_server.core.duckdb_session import connect_utc
from fichero_server.db import storage_snapshots
from fichero_server.db.manager import db_manager
from fichero_server.db.storage import StorageSettings
from fichero_server.db.storage_snapshots import SnapshotBusy
from fichero_server.models import Document


@pytest.fixture
def busy_library(tmp_path, monkeypatch):
    """A managed, open library and a second connection with a write in flight on doc-1."""
    monkeypatch.setattr(storage_snapshots, "settings", StorageSettings(base_path=tmp_path / "state"))
    path = tmp_path / "Busy.fichero"
    path.mkdir()
    db = db_manager.get_database(path)
    db.save(Document(id="doc-1", name="before", page_content="x"))
    other = db.conn.cursor()
    other.execute("BEGIN TRANSACTION")
    other.execute(f"UPDATE {db._table_name(Document)} SET name = 'the write' WHERE id = 'doc-1'")
    try:
        yield db, path, other
    finally:
        try:
            other.execute("ROLLBACK")
        except Exception:  # noqa: BLE001 -- already committed by the test
            pass
        db_manager.close_database(path)


def _name_in_copy(db, snapshot) -> str:
    root = storage_snapshots.settings.snapshots_dir / snapshot.duckdb_path / "fichero.duckdb"
    conn = connect_utc(str(root), read_only=True)
    try:
        return conn.execute(f"SELECT name FROM {db._table_name(Document)} WHERE id = 'doc-1'").fetchone()[0]
    finally:
        conn.close()


def test_a_write_that_finishes_during_the_wait_is_in_the_snapshot(busy_library):
    db, path, other = busy_library
    threading.Timer(0.3, lambda: other.execute("COMMIT")).start()
    started = time.monotonic()
    snapshot = storage_snapshots.snapshot_library(str(path), reason="during a write")
    assert time.monotonic() - started >= 0.25                       # it WAITED, it did not force
    assert _name_in_copy(db, snapshot) == "the write"                   # consistent: the committed write is in it
    assert db.get(Document, "doc-1").name == "the write"            # and the write is not lost


def test_a_write_held_past_the_wait_is_refused_by_name_and_leaves_nothing(busy_library, monkeypatch):
    db, path, other = busy_library
    monkeypatch.setattr(storage_snapshots, "SNAPSHOT_WRITE_WAIT_S", 0.3)
    with pytest.raises(SnapshotBusy, match="being written to"):
        storage_snapshots.snapshot_library(str(path), reason="held too long")
    library_dir = storage_snapshots.settings.snapshots_dir / path.stem
    assert not library_dir.exists() or not any(library_dir.iterdir())   # no half-snapshot on disk
    assert storage_snapshots.list_snapshots(library_name=path.stem) == [] # and no record of one
    other.execute("COMMIT")                                         # the write goes on, untouched
    assert db.get(Document, "doc-1").name == "the write"
    # Once it has finished, a snapshot is taken as normal.
    assert _name_in_copy(db, storage_snapshots.snapshot_library(str(path), reason="after")) == "the write"


def test_the_route_answers_409_with_the_reason_not_500(busy_library, monkeypatch):
    from fastapi.testclient import TestClient

    import fichero_server.api.main as api_main

    db, path, other = busy_library
    monkeypatch.setattr(storage_snapshots, "SNAPSHOT_WRITE_WAIT_S", 0.3)
    client = TestClient(api_main.app)
    response = client.post("/api/storage/snapshots", params={"library_path": str(path), "reason": "busy"})
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["reason"] == "library_busy"
    other.execute("COMMIT")
    assert db.get(Document, "doc-1").name == "the write"



def _managed_job(db, hold: threading.Event, started: threading.Event):
    """The engine's own unit of work on another thread (an audited action, a background job): a
    transaction on the SHARED connection, holding its gate from BEGIN to COMMIT."""
    def run():
        with db.transaction():
            doc = db.get(Document, "doc-2")
            doc.name = "written by the job"
            db.save(doc)
            started.set()
            hold.wait(10)
    job = threading.Thread(target=run, name="background-job")
    job.start()
    started.wait(5)
    return job


def test_a_managed_transaction_is_waited_for_not_checkpointed_inside(busy_library):
    """The sibling the live engine found (#5185 follow-up): holding only the connection's statement
    lock let the snapshot's CHECKPOINT run INSIDE another thread's open transaction -- "the current
    transaction has transaction local changes", a 500. The snapshot now waits for the job's gate."""
    db, path, other = busy_library
    other.execute("COMMIT")                                   # only the managed job is writing now
    db.save(Document(id="doc-2", name="before", page_content="y"))
    hold, started = threading.Event(), threading.Event()
    job = _managed_job(db, hold, started)
    threading.Timer(0.3, hold.set).start()
    snapshot = storage_snapshots.snapshot_library(str(path), reason="during the job")
    job.join()
    root = storage_snapshots.settings.snapshots_dir / snapshot.duckdb_path / "fichero.duckdb"
    conn = connect_utc(str(root), read_only=True)
    try:
        name = conn.execute(f"SELECT name FROM {db._table_name(Document)} WHERE id = 'doc-2'").fetchone()[0]
    finally:
        conn.close()
    assert name == "written by the job"                       # the job committed, then the copy
    assert db.get(Document, "doc-2").name == "written by the job"


def test_a_managed_transaction_held_past_the_wait_is_named_in_the_refusal(busy_library, monkeypatch):
    db, path, other = busy_library
    other.execute("COMMIT")
    db.save(Document(id="doc-2", name="before", page_content="y"))
    monkeypatch.setattr(storage_snapshots, "SNAPSHOT_WRITE_WAIT_S", 0.3)
    hold, started = threading.Event(), threading.Event()
    job = _managed_job(db, hold, started)
    try:
        with pytest.raises(SnapshotBusy) as refused:
            storage_snapshots.snapshot_library(str(path), reason="held too long")
    finally:
        hold.set()
        job.join()
    message = str(refused.value)
    # WHO: the thread and the code that opened the transaction -- the evidence a busy snapshot needs.
    assert "'background-job'" in message and "test_a_snapshot_waits_for_a_write.py:" in message and "open" in message
    assert db.get(Document, "doc-2").name == "written by the job"         # the job's write stands
