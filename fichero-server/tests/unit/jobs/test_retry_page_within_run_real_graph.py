"""`activity.retry.page-within-run` against the REAL graph (review 293): the tester runs this on the M4. A run is read, then
Retry on one of its pages re-enters the SAME thread id with the real LangGraph runner (only the cloud model is a stub).
It checks what the unit test stubs away: the run id and its record are not overwritten, the run ends done again, and the
state reducers keep the earlier pages (the run's account still counts the whole folder)."""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from tests.unit.jobs.test_runs_are_jobs import (  # noqa: F401
    _execute,
    _status,
    _wait_for,
    cloud,
    no_embedding_model,
    pages,
    workflow,
)


def test_retry_on_a_page_reopens_the_same_run_and_keeps_its_earlier_pages(client, db, workflow, pages, cloud):
    run = _execute(client, workflow, pages)
    assert _wait_for(lambda: _status(client, run) == "completed", 120)
    before = client.get(f"/api/activity/jobs/{run}").json()
    page_job = next(c["id"] for step in before["children"] for c in step["children"])
    pages_before = client.get(f"/api/workflow-execution/threads/{run}/status").json()

    r = client.post(f"/api/activity/jobs/{page_job}/retry")

    assert r.status_code == 200, r.text  # no 409, and not a new run
    assert "replaces" not in r.json()
    assert _wait_for(lambda: _status(client, run) == "completed", 120)  # the same run id ends done again
    runs = client.get("/api/workflow-execution/runs").json()
    ids = [x.get("thread_id") for x in (runs if isinstance(runs, list) else runs.get("runs", []))]
    assert ids.count(run) == 1  # the run record was reopened, not duplicated or replaced
    after = client.get(f"/api/workflow-execution/threads/{run}/status").json()
    assert after.get("pages_total", pages_before.get("pages_total")) == pages_before.get("pages_total"), (
        "the state reducers lost the earlier pages: the reopened pass counted only the retried one")
