"""A whole recipe RUN through Find Regions, runner -> lane (review 431, #5863): the Kraken segmenter's page is a row on
the model lane under the run; Stop and Pause on the run reach it while it WAITS, and the step reads stopped / paused,
never failed. Real scheduler and lanes; only the model is a stub, and another heavy model holds the lane.

Written for the M4 (not run where it was written)."""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs
from fichero_server.execution.cancellation import clear_cancellation, clear_pause, request_pause
from fichero_server.recipes import runner as recipes
from tests.unit.jobs.test_closed_mid_run_5608 import _recipe_steps
from tests.unit.jobs.test_runs_are_jobs import _wait_for, pages  # noqa: F401

ENDED = ("done", "failed", "cancelled")
REGIONS = {"steps": ["find-regions"], "card": "regions", "provider": "kraken", "model": "kraken:builtin/blla@bundled",
           "job": "find-regions"}


@pytest.fixture
def model_lane_held(db, monkeypatch):
    """The local-ml lane held by another heavy model, so the run's segmenter page WAITS behind it."""
    from fichero_server.llm import kraken_runtime

    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda path, **k: {
        "width": 32, "height": 32, "lines": [], "regions": []})
    release = threading.Event()
    held = jobs.submit(db, "read-a-page", "held", model="omlx:reader", fn=lambda: release.wait(60))
    assert _wait_for(lambda: jobs.read_job(db, held.job_id)["state"] == "running", 30)
    yield release
    release.set()


def _regions_run(db, pages) -> str:
    recipes.register_job_kinds()
    return recipes.enqueue(db, {"runs": [REGIONS], "skipped": []}, documents=[p.id for p in pages], started_by="owner")


def _waiting_segmenter(db, run) -> bool:
    return db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = 'find-regions' AND state = 'waiting' "
                               "AND parent_id = ?", [run])[0] == 1


def test_stop_on_the_run_withdraws_the_waiting_segmenter_page_and_the_step_reads_stopped(
        client, test_package, pages, model_lane_held):
    db = db_manager.get_database(test_package)
    run = _regions_run(db, pages)
    assert _wait_for(lambda: _waiting_segmenter(db, run), 60)

    assert client.post(f"/api/activity/jobs/{run}/cancel").json()["state"] in ("stopping", "cancelled")

    assert _wait_for(lambda: jobs.read_job(db, run)["state"] in ENDED, 30), jobs.read_job(db, run)
    assert jobs.read_job(db, run)["state"] == "cancelled"
    [step] = _recipe_steps(db, run)
    assert (step["state"], step["why"]) == ("cancelled", "Stopped by you")
    assert db.execute_fetchone("SELECT state, reason FROM jobs WHERE kind = 'find-regions' AND parent_id = ?",
                               [run]) == ("cancelled", "Stopped by you")
    clear_cancellation(run)


def test_pause_on_the_run_defers_it_not_done_and_un_pausing_finishes_find_regions(
        client, test_package, pages, model_lane_held, monkeypatch):
    """434: a Pause withdraws the waiting segmenter page and the run goes back to WAITING (resumes from its checkpoint);
    it must not end done with nothing left to resume. Un-pause (and a free lane): Find Regions finishes."""
    monkeypatch.setattr(recipes, "PAUSED_LOOK_AGAIN_SECONDS", 0.2)
    db = db_manager.get_database(test_package)
    run = _regions_run(db, pages)
    assert _wait_for(lambda: _waiting_segmenter(db, run), 60)

    request_pause(run)

    assert _wait_for(lambda: jobs.read_job(db, run)["state"] == "waiting"
                     and jobs.read_job(db, run)["reason"] == "Paused with its run", 30), jobs.read_job(db, run)
    assert jobs.read_job(db, run)["state"] != "done"
    assert db.execute_fetchone("SELECT state FROM jobs WHERE kind = 'find-regions' AND parent_id = ?",
                               [run]) == ("cancelled",)

    # Paused for several looks: no further page rows (437). The run is re-picked at each look and writes nothing.
    time.sleep(2.0)  # about ten looks at the 0.2 s grace
    assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = 'find-regions' AND parent_id = ?",
                               [run])[0] == 1, "a paused run submitted new page rows"

    clear_pause(run)
    model_lane_held.set()  # the lane frees too
    assert _wait_for(lambda: jobs.read_job(db, run)["state"] in ENDED, 90), jobs.read_job(db, run)
    assert jobs.read_job(db, run)["state"] == "done", jobs.read_job(db, run)
    [step] = _recipe_steps(db, run)
    assert step["state"] == "done", step
