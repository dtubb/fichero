"""A run's failed pages are one number: its account's, which its job tree shows (#5654 item 6,
`activity.run.account`).

WHY: on the demo (2026-10-10) a run's thread account said pages_failed 0 and failures [] while its job tree
said failed 1. The tree counted rows under the run that failed (a page's first read, read again after a
passing cause and done; a model call), the account counted pages. And a step that reads every page in one
call (not fanned out) kept its pages' failures in its output, which the account did not read.

Driven through the public surface (`POST /api/workflow-execution/execute`, the run's status, the job tree);
only the model is a stub.
"""
# ruff: noqa: F811 -- pytest fixtures imported from test_runs_are_jobs are named as test arguments
from __future__ import annotations

import pytest

from fichero_server.workflows import page_retry
from fichero_server.workflows.run_account import build_account
from tests.unit.jobs.test_run_account_5555 import _account, _fail_page, pages  # noqa: F401
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


def test_a_page_read_again_and_done_is_not_a_failure_in_the_tree(client, workflow, pages, cloud):
    restore = _fail_page(cloud, "the model stopped answering for 120 s", times=1)
    try:
        run = _execute(client, workflow, pages)
        assert _wait_for(lambda: _status(client, run) in ("completed", "failed"))
    finally:
        restore()
    account = _account(client, run)
    assert (account["pages_done"], account["pages_failed"], account["retried"]) == (3, 0, 1)

    tree = _tree(client, run)
    assert (tree["done"], tree["total"], tree["failed"]) == (3, 3, account["pages_failed"])


def test_a_step_that_reads_every_page_in_one_call_counts_its_failed_page():
    """The review read all four pages in one call; one timed out. Its output names it; the account counts it."""
    files = [f"/p/c01_01{i}.jpg" for i in range(4)]
    results = [{"file": f, "text": "ok"} for f in files]
    results[2] = {"file": files[2], "text": "", "value": None,
                  "error": "No streaming chunk received for 120.0s"}
    state = {"files": files, "outputs": {"review": {"results": results, "error": "1/4 failed: No streaming"}}}

    account = build_account(status="completed", reason=None, state=state)

    assert (account.pages_total, account.pages_done, account.pages_failed, account.pages_left) == (4, 3, 1, 0)
    [failure] = account.failures
    assert failure.page == "c01_012.jpg" and "No streaming chunk" in failure.reason


def test_a_fanned_out_steps_aggregate_is_not_counted_twice():
    files = ["/p/a.jpg", "/p/b.jpg"]
    items = [{"file": files[0], "index": 0, "total": 2, "result": {"text": "a"}, "success": True},
             {"file": files[1], "index": 1, "total": 2, "result": {"error": "refused"}, "success": False}]
    state = {"files": files, "parallel_results": {"transcribe": items},
             "outputs": {"transcribe": {"results": [{"file": files[0], "text": "a"},
                                                    {"file": files[1], "error": "refused"}]}}}

    account = build_account(status="completed", reason=None, state=state)

    assert (account.pages_done, account.pages_failed) == (1, 1)
