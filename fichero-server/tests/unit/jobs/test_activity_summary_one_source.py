"""The one engine summary (`activity.popover.same-summary`, `activity.window.live-block`, `activity.window.background-group`;
#5851, #5839, #5852): the live blocks (Recipe > Stage > Workflow, done / failed / left), the background group (one line
per kind with its total, a wait that looks waiting) and the History count are built ONCE from the ordered job list, and
ride in the one jobs response the window and the popover both read, so they cannot disagree."""
from __future__ import annotations

from fichero_server.api.routes.system.activity import (
    BackgroundJob,
    BackgroundJobsResponse,
    background_lines,
    order_for_activity,
    recipe_block,
    workflow_block,
)
from fichero_server.workflows.run_account import RunAccount


def _job(job_id, task_type, state, **kw):
    return BackgroundJob(id=job_id, task_type=task_type, name=kw.pop("name", job_id), current=kw.pop("current", 0),
                         total=kw.pop("total", 0), percent=0.0, state=state, **kw)


def test_a_workflow_run_is_a_live_block_with_its_counts():
    account = RunAccount(state="running", pages_total=20, pages_done=7, pages_failed=1, pages_left=12)
    block = workflow_block(_job("r1", "workflow", "running", name="Transcribe", account=account))
    assert (block.workflow, block.done, block.failed, block.left, block.total) == ("Transcribe", 7, 1, 12, 20)


def test_a_recipe_block_names_the_recipe_the_stage_and_the_workflow_with_its_folders():
    account = RunAccount(state="running", pages_total=20, pages_done=7, pages_left=13)
    status = {"state": "running", "reason": None, "waiting_for": None, "folders_done": 2, "folders_total": 8,
              "steps": [{"state": "done", "doing": "Finding the lines"},
                        {"state": "running", "doing": "Reading the lines with Kraken", "account": account}]}
    block = recipe_block(_job("rec", "run-a-recipe", "running", name="Run the recipe: Transcribe"), status, "Read lines")
    assert (block.recipe, block.stage, block.workflow) == ("Run the recipe: Transcribe", "Reading the lines with Kraken",
                                                           "Read lines")
    assert (block.done, block.left, block.folders_done, block.folders_total) == (7, 13, 2, 8)


def test_a_waiting_block_says_what_it_waits_for():
    status = {"state": "waiting", "reason": "Waiting for the recipe run x to finish", "steps": []}
    assert recipe_block(_job("rec", "run-a-recipe", "waiting"), status, None).reason.startswith("Waiting for")


def test_background_work_is_one_line_per_kind_and_never_a_run_or_an_ended_row():
    jobs = [_job("w", "workflow", "running"), _job("e", "embed", "waiting", name="Embed for search", total=40,
                                                  reason="Waiting for reading to finish"),
            _job("t", "thumbnail", "running", name="Thumbnails", current=5, total=9),
            _job("old", "embed", "failed")]
    lines = background_lines(jobs)
    assert [(line.kind, line.state, line.total) for line in lines] == [("embed", "waiting", 40), ("thumbnail", "running", 9)]
    assert lines[0].reason == "Waiting for reading to finish"  # a wait that looks waiting, and says why


def test_the_history_count_is_the_ended_rows_and_the_summary_rides_in_the_one_response():
    listed = order_for_activity([_job("old", "workflow", "failed"), _job("stopped", "run-a-recipe", "cancelled"),
                                 _job("live", "workflow", "running")])
    assert sum(1 for j in listed if j.group == "earlier") == 2
    assert "activity" in BackgroundJobsResponse.model_fields  # the window and the popover read this one field


def test_a_live_block_reuses_the_status_the_list_already_read(monkeypatch):
    """Review 297: the summary re-ran `_recipe_state` for each live recipe run the list had already derived."""
    import asyncio

    from fichero_server.api.routes.system import activity

    async def not_again(*_a, **_k):
        raise AssertionError("_recipe_state ran again")

    monkeypatch.setattr(activity, "_recipe_state", not_again)
    monkeypatch.setattr(activity, "get_activity_tracker", lambda _p: type("T", (), {"store": type(
        "S", (), {"get_workflow_run": staticmethod(lambda _i: asyncio.sleep(0, None))})()})())
    status = {"state": "running", "reason": None, "waiting_for": None, "steps": []}
    db = type("Db", (), {"path": "/tmp/x/library.duckdb"})()
    blocks = asyncio.run(activity.live_blocks(db, [_job("rec", "run-a-recipe", "running")], {"rec": status}))
    assert [b.id for b in blocks] == ["rec"]
