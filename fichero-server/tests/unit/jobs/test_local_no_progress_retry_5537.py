"""A page whose local model stopped answering is read once more before it fails (#5537).

Spec: `compute.memory.local-call-judged-by-progress` in
docs/contributor_manual/specs/compute/jobs-and-fine-tuning.md. Driven through a real run
(`POST /api/workflow-execution/execute`); only the model call is a stub, raising the engine's own
"stopped answering" error (what `llm.model_call_slot` raises when a local stream goes quiet; pinned
against a stub server in tests/unit/llm/test_local_no_progress_5537.py).
"""
# ruff: noqa: F811 -- pytest fixtures imported from test_runs_are_jobs are named as test arguments
from __future__ import annotations

from fichero_server.llm.local_inference import LocalModelStoppedAnsweringError
from tests.unit.jobs.test_run_account_5555 import (  # noqa: F401
    _account,
    _fail_page,
    pages,
    quick_retry,
)
from tests.unit.jobs.test_runs_are_jobs import (  # noqa: F401
    _execute,
    _status,
    _wait_for,
    cloud,
    no_embedding_model,
    workflow,
)

STOPPED = str(LocalModelStoppedAnsweringError(120.0))


def test_a_page_whose_model_stopped_answering_once_is_read_again_and_done(client, workflow, pages, cloud):
    restore = _fail_page(cloud, STOPPED, times=1)
    try:
        run = _execute(client, workflow, pages)
        assert _wait_for(lambda: _status(client, run) in ("completed", "failed"))
    finally:
        restore()
    account = _account(client, run)
    assert (account["pages_done"], account["pages_failed"], account["retried"]) == (3, 0, 1)
    assert cloud.calls == 4


def test_a_page_that_stops_answering_twice_fails_with_the_worded_reason(client, workflow, pages, cloud):
    restore = _fail_page(cloud, STOPPED, times=5)
    try:
        run = _execute(client, workflow, pages)
        assert _wait_for(lambda: _status(client, run) in ("completed", "failed"))
    finally:
        restore()
    account = _account(client, run)
    assert (account["pages_done"], account["pages_failed"], account["retried"]) == (2, 1, 1)
    [failure] = account["failures"]
    assert "the model stopped answering for 120 s" in failure["reason"]
    assert "ReadTimeout" not in failure["reason"]
