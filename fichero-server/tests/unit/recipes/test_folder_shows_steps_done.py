"""Each folder shows which recipe steps are done on it, current while the run goes (`activity.run.folder-steps-done`,
pointing at `compute.recipe.folder-shows-steps-done`, #5642). WHY: at 100,000 pages "3 of 800 folders done" says
nothing about which steps a folder still needs; a person opens a folder to read it once its reading is done.

Through the public route (`GET /api/recipes/project/runs/{id}`) and the real scheduler, the harness of
test_recipe_batches_to_spec.py (each step's workflow run stubbed at the boundary; it leaves no lines, readings or
names, so the lines-and-read card is done on no page, and Names, which notes the pages it ran on, on every page).
The count is written on the run as each step ends on a batch: a poll reads it, never the pages.
"""
from __future__ import annotations

from fichero_server.execution import jobs
from tests.unit.recipes.test_recipe_batches_to_spec import (  # noqa: F401 -- fixtures
    _finished, _save, _start, _status, _wait, archive, engine, steps)


def _by_folder(run):
    return {f["folder_id"]: {",".join(s["steps"]): (s["done"], s["of"]) for s in f["steps"]}
            for f in run["folder_steps"]}


def test_each_folder_says_how_many_pages_each_step_is_done_on(client, db, archive, steps):  # noqa: F811
    _save(client)
    run = _finished(client, _start(client)["started"]["job_id"])

    assert run["state"] == "done", run
    assert _by_folder(run) == {
        archive["A"]: {"lines,read": (0, 2), "names": (2, 2)},
        archive["A1"]: {"lines,read": (0, 1), "names": (1, 1)},
        archive["B"]: {"lines,read": (0, 2), "names": (2, 2)},
    }, "a page in no folder has no folder row; a folder counts its own pages, not its folders'"


def test_the_count_is_current_mid_run_and_a_resume_counts_no_page_twice(client, db, archive, steps, monkeypatch):  # noqa: F811
    from fichero_server.recipes import runner

    monkeypatch.setattr(runner, "BATCH_PAGE_LIMIT", 1)  # folder B is two batches
    _save(client)
    steps.interrupt = ("names", 1)  # the project closes as names starts on B's second batch
    job_id = _start(client, folder_id=archive["B"])["started"]["job_id"]
    assert _wait(lambda: _status(client, job_id)["reason"].startswith("Interrupted")), _status(client, job_id)
    assert _by_folder(_status(client, job_id)) == {archive["B"]: {"lines,read": (0, 2), "names": (1, 2)}}, (
        "the batch that ended, and each step begun on the batch going (Names on its 2nd page), count while the run goes")

    jobs.resume(db)
    run = _finished(client, job_id)

    assert _by_folder(run) == {archive["B"]: {"lines,read": (0, 2), "names": (2, 2)}}, "the resumed batch counted twice"
