"""`activity.retry.page-within-run` against the REAL graph (reviews 293, 295): the tester runs this on the M4. A run reads
three pages and one FAILS; Retry on that failed page re-enters the SAME thread id with the real LangGraph runner (only the
cloud model is a stub). It checks what the unit test stubs away: the run is the same run (no new thread, one record), the
model really read the retried page again, the run ends done, and the state reducers kept the earlier pages (the run's
account says done == total == all three pages, not just the retried one)."""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

import asyncio

from tests.unit.jobs.test_runs_are_jobs import (  # noqa: F401
    _execute,
    _status,
    _wait_for,
    cloud,
    no_embedding_model,
    pages,
    workflow,
)


def _account(db, run):
    from fichero_server.workflows import run_account as accounts

    accounts.forget(run)
    return asyncio.run(accounts.run_account(db, run))


def test_retry_on_a_failed_page_reopens_the_same_run_and_keeps_its_earlier_pages(client, db, workflow, pages, cloud):
    failing = {"left": 1}
    reads = cloud.__call__

    async def one_page_fails(images, prompt, config, **kwargs):
        if failing["left"]:
            failing["left"] -= 1
            raise RuntimeError("the model refused this page")
        return await reads(images, prompt, config, **kwargs)

    import fichero_server.llm as llm

    llm.vision = one_page_fails  # (the `cloud` fixture restores the original at teardown)
    # The run starts with the node cache ON (an ordinary run): the pages it reads are cache hits for a reopen.
    r = client.post("/api/workflow-execution/execute", json={
        "workflow_id": workflow.id, "inputs": {"selected_doc_ids": [d.id for d in pages]}})
    assert r.status_code == 202, r.text
    run = r.json()["thread_id"]
    assert _wait_for(lambda: _status(client, run) in ("completed", "failed"), 120)
    first = _account(db, run)
    assert first.pages_failed == 1 and first.pages_done == len(pages) - 1  # the starting point: one failed page

    failed_page = db.execute_fetchone(
        "SELECT id FROM jobs WHERE state = 'failed' AND kind NOT IN ('workflow', 'workflow-step') ORDER BY created_at LIMIT 1")
    assert failed_page is not None, "the failed page has a job row to Retry"
    before_calls = cloud.calls

    r = client.post(f"/api/activity/jobs/{failed_page[0]}/retry")

    assert r.status_code == 200, r.text  # no 409, and not a new run
    assert "replaces" not in r.json()
    assert _wait_for(lambda: cloud.calls > before_calls, 120), "the retried page was read again by the model"
    assert _wait_for(lambda: _status(client, run) == "completed" and _account(db, run).pages_failed == 0, 120)
    assert cloud.calls - before_calls == 1, (  # only the retried page is read; the others are cache hits
        f"Retry on one page made {cloud.calls - before_calls} model calls, not 1")
    after = _account(db, run)
    assert after.pages_total == len(pages) and after.pages_done == len(pages), (
        "the state reducers lost the earlier pages, or the retry did not finish the run")
    listed = client.get("/api/workflow-execution/runs", params={"limit": 500}).json()["items"]  # WorkflowRunListResponse
    ids = [x["thread_id"] for x in listed]
    assert ids.count(run) == 1  # one record for the run: reopened, not duplicated


def test_retry_in_a_stopped_run_reads_the_retried_page_and_not_the_never_read_one(client, db, workflow, pages, cloud):
    """The stopped branch (reviews 305, 307): three pages, one read (done), one stopped, one never read. Retry on the
    stopped page reads exactly that page: the model is called once, the never-read page is NOT read, and the run keeps
    its checkpoint (its account still counts all three pages, the never-read one as not done)."""
    failing = {"left": 2}  # two of the three pages are not read: the stopped one and the one that never was
    reads = cloud.__call__

    async def two_pages_unread(images, prompt, config, **kwargs):
        if failing["left"]:
            failing["left"] -= 1
            raise RuntimeError("stopped before this page was read")
        return await reads(images, prompt, config, **kwargs)

    import fichero_server.llm as llm

    llm.vision = two_pages_unread
    r = client.post("/api/workflow-execution/execute", json={
        "workflow_id": workflow.id, "inputs": {"selected_doc_ids": [d.id for d in pages]}})
    assert r.status_code == 202, r.text
    run = r.json()["thread_id"]
    assert _wait_for(lambda: _status(client, run) in ("completed", "failed"), 120)
    asyncio.run(_mark_stopped(db, run))  # what a Stop leaves: the run and its two unread pages say cancelled
    before = _account(db, run)
    assert before.pages_total == len(pages) and before.pages_done == 1, "one page read; the account is from the checkpoint"
    unread = [row[0] for row in db.execute_fetchall(
        "SELECT id FROM jobs WHERE state = 'cancelled' AND kind NOT IN ('workflow', 'workflow-step') ORDER BY id")]
    assert len(unread) == 2
    retried, never_read = unread
    calls = cloud.calls

    r = client.post(f"/api/activity/jobs/{retried}/retry")

    assert r.status_code == 200, r.text
    assert _wait_for(lambda: cloud.calls > calls, 120)
    assert _wait_for(lambda: _status(client, run) in ("completed", "failed"), 120)
    assert cloud.calls - calls == 1, "only the retried page is read, not the never-read one"
    after = _account(db, run)
    assert after.pages_total == len(pages), "the run's record is intact"
    assert after.pages_done == 2 and len(after.not_done_ids) == 1, "two pages read now; the never-read one still is not"
    assert db.execute_fetchone("SELECT state FROM jobs WHERE id = ?", [never_read])[0] == "cancelled"


async def _mark_stopped(db, run):
    from fichero_server.api.routes.workflow_execution.core import get_activity_tracker as tracker

    await tracker(str(db.path)).store.update_workflow_run(thread_id=run, status="cancelled")
    db.execute("UPDATE jobs SET state = 'cancelled', reason = 'Stopped by you' WHERE state = 'failed' "
               "AND kind NOT IN ('workflow', 'workflow-step')")
    db.execute("UPDATE jobs SET state = 'cancelled', reason = 'Stopped by you' WHERE id = ?", [run])
