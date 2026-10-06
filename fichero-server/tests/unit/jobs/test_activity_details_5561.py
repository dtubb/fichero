"""What the Activity details view reads from the engine (#5561).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md, "The details view (#5561)":

* `activity.details.engine-carries-what-it-shows`: "every node of `GET /api/activity/jobs/{id}` carries
  `started_at`, `finished_at`, `working_on`, `started_by`, the page's document id and display name, and the
  run node its peak memory; the engine serves a log filtered by job id".
* `activity.details.log-filtered-newest-last`: "the log shows only the lines the engine wrote for this row
  and the rows under it, newest last".
* `activity.details.heading-names-not-ids`: no thread id, node id or temp name where a name belongs.

Driven through the public surface: a real entity-extraction run started with
`POST /api/workflow-execution/execute`, read with `GET /api/activity/jobs/{id}` and
`GET /api/activity/jobs/{id}/log`. Only the model is a stub (a cloud chat model answering from memory).
"""
# ruff: noqa: F811 -- pytest fixtures imported from other test modules are named as test arguments
from __future__ import annotations

from datetime import datetime

from fichero_server.execution import jobs
from tests.unit.jobs.test_run_account_5555 import _fail_page, pages, quick_retry  # noqa: F401
from tests.unit.jobs.test_runs_are_jobs import (  # noqa: F401
    _execute,
    _status,
    _tree,
    _wait_for,
    cloud,
    no_embedding_model,
    workflow,
)


def _finished_tree(client, workflow, pages):
    run = _execute(client, workflow, pages)
    assert _wait_for(lambda: _status(client, run) in ("completed", "failed"))
    return _tree(client, run)


def _calls(tree):
    return [c for step in tree["children"] for c in step["children"]]


def _log(client, job_id):
    r = client.get(f"/api/activity/jobs/{job_id}/log")
    assert r.status_code == 200, r.text
    return r.json()


def _when(text):
    return datetime.fromisoformat(text)


def _nodes(tree):
    yield tree
    for child in tree["children"]:
        yield from _nodes(child)


def test_activity_details_engine_carries__times_started_by_and_names_on_every_node(client, workflow, pages, cloud):
    """`activity.details.engine-carries-what-it-shows` and `heading-names-not-ids`: every node says when it
    started and ended (absolute, UTC), who started it, and its name; a page its document's id and file
    name, a run and a step the names their records have, never an id."""
    tree = _finished_tree(client, workflow, pages)
    started, finished = _when(tree["started_at"]), _when(tree["finished_at"])
    assert started.tzinfo is not None and started <= finished
    assert tree["started_by"]
    assert tree["display_name"] == workflow.name  # the workflow's name, not its thread id
    assert tree["working_on"] is None  # a finished run works on nothing
    step = next(s for s in tree["children"] if s["subject"].endswith("Transcribe"))
    assert step["display_name"] and tree["id"] not in step["display_name"]
    calls = _calls(tree)
    assert {c["display_name"] for c in calls} == {d.name for d in pages}
    assert {c["document_id"] for c in calls} == {d.id for d in pages}
    for node in _nodes(tree):
        assert "finished_at" in node and "started_at" in node and "started_by" in node
        if node["finished_at"] and node["started_at"]:
            assert _when(node["started_at"]) <= _when(node["finished_at"])
    # The run node's peak memory rides on its account (#5537), the one record its status shows.
    assert "engine_peak_memory_bytes" in tree["account"]


def test_activity_details_engine_carries__working_on_names_the_running_page(client, db, pages):
    """`activity.details.state-says-why` (a running row what it is working on now): a running run's node
    names its running step and, under it, the page by its file name."""
    run = "run-working-on"
    jobs._record(db, run, kind="workflow", subject=run, parent_id=None, state="running", reason=None,
                 name="Transcribe")
    jobs._record(db, jobs.step_id(run, "transcribe"), kind="workflow-step", subject=jobs.step_id(run, "transcribe"),
                 parent_id=run, state="running", reason=None, name="Transcribe")
    jobs._record(db, "page-0", kind="read-a-page", subject=pages[0].id, parent_id=jobs.step_id(run, "transcribe"),
                 state="running", reason=None, name=None)
    tree = _tree(client, run)
    assert tree["working_on"] == f"Transcribe, {pages[0].name}"
    assert tree["children"][0]["working_on"] == pages[0].name
    assert tree["started_at"] is not None and tree["finished_at"] is None  # running: no end, never "now"


def test_activity_details_log__a_run_with_a_failed_page_says_so_newest_last(client, workflow, pages, cloud):
    """`activity.details.log-filtered-newest-last`: the run's log has its events and its rows' lines (a
    failed page by its file name and why), oldest first, so the newest is last; a page's log has only
    that page's lines."""
    restore = _fail_page(cloud, "the provider refused this letter", times=99)
    try:
        tree = _finished_tree(client, workflow, pages)
    finally:
        restore()
    log = _log(client, tree["id"])
    assert log["job_id"] == tree["id"]
    lines = log["lines"]
    assert lines
    failed = [line for line in lines if line["level"] == "error" and "refused this letter" in line["message"]]
    assert failed and any(line["message"].startswith("Failed: p") and ".png" in line["message"] for line in failed)
    times = [_when(line["timestamp"]) for line in lines if line["timestamp"]]
    assert times == sorted(times)  # newest last
    under = {n["id"] for n in _nodes(tree)}
    assert {line["job_id"] for line in lines} <= under  # nothing about another row

    page = next(c for c in _calls(tree) if c["state"] == "failed")
    page_lines = _log(client, page["id"])["lines"]
    assert page_lines and {line["job_id"] for line in page_lines} == {page["id"]}
    assert any("refused this letter" in line["message"] for line in page_lines)


def test_activity_details_log__another_run_is_not_in_it(client, workflow, pages, cloud):
    """`activity.details.log-filtered-newest-last`: "only the lines the engine wrote for this row and the
    rows under it": a second run's lines never appear in the first's log."""
    first = _finished_tree(client, workflow, pages)
    second = _finished_tree(client, workflow, pages[:1])
    assert first["id"] != second["id"]
    second_rows = {n["id"] for n in _nodes(second)}
    assert not second_rows & {line["job_id"] for line in _log(client, first["id"])["lines"]}


def test_activity_details_log__an_unknown_job_is_404(client, db):
    r = client.get("/api/activity/jobs/no-such-job/log")
    assert r.status_code == 404
