"""An import's derivative stages are jobs (#5353; `activity.durable.*`, `activity.throttle.lanes`).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md. The derivative pool used an
in-memory executor: a quit mid-import lost its queue (only `Status.pending` remembered, and only
for some stages), nothing showed per stage, and nothing could pause it. The stages themselves are
faked here (no thumbnails rendered, no model loaded): these pin the queue around them.
"""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs
from fichero_server.importers import derivatives
from fichero_server.models import DocType, Document, FileType, Status


def _docs(db, n):
    docs = [Document(name=f"p{i}.md", doc_type=DocType.file, file_type=FileType.text,
                     status=Status.pending, page_content=f"page {i}") for i in range(n)]
    for doc in docs:
        db.save(doc)
    return docs


@pytest.fixture
def stages(monkeypatch):
    """Record each stage instead of rendering or embedding."""
    ran: list[tuple[str, str]] = []
    lock = threading.Lock()

    def stage(name, seconds=0.0):
        def run(doc_id, library):
            time.sleep(seconds)
            with lock:
                ran.append((name, doc_id))
        return run

    monkeypatch.setattr(derivatives, "_thumbnail_stage", stage("thumbnail"))
    monkeypatch.setattr(derivatives, "_embed_stage", stage("embed"))
    monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: False)
    return ran


def _wait_for(predicate, seconds=60.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_an_imports_stages_survive_a_quit_and_run_on_the_next_open(test_package, stages, monkeypatch):
    """WHY: the pool was memory. Quit mid-import and every queued thumbnail and embed was gone;
    only `Status.pending` could re-queue some of them. The rows are written with the import, so
    the next open carries on with exactly what was left."""
    db = db_manager.get_database(test_package)
    jobs.set_paused(True)
    with db.transaction():
        docs = _docs(db, 2)
        derivatives.queue_derivatives(docs, library_path=test_package, db=db)

    db_manager.close_database(test_package)  # quit
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    db = db_manager.get_database(test_package)
    assert sorted(db.execute_fetchall("SELECT kind, state FROM jobs")) == [
        ("embed", "waiting"), ("embed", "waiting"), ("thumbnail", "waiting"), ("thumbnail", "waiting")]

    jobs.set_paused(False)
    assert _wait_for(lambda: len(stages) == 4)
    assert sorted(stages) == sorted((stage, doc.id) for stage in ("thumbnail", "embed") for doc in docs)


def test_a_rolled_back_import_queues_nothing(db, test_package, stages):
    """WHY: a stage queued for a document that never committed would look the id up, find
    nothing, and fail; the rows commit or roll back with the documents they name."""
    with pytest.raises(RuntimeError):
        with db.transaction():
            derivatives.queue_derivatives(_docs(db, 1), library_path=test_package, db=db)
            raise RuntimeError("the import failed")
    assert db.execute_fetchall("SELECT kind FROM jobs") == []


def test_thumbnails_run_two_at_a_time_never_three(db, test_package, monkeypatch):
    """WHY: more concurrent texture decodes than two destabilised the window server (#1400);
    the images lane is two wide, and stays two wide however much is queued."""
    live, peak, lock = [0], [0], threading.Lock()

    def thumbnail(doc_id, library):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.05)
        with lock:
            live[0] -= 1

    monkeypatch.setattr(derivatives, "_thumbnail_stage", thumbnail)
    monkeypatch.setattr(derivatives, "_embed_stage", lambda doc_id, library: None)
    monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: False)
    for future in derivatives.queue_derivatives(_docs(db, 8), library_path=test_package):
        future.result(timeout=60)
    assert peak[0] == 2


def test_pause_holds_an_import_and_activity_shows_one_row_per_stage(db, client, test_package, stages):
    """WHY: an import of 1,600 pages queues thousands of stage jobs; Activity must say "Make
    thumbnails: 3 waiting, paused by you", not list every page, and nothing may run while paused."""
    jobs.set_paused(True)
    derivatives.queue_derivatives(_docs(db, 3), library_path=test_package)
    time.sleep(0.3)
    assert stages == []
    rows = [j for j in client.get("/api/activity/jobs").json()["jobs"] if j["task_type"] in ("thumbnail", "embed")]
    assert sorted((r["name"], r["total"], r["state"], r["reason"]) for r in rows) == [
        ("Embed for search", 3, "waiting", "Paused by you"),
        ("Make thumbnails", 3, "waiting", "Paused by you"),
    ]
    jobs.set_paused(False)
    assert _wait_for(lambda: len(stages) == 6)


def test_queuing_the_same_pages_again_does_nothing_twice(db, test_package, stages):
    """WHY: opening a library re-queues every page still `pending` (db/manager.py) on top of the
    rows that survived the quit; a page must still be thumbnailed and embedded once."""
    jobs.set_paused(True)
    docs = _docs(db, 300)
    derivatives.queue_derivatives(docs, library_path=test_package)
    derivatives.queue_derivatives(docs, library_path=test_package)
    assert db.execute_fetchone("SELECT count(*) FROM jobs")[0] == 600
    jobs.set_paused(False)
    assert _wait_for(lambda: len(stages) == 600)
    time.sleep(0.3)
    assert len(stages) == 600
