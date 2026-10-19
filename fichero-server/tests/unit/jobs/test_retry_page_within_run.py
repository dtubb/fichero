"""`activity.retry.page-within-run` (#5853): Retry on a run's page reads it WITHIN its run, not as a new run. An ended run
reopens (same run id) for the page; a live run takes the page into its queue (no 409) and reopens when its pass ends."""
from __future__ import annotations

import asyncio

import pytest

from fichero_server.execution import jobs


def _row(db, job_id, kind, parent, state, subject=None):
    db.execute("INSERT INTO jobs (id, kind, subject, parent_id, state, created_at, started_by) "
               "VALUES (?, ?, ?, ?, ?, now(), 'workflow')", [job_id, kind, subject or job_id, parent, state])


@pytest.fixture
def run(db):
    jobs._ensure(db)
    _row(db, "run-1", "workflow", None, "failed")
    _row(db, "step-1", "workflow-step", "run-1", "failed")
    _row(db, "page-1", "read-a-page", "step-1", "failed", subject="doc-7")
    return db


def test_a_page_knows_the_run_it_belongs_to(run):
    assert jobs.run_of_page(run, "page-1") == "run-1"
    assert jobs.run_of_page(run, "run-1") is None


def _stub_run(monkeypatch, status):
    from fichero_server.api.routes.workflow_execution import core

    reopened: list[tuple] = []

    class Store:
        async def get_workflow_run(self, thread_id):
            return type("R", (), {"status": status})()

    monkeypatch.setattr(core, "get_activity_tracker", lambda _p: type("T", (), {"store": Store()})())

    async def read_again(_db, thread_id, *, documents=None, reopen=False, only_these=False):
        reopened.append((thread_id, documents, reopen) + ((only_these,) if only_these else ()))
        return thread_id, object(), len(documents or [])

    monkeypatch.setattr(core, "read_again", read_again)
    return core, reopened


def test_an_ended_run_reopens_for_the_page_under_the_same_run_id(run, monkeypatch):
    core, reopened = _stub_run(monkeypatch, "failed")
    assert asyncio.run(core.retry_page_in_run(run, "page-1")) == ("run-1", "reopened")
    assert reopened == [("run-1", ["doc-7"], True)]  # the same run, the page's document, reopened (not a new run)


def test_a_live_run_takes_the_page_into_its_queue_with_no_409_and_reopens_when_its_pass_ends(run, monkeypatch):
    core, reopened = _stub_run(monkeypatch, "running")
    assert asyncio.run(core.retry_page_in_run(run, "page-1")) == ("run-1", "queued")
    row = jobs.read_job(run, "page-1")
    assert row["state"] == "waiting" and row["reason"] == jobs.QUEUED_RETRY
    assert reopened == []  # nothing yet: the run is still going
    scheduled: list = []
    from fichero_server.execution import runner

    monkeypatch.setattr(runner, "on_background_loop", lambda coro: (scheduled.append(coro), coro.close()))
    jobs._reopen_for_queued_retries(run, "run-1")  # the run's pass ends (record_run calls this on completed/failed)
    assert len(scheduled) == 1 and jobs._PAGE_RETRIES == {}


def test_a_retry_queued_just_as_the_run_ends_is_not_left_waiting_forever(run, monkeypatch):
    """The run ends between the live look and the queue: its end found nothing to take, so the retry itself must see
    the run is over and reopen it."""
    core, reopened = _stub_run(monkeypatch, "running")
    looks = iter(["running", "completed"])  # live at the first look, over by the second

    class Store:
        async def get_workflow_run(self, thread_id):
            return type("R", (), {"status": next(looks)})()

    monkeypatch.setattr(core, "get_activity_tracker", lambda _p: type("T", (), {"store": Store()})())
    assert asyncio.run(core.retry_page_in_run(run, "page-1")) == ("run-1", "reopened")
    assert reopened == [("run-1", ["doc-7"], True)] and jobs._PAGE_RETRIES == {}


def test_the_queued_pages_are_taken_once(run):
    jobs.queue_page_retry(run, "page-1", "run-1", "doc-7")
    assert jobs.take_page_retries("run-1") == ["doc-7"] and jobs.take_page_retries("run-1") == []


def test_a_workflow_edited_since_its_run_hands_validation_only_edges_among_the_runs_nodes():
    """Review 302: reopening validates the run's nodes with edges that must match them; an edge to a node the edit
    removed is dropped, and the run's own edges stay."""
    from fichero_server.api.routes.workflow_execution.core import edges_among

    nodes = [{"id": "files-source"}, {"id": "transcribe"}]
    edges = [{"source": "files-source", "target": "transcribe", "source_port": "files", "target_port": "files"},
             {"source": "files-source", "target": "added-since", "source_port": "files", "target_port": "files"},
             {"source": "gone", "target": "transcribe"},
             {"source": "files-source", "route_map": {"a": "transcribe", "b": "added-since"}}]
    assert edges_among(edges, nodes) == [edges[0]]


def test_retry_on_a_done_page_answers_in_words_and_does_nothing(run, monkeypatch):
    import pytest
    from fastapi import HTTPException

    core, reopened = _stub_run(monkeypatch, "failed")
    run.execute("UPDATE jobs SET state = 'done' WHERE id = 'page-1'")
    with pytest.raises(HTTPException) as refused:
        asyncio.run(core.retry_page_in_run(run, "page-1"))
    assert refused.value.status_code == 409 and "already read" in refused.value.detail
    assert reopened == []


def test_retry_in_a_stopped_run_reopens_over_the_done_pages_plus_this_one_and_keeps_the_checkpoint(run, monkeypatch):
    """Review 305: a stopped run's Retry never deletes its checkpoint (the account is built from it); it reopens over the
    pages it read (cache hits) plus this one, leaving the never-read pages out."""
    core, reopened = _stub_run(monkeypatch, "cancelled")

    async def done(_db, run_id):
        return ["doc-1", "doc-2"]

    monkeypatch.setattr(core, "_done_documents", done)
    run.execute("UPDATE jobs SET state = 'cancelled' WHERE id = 'page-1'")
    assert asyncio.run(core.retry_page_in_run(run, "page-1")) == ("run-1", "reopened")
    assert reopened == [("run-1", ["doc-1", "doc-2", "doc-7"], True, True)]
    assert "adelete_thread" not in __import__("inspect").getsource(core.retry_page_in_run)


def test_a_reopen_narrowed_to_some_documents_skips_the_other_files_of_the_runs_old_list():
    """The M4's 3-page stopped test (72fd084a9): narrowing `selected_doc_ids` did not narrow, because the checkpoint keeps the
    run's file list; `only_doc_ids` is carried to every file's branch, which skips a file whose document is not named."""
    import inspect

    from fichero_server.workflows import builder, runtime

    assert runtime.build_initial_state({"only_doc_ids": ["a"]})["only_doc_ids"] == ["a"]
    assert runtime.build_initial_state({})["only_doc_ids"] == []
    source = inspect.getsource(builder)
    assert source.count('"only_doc_ids": state.get("only_doc_ids") or []') == 2  # both fan-outs pass it on
    assert "not part of this reopen" in source  # and the per-file branch skips the others
