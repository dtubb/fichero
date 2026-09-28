"""The workflow node cache writes through the library's managed connection, so a snapshot orders
around its writes -- never a 500, never a hang -- and the cache survives the library closing and the
engine restarting (#5189).

WHY: NodeCache predated the single shared connection (#2508) and kept a raw connection of its own to
the library file. Its writes then held the library's database outside every lock the engine owns, so
a snapshot could only poll for a gap; one long write refused a real snapshot (a 409 in a live run),
and snapshots gate conversions and migrations. On the managed connection a cache write and a snapshot
simply take turns: a write in progress lands before the copy, or -- held past the snapshot's wait --
the snapshot is refused by name, bounded, and the write still lands. If this regresses, a busy
workflow can block every snapshot, or a snapshot can hang behind a write.
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
from fichero_server.workflows import cache as cache_module
from fichero_server.workflows.cache import get_node_cache


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_snapshots, "settings", StorageSettings(base_path=tmp_path / "state"))
    monkeypatch.setattr(cache_module, "_cache_instances", {})
    path = tmp_path / "Cached.fichero"
    path.mkdir()
    db = db_manager.get_database(path)
    try:
        yield db, path
    finally:
        db_manager.close_database(path)


def _rows_in_snapshot(snapshot) -> int:
    copy = storage_snapshots.settings.snapshots_dir / snapshot.duckdb_path / "fichero.duckdb"
    conn = connect_utc(str(copy), read_only=True)
    try:
        return conn.execute("SELECT COUNT(*) FROM node_cache").fetchone()[0]
    finally:
        conn.close()


def _write_while_holding(db, cache, key: str, hold: threading.Event, wrote: threading.Event):
    """A cache write still IN PROGRESS: the statement ran, and its caller holds the connection's
    lock (as a slow write would) until `hold` is set."""
    def run():
        with db._lock:
            cache.set(key, {"text": "a transcription"}, "wf", "node", "transcribe")
            wrote.set()
            hold.wait(10)
    thread = threading.Thread(target=run, name="workflow-node")
    thread.start()
    wrote.wait(5)
    return thread


def test_a_librarys_cache_is_on_the_librarys_managed_connection(library):
    db, path = library
    cache = get_node_cache(path / "fichero.duckdb")
    assert cache.conn is db.conn                     # not a second connection to the same file
    cache.set("k", {"v": 1}, "wf", "node", "transcribe")
    assert db.execute_fetchone("SELECT COUNT(*) FROM node_cache")[0] == 1


def test_a_write_in_progress_during_a_snapshot_is_in_the_snapshot(library):
    db, path = library
    cache = get_node_cache(path / "fichero.duckdb")
    hold, wrote = threading.Event(), threading.Event()
    writer = _write_while_holding(db, cache, "in-progress", hold, wrote)
    threading.Timer(0.3, hold.set).start()
    snapshot = storage_snapshots.snapshot_library(str(path), reason="during a workflow")
    writer.join()
    assert _rows_in_snapshot(snapshot) == 1           # the write finished, then the copy


def test_a_write_held_past_the_wait_is_refused_by_name_and_never_hangs(library, monkeypatch):
    db, path = library
    monkeypatch.setattr(storage_snapshots, "SNAPSHOT_WRITE_WAIT_S", 0.3)
    cache = get_node_cache(path / "fichero.duckdb")
    hold, wrote = threading.Event(), threading.Event()
    writer = _write_while_holding(db, cache, "held", hold, wrote)
    outcome: list = []

    def snap():
        try:
            outcome.append(storage_snapshots.snapshot_library(str(path), reason="held"))
        except Exception as refusal:  # noqa: BLE001 -- the outcome is what is asserted
            outcome.append(refusal)

    started = time.monotonic()
    snapper = threading.Thread(target=snap)
    snapper.start()
    snapper.join(timeout=5)
    try:
        assert not snapper.is_alive(), "the snapshot hung behind a held write"
        assert time.monotonic() - started < 5
        [result] = outcome
        assert isinstance(result, SnapshotBusy) and "held the connection's lock" in str(result)
    finally:
        hold.set()
        writer.join()
        snapper.join()
    assert get_node_cache(path / "fichero.duckdb").get("held") is not None   # the write landed


def test_the_cache_survives_the_library_closing_and_an_engine_restart(library, monkeypatch):
    db, path = library
    cache = get_node_cache(path / "fichero.duckdb")
    cache.set("kept", {"text": "an expensive answer"}, "wf", "node", "transcribe")
    db_manager.close_database(path)                   # the library is closed and opened again
    assert cache.get("kept").result == {"text": "an expensive answer"}
    db_manager.close_database(path)                   # an engine restart: no cache objects survive
    monkeypatch.setattr(cache_module, "_cache_instances", {})
    fresh = get_node_cache(path / "fichero.duckdb")
    assert fresh.get("kept").result == {"text": "an expensive answer"}
