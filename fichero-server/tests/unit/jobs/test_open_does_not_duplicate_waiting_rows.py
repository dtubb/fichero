"""Opening a library must not make two waiting rows for one pending document (#6209).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md, acceptance
`activity.lane.no-wait-on-a-job-that-will-not-run`. Built 2026-11-07: `enqueue_many`
only reuses waiting jobs (running jobs have already read their input), and `resume`
only resets a running job to waiting if there's no waiting job already (to avoid duplicates).
"""
from __future__ import annotations

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs


def _killed_mid_job(db, kind: str, subject: str) -> str:
    """A job row as it is left when the engine stops: running, never finished."""
    job_id = jobs.enqueue(db, kind, subject, started_by="owner")
    db.execute("UPDATE jobs SET state = 'running', attempts = 1, started_at = now() WHERE id = ?", [job_id])
    return job_id


def _open_as_the_engine_does(test_package):
    """The engine starting again: a new manager has nothing open, and opening the project runs its resume."""
    db_manager.close_database(test_package)
    return db_manager.get_database(test_package)


def test_opening_a_library_does_not_duplicate_waiting_rows_for_pending_thumbnail(
    client, db, test_package, monkeypatch
):
    """When a library is opened, documents with running thumbnail jobs must not get duplicate waiting jobs."""
    # Arrange: Create a document in pending status and a thumbnail job in running status
    # This simulates a document that was being processed when the engine stopped
    doc_id = "doc-6209-thumb"
    
    # Create the document
    from fichero_server.models import DocType, Document, FileType
    
    doc = Document(
        id=doc_id,
        name="test.jpg",
        doc_type=DocType.file,
        file_type=FileType.image,
        status="pending",
        page_content="",
    )
    db.save(doc)
    
    # Create a running thumbnail job for this document
    _killed_mid_job(db, "thumbnail", doc_id)
    
    # Verify: there should be one running job for this document
    running_jobs = db.execute_fetchall(
        "SELECT id, state FROM jobs WHERE subject = ? AND kind = 'thumbnail'",
        [doc_id],
    )
    assert len(running_jobs) == 1
    assert running_jobs[0][1] == "running"
    
    # Act: Reopen the library (simulating what happens when the engine restarts)
    # This is what the engine does on open: first queue_derivatives, then jobs.resume
    # We need to override FICHERO_SKIP_DERIVATIVE_RESUME to test the real flow
    monkeypatch.setenv("FICHERO_SKIP_DERIVATIVE_RESUME", "0")
    reopened_db = _open_as_the_engine_does(test_package)
    
    # Assert: there should be at most ONE job for the document, not two
    # The job might be waiting or running (scheduler starts it immediately)
    # Or the job might have finished (if it was a quick job like thumbnail)
    all_jobs = reopened_db.execute_fetchall(
        "SELECT id, kind, subject, state FROM jobs WHERE kind = 'thumbnail' AND subject = ?",
        [doc_id],
    )
    assert len(all_jobs) <= 1, (
        f"Expected at most 1 job, found {len(all_jobs)}: {[(j[0], j[1], j[2], j[3]) for j in all_jobs]}"
    )
    # If there's a job, it should be waiting or running (not failed/deleted)
    if all_jobs:
        state = all_jobs[0][3]
        assert state in ('waiting', 'running'), f"Expected waiting or running, found {state}"


def test_opening_a_library_does_not_duplicate_waiting_rows_for_embed(
    client, db, test_package, monkeypatch
):
    """When a library is opened, documents with running embed jobs must not get duplicate waiting jobs."""
    # Arrange: Create a document with page_content and a running embed job
    doc_id = "doc-6209-embed"
    
    from fichero_server.models import DocType, Document, FileType
    
    doc = Document(
        id=doc_id,
        name="test.pdf",
        doc_type=DocType.file,
        file_type=FileType.pdf,
        status="pending",
        page_content="This is some text to embed",
    )
    db.save(doc)
    
    # Create a running embed job for this document
    _killed_mid_job(db, "embed", doc_id)
    
    # Verify: there should be one running job for this document
    running_jobs = db.execute_fetchall(
        "SELECT id, state FROM jobs WHERE subject = ? AND kind = 'embed'",
        [doc_id],
    )
    assert len(running_jobs) == 1
    assert running_jobs[0][1] == "running"
    
    # Act: Reopen the library
    # We need to override FICHERO_SKIP_DERIVATIVE_RESUME to test the real flow
    monkeypatch.setenv("FICHERO_SKIP_DERIVATIVE_RESUME", "0")
    reopened_db = _open_as_the_engine_does(test_package)
    
    # Assert: there should be exactly ONE job for the document, not two
    # The job might be waiting or running (scheduler starts it immediately)
    all_jobs = reopened_db.execute_fetchall(
        "SELECT id, kind, subject, state FROM jobs WHERE kind = 'embed' AND subject = ?",
        [doc_id],
    )
    assert len(all_jobs) == 1, (
        f"Expected exactly 1 job, found {len(all_jobs)}: {[(j[0], j[1], j[2], j[3]) for j in all_jobs]}"
    )
    # The job should be waiting or running (not failed/deleted)
    state = all_jobs[0][3]
    assert state in ('waiting', 'running'), f"Expected waiting or running, found {state}"
