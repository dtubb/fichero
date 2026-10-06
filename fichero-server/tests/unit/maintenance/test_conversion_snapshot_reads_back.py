"""The conversion's snapshot reads back on a project that is being written to (#5562).

Spec: `segments-and-geometry.md` -- `source.convert.snapshot-first-and-proved`,
`source.convert.starts-when-a-project-opens`.

WHY: on clones of the real Marshall project the conversion refused with "snapshot ... does not
read back": artifacts expected 21,996, found 17,727 (one per page -- the dates artifacts Work Out
Dates had just written), and activities, checkpoints, checkpoint_writes, jobs and workflow_runs
all a few rows short. The copy dropped nothing: the proof compared it with the project counted
AFTER the snapshot's Parquet exports and vector copy, by which time the project had moved on. The
fix counts the project at the copy, under the same locks, and the proof compares against that.
The check is as strict as before -- every table, exact counts -- it is only aimed at the right
moment. If this regresses, no legacy project that is being used converts (#5222), or worse, a
proof passes on a copy that is not the project.

Everything here runs the REAL `snapshot_library`, the real copy, the real proof and the real
page loop on a temporary project; only where snapshots are kept is moved under `tmp`.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action and route)
from fichero_server.core.duckdb_session import connect_utc
from fichero_server.db import Database
from fichero_server.db import storage_snapshots
from fichero_server.db.storage import StorageSettings
from fichero_server.maintenance import conversion_on_open
from fichero_server.maintenance import project_conversion as pc
from fichero_server.models import Artifact, Segment
from fichero_server.models.conversion import ConversionRun, ConversionVerdict
from tests.unit.maintenance.test_project_conversion_resume import _pages

pytestmark = pytest.mark.source_model

PAGES = 5


def _dates_artifact(document_id: str) -> Artifact:
    """What Work Out Dates writes on every page it reads (`date_extract.py`)."""
    return Artifact(
        document_id=document_id, artifact_type="dates", content="1918-03-31",
        data={"document_id": document_id, "status": "dated"}, provider="rule", model="histdate",
    )


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project of unconverted pages that ALREADY carry dates artifacts, as Marshall's did."""
    monkeypatch.setattr(storage_snapshots, "settings", StorageSettings(base_path=tmp_path / "state"))
    package = tmp_path / "Marshall-shaped.fichero"
    package.mkdir()
    db = Database(package / "fichero.duckdb")
    docs = _pages(db, PAGES)
    for doc in docs:
        db.save(_dates_artifact(doc.id))
    try:
        yield db, package, docs
    finally:
        db.close()


def _rows_in_copy(snapshot, table: str) -> int:
    source = Path(snapshot.snapshot_path) / "duckdb_file" / "fichero.duckdb"
    conn = connect_utc(str(source), read_only=True)
    try:
        return conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
    finally:
        conn.close()


def _snapshot_of(run: ConversionRun):
    [snapshot] = [s for s in storage_snapshots.list_snapshots() if s.id == run.snapshot_id]
    return snapshot


def test_a_project_with_dates_artifacts_converts_end_to_end(project):
    """The clean case: dates artifacts on every page, nothing else writing. The snapshot carries
    every artifact kind, proves, and every page converts."""
    db, package, docs = project
    artifacts_before = db.table_row_counts()["artifacts"]
    assert artifacts_before == 2 * PAGES                    # a transcription and a dates per page

    run = pc.convert_project(db, package)

    assert run.verdict is ConversionVerdict.completed, run.snapshot_proof
    assert run.snapshot_proof["mismatches"] == {}
    assert run.pages_converted == PAGES and not run.failures
    snapshot = _snapshot_of(run)
    assert _rows_in_copy(snapshot, "artifacts") == artifacts_before   # every kind, dates included
    assert snapshot.is_pinned
    assert all(db.query(Segment, document_id=d.id) for d in docs)


def test_rows_written_while_the_snapshot_finishes_do_not_refuse_it(project, monkeypatch):
    """The Marshall shape: Work Out Dates (and the job rows around it) land AFTER the copy, while
    the snapshot is still exporting and copying vectors. Before #5562 the proof counted the
    project after all that and refused (artifacts expected N+pages, found N)."""
    db, package, docs = project
    at_copy = db.table_row_counts()
    real_manifest = storage_snapshots._write_manifest

    def meanwhile(root, manifest):
        for doc in docs:                                     # a second Work Out Dates pass
            db.save(_dates_artifact(doc.id))
        real_manifest(root, manifest)

    monkeypatch.setattr(storage_snapshots, "_write_manifest", meanwhile)

    run = pc.plan_conversion(db, package)

    assert run.verdict is ConversionVerdict.ready, run.snapshot_proof
    assert run.snapshot_proof["mismatches"] == {}
    # The copy is the project AT THE COPY -- every row of every table as it was then...
    snapshot = _snapshot_of(run)
    assert _rows_in_copy(snapshot, "artifacts") == at_copy["artifacts"]
    # ...and the later writes are in the project, not lost.
    assert db.table_row_counts()["artifacts"] == at_copy["artifacts"] + PAGES


def test_a_copy_that_lost_rows_is_still_refused(project, monkeypatch):
    """The check is not weakened: a copy that does not hold the rows the project had AT THE COPY
    is refused, whatever happened after."""
    db, package, _docs = project
    from fichero_server.db.manager import db_manager

    original = db_manager.copy_database_file

    def lossy(*args, **kwargs):
        dest = original(*args, **kwargs)
        conn = connect_utc(str(dest))
        try:
            conn.execute("DELETE FROM artifacts WHERE artifact_type = 'dates'")
        finally:
            conn.close()
        return dest

    monkeypatch.setattr(db_manager, "copy_database_file", lossy)

    run = pc.plan_conversion(db, package)

    assert run.verdict is ConversionVerdict.refused_snapshot
    assert run.snapshot_proof["mismatches"]["artifacts"] == {
        "expected": 2 * PAGES, "found": PAGES,
    }


def test_a_writer_outside_the_locks_committing_across_the_checkpoint_is_waited_out(project, monkeypatch):
    """The activity store and the workflow checkpointer write through their OWN connections to
    the library file, outside the engine's locks -- the activities, checkpoints and
    checkpoint_writes rows Marshall's proof found short. One commits between the count before
    the CHECKPOINT and the one after: the copy is retried, and the snapshot that is kept holds
    the row and proves."""
    db, package, _docs = project
    path = str(package / "fichero.duckdb")
    side = connect_utc(path)                                  # as ActivityStore opens it
    side.execute("CREATE TABLE activities (id TEXT PRIMARY KEY, message TEXT)")
    side.close()
    calls = {"n": 0}
    real_counts = db.table_row_counts

    def counts_while_a_job_logs():
        counted = real_counts()
        calls["n"] += 1
        if calls["n"] == 1:                                   # the count BEFORE the first checkpoint
            writer = connect_utc(path)
            try:
                writer.execute("INSERT INTO activities VALUES ('a-1', 'page dated')")
            finally:
                writer.close()
        return counted

    monkeypatch.setattr(db, "table_row_counts", counts_while_a_job_logs)

    run = pc.plan_conversion(db, package)

    assert run.verdict is ConversionVerdict.ready, run.snapshot_proof
    assert calls["n"] >= 4, "the moved count must have caused a second checkpoint and count"
    assert _rows_in_copy(_snapshot_of(run), "activities") == 1


def test_a_writer_that_never_stops_refuses_by_name_and_converts_nothing(project, monkeypatch):
    """Bounded: rows moving across every checkpoint until the wait runs out is a refusal, never a
    snapshot proved against a count that is not the copy's."""
    db, package, docs = project
    monkeypatch.setattr(storage_snapshots, "SNAPSHOT_WRITE_WAIT_S", 0.3)
    real_counts = db.table_row_counts
    path = str(package / "fichero.duckdb")
    side = connect_utc(path)
    side.execute("CREATE TABLE activities (id TEXT PRIMARY KEY, message TEXT)")
    side.close()
    tick = {"n": 0}

    def always_moving():
        counted = real_counts()
        tick["n"] += 1
        writer = connect_utc(path)
        try:
            writer.execute(f"INSERT INTO activities VALUES ('a-{tick['n']}', 'still running')")
        finally:
            writer.close()
        return counted

    monkeypatch.setattr(db, "table_row_counts", always_moving)

    run = pc.convert_project(db, package)

    assert run.verdict is ConversionVerdict.refused_snapshot
    assert "rows were written while the copy was checkpointed" in run.snapshot_proof["mismatches"]["__snapshot__"]
    assert not any(db.query(Segment, document_id=d.id) for d in docs)


def test_closing_during_the_open_time_steps_takes_no_snapshot(project, monkeypatch):
    """Through the open path: the stop arrives while the steps before the conversion run; the
    runner returns without snapshotting, so nothing happens at shutdown. (Marshall's refusal was
    logged at SHUTDOWN: the stop was ignored here and the snapshot taken on the way out.)"""
    db, package, _docs = project
    monkeypatch.setenv("FICHERO_CONVERSION_START_DELAY_SECONDS", "0")
    monkeypatch.delenv("FICHERO_SKIP_PROJECT_CONVERSION", raising=False)
    in_steps = threading.Event()
    from fichero_server.api.routes.document import segment_readings

    def slow_steps(_db, *, should_stop):
        """A long open-time step that, like the real one, returns early when told to stop."""
        in_steps.set()
        deadline = time.monotonic() + 30
        while not should_stop() and time.monotonic() < deadline:
            time.sleep(0.01)

    monkeypatch.setattr(segment_readings, "compose_line_readings", slow_steps)
    snapshots_taken: list = []
    real_snapshot = storage_snapshots.snapshot_library
    monkeypatch.setattr(
        storage_snapshots, "snapshot_library",
        lambda *a, **k: snapshots_taken.append(a) or real_snapshot(*a, **k),
    )

    thread = conversion_on_open.start(db, package)
    assert thread is not None and in_steps.wait(30)
    conversion_on_open.stop(package)                         # the library closes
    thread.join(30)

    assert not thread.is_alive()
    assert snapshots_taken == []
    assert db.query(ConversionRun) == []
