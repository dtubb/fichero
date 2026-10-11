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
