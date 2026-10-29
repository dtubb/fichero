"""`activity.recipe-run.stop-reaches-its-step`: a stopped run says who stopped it.

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md. WHY (2026-10-11, the hardening pass): #5609's
Stop works (checked live on a scratch engine: the answer was "stopping", its running step was stopped and the run
ended cancelled), but every stopped row read "Stopped by you", though an agent may have pressed it. The person's own
Stop still reads "Stopped by you"; through the MCP server or the command line it says so; another account is named.
Through the activity route, with the real recipes lane and a held network lane.
"""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs
from tests.unit.jobs.test_cancel_recipe_run_5609 import ENDED  # noqa: F401
from tests.unit.jobs.test_closed_mid_run_5608 import _first_child, _recipe, _waiting_pages, lane_held  # noqa: F401
from tests.unit.jobs.test_runs_are_jobs import _wait_for, cloud, no_embedding_model, pages, workflow  # noqa: F401


def test_a_run_stopped_through_an_agent_says_so(client, test_package, workflow, pages, cloud, lane_held):
    db = db_manager.get_database(test_package)
    running = _recipe(db, workflow, pages)
    assert _wait_for(lambda: _first_child(db, running) is not None, 60)
    assert _wait_for(lambda: _waiting_pages(db, _first_child(db, running)) == 3, 60)
    waiting = _recipe(db, workflow, pages)

    r = client.post(f"/api/activity/jobs/{waiting}/cancel", headers={"X-Fichero-Client": "fichero-mcp"})
    assert r.status_code == 200 and r.json()["state"] == "cancelled", r.text
    assert jobs.read_job(db, waiting)["reason"] == "Stopped by you, through an agent (MCP)"

    r = client.post(f"/api/activity/jobs/{running}/cancel", headers={"X-Fichero-Client": "fichero-mcp"})
    assert r.json()["state"] in ("stopping", "cancelled"), r.text
    assert _wait_for(lambda: jobs.read_job(db, running)["state"] in ENDED, 30)
    row = jobs.read_job(db, running)
    assert row["state"] == "cancelled" and row["reason"].startswith("Stopped by you, through an agent (MCP); "), row


def test_the_persons_own_stop_and_another_accounts(client, test_package, workflow, pages, cloud, lane_held):
    db = db_manager.get_database(test_package)
    first = _recipe(db, workflow, pages)
    assert _wait_for(lambda: _first_child(db, first) is not None, 60)
    mine, theirs = _recipe(db, workflow, pages), _recipe(db, workflow, pages)

    assert client.post(f"/api/activity/jobs/{mine}/cancel").json()["state"] == "cancelled"
    assert jobs.read_job(db, mine)["reason"] == "Stopped by you"
    registry.invoke(db, "job.cancel", {"job_id": theirs}, ActionContext(actor="javier", is_bootstrap=True))
    assert jobs.read_job(db, theirs)["reason"] == "Stopped by javier"
    client.post(f"/api/activity/jobs/{first}/cancel")


def test_a_system_stop_with_no_known_stopper_says_stopped_6005(db):
    """`activity.recipe-run.stopped-by-unknown-says-stopped` (#6005): the engine's own stop (the action's default actor,
    "system", and no client) names nobody: "Stopped", never "Stopped by you". The person's own stop still says "you"."""
    jobs._ensure(db)
    theirs = jobs._insert(db, "a-plain-job", "s", None, "workflow")
    mine = jobs._insert(db, "a-plain-job", "s", None, "workflow")

    registry.invoke(db, "job.cancel", {"job_id": theirs}, ActionContext(is_bootstrap=True))
    registry.invoke(db, "job.cancel", {"job_id": mine}, ActionContext(actor="owner", is_bootstrap=True))

    assert jobs.read_job(db, theirs)["reason"] == "Stopped"
    assert jobs.read_job(db, mine)["reason"] == "Stopped by you"


def test_a_restores_stop_of_every_job_names_nobody_6005(db):
    """`jobs.stop_everything` (a restore, a bulk Undo) is the engine's own stop: "Stopped", never "Stopped by you"."""
    jobs._ensure(db)
    job = jobs._insert(db, "a-plain-job", "s", None, "workflow")

    assert jobs.stop_everything(db) == 1

    assert jobs.read_job(db, job)["reason"] == "Stopped"


def _parent_and_step(db):
    jobs._ensure(db)
    parent = jobs._insert(db, "a-plain-job", "s", None, "workflow")
    child = jobs._insert(db, "a-plain-job", "s", None, "workflow")
    db.execute("UPDATE jobs SET parent_id = ?, state = 'paused' WHERE id = ?", [parent, child])
    return parent, child


def test_a_runs_step_stopped_with_its_waiting_run_says_who_stopped_the_run_6005(db):
    """A run stopped while it waits stops its parked step too (runner.request_cancel): the step's row names the run's
    stopper; the person's own stop still reads "Stopped by you"."""
    from fichero_server.recipes import runner

    for actor, words in (("system", "Stopped"), ("javier", "Stopped by javier"), ("owner", "Stopped by you")):
        parent, child = _parent_and_step(db)
        jobs.note_stopper(parent, actor)

        assert runner.request_cancel(db, parent) == "cancelled"

        assert jobs.read_job(db, child)["reason"] == words, actor


def test_a_running_runs_step_stopped_at_its_next_look_says_who_stopped_the_run_6005(db):
    """A running run asked to stop stops its step at the next look (runner._stop_child_if_asked): the step's row names
    the run's stopper."""
    from fichero_server.execution.cancellation import clear_cancellation, request_cancellation
    from fichero_server.recipes import runner

    parent, child = _parent_and_step(db)
    jobs.note_stopper(parent, "system")
    request_cancellation(parent)
    try:
        assert runner._stop_child_if_asked(db, parent, child)
    finally:
        clear_cancellation(parent)

    assert jobs.read_job(db, child)["reason"] == "Stopped"


def test_the_persons_own_stop_keeps_its_words_through_a_restore_6240(db):
    """#6240 (1): the person's own Stop is recorded, so a restore's `stop_everything` before the job ends (its
    setdefault names nobody) leaves "Stopped by you"."""
    jobs._ensure(db)
    job = jobs._insert(db, "a-plain-job", "s", None, "workflow")
    jobs.note_stopper(job, "owner")

    jobs.stop_everything(db)

    assert jobs.read_job(db, job)["reason"] == "Stopped by you"


def test_a_step_stopped_by_an_agent_keeps_its_stopper_when_the_run_is_stopped_6240(db):
    """#6240 (2): a step child an agent stopped itself keeps "you, through an agent (MCP)" when its run is then
    stopped by someone else (`pass_stopper` sets only a child with no stopper yet)."""
    from fichero_server.recipes import runner

    parent, child = _parent_and_step(db)
    jobs.note_stopper(child, "owner", "fichero-mcp")
    jobs.note_stopper(parent, "system")

    assert runner.request_cancel(db, parent) == "cancelled"

    assert jobs.read_job(db, child)["reason"] == "Stopped by you, through an agent (MCP)"


def test_the_persons_stop_reaches_a_running_step_a_restore_reached_first_6242(db):
    """#6242: the owner stops a running run, and `stop_everything` reaches its running step before the runner's
    `pass_stopper` does (its setdefault writes nobody, ""): the step still reads "Stopped by you". A step an agent or
    another account stopped keeps theirs."""
    from fichero_server.execution.cancellation import clear_cancellation

    parent, child = _parent_and_step(db)
    agents_parent, agents_child = _parent_and_step(db)
    db.execute("UPDATE jobs SET state = 'running' WHERE id IN (?, ?, ?, ?)", [parent, child, agents_parent, agents_child])
    jobs.note_stopper(parent, "owner")
    jobs.note_stopper(agents_parent, "owner")
    jobs.note_stopper(agents_child, "owner", "fichero-mcp")
    try:
        jobs.stop_everything(db)  # first: the step gets the engine's "" before the runner passes the run's stopper on
        jobs.pass_stopper(parent, child)
        jobs.pass_stopper(agents_parent, agents_child)
    finally:
        for job in (parent, child, agents_parent, agents_child):
            clear_cancellation(job)

    assert jobs.stopped_by(child) == "Stopped by you"
    assert jobs.stopped_by(agents_child) == "Stopped by you, through an agent (MCP)"
