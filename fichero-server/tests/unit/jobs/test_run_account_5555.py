"""A run's account: interrupted runs, Activity's counts, and reading failed pages again (#5555).

Spec: docs/contributor_manual/specs/compute/jobs-and-fine-tuning.md (`compute.run.*`) and
docs/contributor_manual/specs/ui/activity-and-automatic-work.md (`activity.run.account`). Found on the 8 GB
Air: after an engine restart a run said "running" for good; Activity showed the run as "running, total 0"
while only the run's status counted its pages; and pages that failed while a model loaded were never read
again. Driven through the public surface: real runs started with `POST /api/workflow-execution/execute`,
read with the run's status, `GET /api/activity/jobs` and `GET /api/activity/jobs/{run}`, and a project
opened through the database manager. Only the model is a stub (a cloud vision model answering from memory).
"""
# ruff: noqa: F811 -- pytest fixtures imported from test_runs_are_jobs are named as test arguments
from __future__ import annotations

from datetime import timedelta

import pytest

from fichero_server.core.timeutil import utc_now
from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs
from fichero_server.workflows import page_retry
from fichero_server.workflows.run_account import build_account
from tests.unit.jobs.test_runs_are_jobs import (  # noqa: F401
    _execute,
    _status,
    _tree,
    _wait_for,
    cloud,
    no_embedding_model,
    workflow,
)


@pytest.fixture(autouse=True)
def quick_retry(monkeypatch):
    monkeypatch.setattr(page_retry, "RETRY_AFTER_SECONDS", 0.0)


@pytest.fixture
def pages(db, tmp_path):
    """Three pages, each its own picture, so the model can tell them apart."""
    from PIL import Image

    from fichero_server.models import DocType, Document, FileType

    docs = []
    for i, colour in enumerate([(255, 255, 255), (200, 10, 10), (10, 200, 10)]):
        path = tmp_path / f"p{i}.png"
        Image.new("RGB", (16, 16), colour).save(str(path), format="PNG")
        doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
        db.save(doc)
        docs.append(doc)
    return docs


def _account(client, thread_id):
    r = client.get(f"/api/workflow-execution/threads/{thread_id}/status", params={"view": "summary"})
    assert r.status_code == 200, r.text
    return r.json()["account"]


def _fail_page(cloud, error: str, times: int):
    """The model raises `error` for the first page it is asked to read, `times` times, then reads it."""
    original = type(cloud).__call__
    target: dict = {"image": None, "left": times}

    async def call(self, images, prompt, config, **kwargs):
        with self.lock:
            if target["image"] is None:
                target["image"] = str(images)
            fail = str(images) == target["image"] and target["left"] > 0
            if fail:
                target["left"] -= 1
                self.calls += 1
        if fail:
            raise RuntimeError(error)
        return await original(self, images, prompt, config, **kwargs)

    type(cloud).__call__ = call
    return lambda: setattr(type(cloud), "__call__", original)


def test_activity_run_account__activity_counts_the_pages_the_status_counts(client, workflow, pages, cloud):
    """Behaviour `activity.run.account`: Activity is the run's account. A three-page run with a page the
    model refuses: the run's status, its row in Activity and its node in the job tree all say 2 done,
    1 failed, 0 left, with the failed page's reason, from one account."""
    restore = _fail_page(cloud, "the provider refused this letter", times=99)
    try:
        run = _execute(client, workflow, pages)
        assert _wait_for(lambda: _status(client, run) in ("completed", "failed"))
    finally:
        restore()
    account = _account(client, run)
    assert (account["pages_total"], account["pages_done"], account["pages_failed"], account["pages_left"]) == (3, 2, 1, 0)
    [failure] = account["failures"]
    assert failure["page"] in {"p0.png", "p1.png", "p2.png"} and failure["document_id"] in {p.id for p in pages}
    assert "refused this letter" in failure["reason"]
    assert account["retried"] == 0  # a refusal is not a passing cause: read once
    assert account["offer"]["label"] == "Read the 1 page that failed"

    tree = _tree(client, run)
    assert (tree["done"], tree["total"], tree["failed"]) == (2, 3, 1)
    assert tree["account"] == account


def test_activity_window_page_by_file_name__a_page_row_is_named_by_its_file(client, workflow, pages, cloud):
    """#5560: Activity listed the pages being read by their long ids; a page's row carries its file name
    (`label`), the id staying in `subject` for the details."""
    run = _execute(client, workflow, pages)
    assert _wait_for(lambda: _status(client, run) in ("completed", "failed"))
    tree = _tree(client, run)
    page_rows = [p for step in tree["children"] for p in step["children"]]
    assert sorted(p["label"] for p in page_rows) == ["p0.png", "p1.png", "p2.png"]
    assert {p["subject"] for p in page_rows} == {p.id for p in pages}
    assert tree["label"] is None and all(step["label"] is None for step in tree["children"])


def test_compute_run_retry_once__a_page_failing_while_the_model_loads_is_read_again(
        client, workflow, pages, cloud):
    """Behaviour `compute.run.retry-passing-cause-once`: a page that fails for a passing cause (the model
    server not ready) is read once more, and done; the account counts it done and says it was retried."""
    restore = _fail_page(cloud, "the local model server for qwen is not ready: loading", times=1)
    try:
        run = _execute(client, workflow, pages)
        assert _wait_for(lambda: _status(client, run) in ("completed", "failed"))
    finally:
        restore()
    account = _account(client, run)
    assert (account["pages_done"], account["pages_failed"], account["retried"]) == (3, 0, 1)
    assert account["offer"] is None
    assert cloud.calls == 4


def test_compute_run_retry_once__a_second_failure_is_the_pages_failure(client, workflow, pages, cloud):
    """The retry is once: a page that is still not ready the second time fails, with its reason, and is
    marked as retried."""
    restore = _fail_page(cloud, "the local model server for qwen is not ready: loading", times=5)
    try:
        run = _execute(client, workflow, pages)
        assert _wait_for(lambda: _status(client, run) in ("completed", "failed"))
    finally:
        restore()
    account = _account(client, run)
    assert (account["pages_done"], account["pages_failed"]) == (2, 1)
    assert account["failures"][0]["retried"] is True
    assert cloud.calls == 4  # two pages once, the failing page twice


def test_compute_run_read_failed_again__one_action_reads_only_the_failed_pages(client, workflow, pages, cloud):
    """Behaviour `compute.run.read-failed-again`: at the end the run offers "Read the N pages that
    failed" as one action; it starts one run over those pages only, with the same model, and a run that
    did every page has nothing to offer (409)."""
    restore = _fail_page(cloud, "the provider refused this letter", times=99)
    try:
        run = _execute(client, workflow, pages)
        assert _wait_for(lambda: _status(client, run) in ("completed", "failed"))
    finally:
        restore()
    calls_before = cloud.calls
    r = client.post(f"/api/workflow-execution/threads/{run}/read-again")
    assert r.status_code == 202, r.text
    again = r.json()
    assert (again["from_thread_id"], again["pages"]) == (run, 1)
    assert _wait_for(lambda: _status(client, again["thread_id"]) in ("completed", "failed"))
    account = _account(client, again["thread_id"])
    assert (account["pages_total"], account["pages_done"], account["pages_failed"]) == (1, 1, 0)
    assert cloud.calls == calls_before + 1

    r = client.post(f"/api/workflow-execution/threads/{again['thread_id']}/read-again")
    assert r.status_code == 409, r.text


def _ghost(db, thread_id, workflow, page_ids, *, last_heard):
    """What a run the engine stopped mid-way leaves: its record and its row still 'running', one page
    read at `last_heard`, and no worker left in this engine."""
    import asyncio

    from fichero_server.workflows.activity_store import ActivityStore

    store = ActivityStore(str(db.path))
    asyncio.run(store.save_workflow_run(
        thread_id=thread_id, workflow_id=workflow.id, workflow_name=workflow.name, status="running",
        workflow_snapshot={"nodes": workflow.nodes, "edges": workflow.edges,
                           "inputs": {"selected_doc_ids": page_ids}},
        resolved_scope={"requested_ids": page_ids, "resolved_ids": page_ids, "resolved_count": len(page_ids)}))
    jobs.record_run(db.path, thread_id, status="running", name=workflow.name)
    jobs.record_step(db.path, thread_id, "transcribe", status="running", name="Transcribe")
    started = last_heard - timedelta(minutes=3)  # the run started before its page was read
    db.execute("UPDATE workflow_runs SET started_at = ? WHERE thread_id = ?", [started, thread_id])
    db.execute("UPDATE jobs SET created_at = ?, started_at = ? WHERE id LIKE ?", [started, started, f"{thread_id}%"])
    db.execute("INSERT INTO jobs (id, kind, subject, state, attempts, started_by, created_at, started_at, "
               "finished_at, parent_id) VALUES ('page-1', 'read-a-page', 'p0.png', 'done', 0, 'workflow', ?, ?, ?, ?)",
               [last_heard, last_heard, last_heard, f"{thread_id}:transcribe"])


def test_compute_run_interrupted_on_start__a_ghost_run_is_marked_interrupted_and_offers_its_pages(
        client, test_package, workflow, pages, cloud):
    """Behaviour `compute.run.interrupted-on-start`: on opening the project after the engine stopped, a
    run the engine did not finish is marked interrupted, with when the engine stopped (the last work the
    run recorded), its row in Activity says so, and it offers to read the pages not done; reading them is
    one run."""
    db = db_manager.get_database(test_package)
    last_heard = utc_now() - timedelta(minutes=7)
    page_ids = [p.id for p in pages]
    _ghost(db, "thread-ghost", workflow, page_ids, last_heard=last_heard)

    db_manager.close_database(test_package)
    db_manager.get_database(test_package)  # the engine starts again and opens the project

    hhmm = last_heard.astimezone().strftime("%H:%M")
    tree = _tree(client, "thread-ghost")
    assert tree["state"] == "failed"
    assert tree["reason"] == f"Interrupted: the engine stopped at {hhmm}, before this run finished"
    account = tree["account"]
    assert account["state"] == "interrupted" and account["interrupted"] is True
    assert account["reason"] == tree["reason"]
    assert account["offer"]["label"] == "Read the 3 pages not done"
    listed = {j["id"]: j for j in client.get("/api/activity/jobs").json()["jobs"]}
    assert listed["thread-ghost"]["state"] == "failed"
    assert listed["thread-ghost"]["account"]["interrupted"] is True

    r = client.post("/api/workflow-execution/threads/thread-ghost/read-again")
    assert r.status_code == 202, r.text
    again = r.json()["thread_id"]
    assert _wait_for(lambda: _status(client, again) in ("completed", "failed"))
    assert _account(client, again)["pages_done"] == 3


def test_compute_run_interrupted_on_start__pages_done_are_kept():
    """An interrupted run keeps its pages done and left from its checkpoint, and offers only the pages not
    done (here the third)."""
    docs = [{"id": f"page-{i}", "path": f"/p{i}.png"} for i in range(3)]
    state = {
        "files": [d["path"] for d in docs],
        "outputs": {"files-source": {"files": [d["path"] for d in docs], "documents": docs}},
        "parallel_results": {"transcribe": [
            {"file": "/p0.png", "index": 0, "total": 3, "success": True, "result": {}},
            {"file": "/p1.png", "index": 1, "total": 3, "success": True, "result": {}}]},
    }
    account = build_account(status="failed", reason="Interrupted: the engine stopped at 14:05, before this run "
                            "finished", state=state)
    assert (account.state, account.pages_done, account.pages_left) == ("interrupted", 2, 1)
    assert account.not_done_ids == ["page-2"]
    assert account.offer.label == "Read the 1 page not done"


def test_activity_run_account__a_running_run_says_what_it_waits_for_its_estimate_and_peak_memory():
    """While a run runs its account says what a page waits for (a memory wait, #5537), the time left at
    its own pace, and the peak memory so far."""
    state = {"files": ["/a", "/b", "/c", "/d"], "parallel_results": {"read": [
        {"file": "/a", "index": 0, "total": 4, "success": True, "result": {}}]}}
    now = utc_now()
    account = build_account(
        status="running", reason=None, state=state, started_at=now - timedelta(seconds=60), now=now,
        waiting_reason="Waiting: memory is tight: Qwen needs about 3.9 GB, this Mac has about 1.8 GB free",
        live_peaks={"engine_peak_memory_bytes": 2_000_000_000, "model_server_peak_memory_bytes": 3_500_000_000})
    assert account.waiting_reason.startswith("Waiting: memory is tight")
    assert account.estimate_seconds_left == 180.0
    assert (account.engine_peak_memory_bytes, account.model_server_peak_memory_bytes) == (2_000_000_000, 3_500_000_000)
    assert account.offer is None


@pytest.mark.parametrize("cause, passing", [
    ("The local model server for qwen is not ready: loading weights", True),
    ("The local model server did not start qwen in time: timed out", True),
    ("Waiting: memory is tight: qwen needs about 3.9 GB. Waited 5 minutes for memory; close other apps", True),
    ("Qwen 8B needs about 7.0 GB to load and read a page, more than this Mac's 8.0 GB of memory can give", False),
    ("the provider refused this letter", False),
    ("Model qwen is not installed", False),
    ("", False),
])
def test_compute_run_retry_once__which_causes_pass(cause, passing):
    assert page_retry.is_passing_cause(cause) is passing
