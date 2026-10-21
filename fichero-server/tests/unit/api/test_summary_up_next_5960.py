"""`activity.summary.up-next` (#5960): the summary carries `up_next: [{id, name, stage, after, why}]`, the not-yet-started work
in lane order, each with what it waits for in words. The list is already in lane order (`order_for_activity`); this only
picks the waiting rows and says what each waits for."""
from __future__ import annotations

from fichero_server.api.main import app
from fichero_server.api.routes.system.activity import BackgroundJob, up_next


def _job(job_id, task_type, state, **kw):
    return BackgroundJob(id=job_id, task_type=task_type, name=kw.pop("name", job_id), current=0, total=0, percent=0.0,
                         state=state, **kw)


def test_only_waiting_work_is_up_next_in_the_order_given():
    jobs = [_job("a", "workflow", "running"), _job("b", "workflow", "waiting", name="Mosquera box",
                                                     reason="waiting for the model lane: another box is reading"),
            _job("c", "embed", "waiting", reason="memory is tight"), _job("d", "workflow", "failed"),
            _job("e", "run-a-recipe", "waiting", name="Run the recipe", reason="after Read")]
    items = up_next(jobs)
    assert [i.id for i in items] == ["b", "c", "e"]
    assert [i.why for i in items] == ["waiting for the model lane: another box is reading", "memory is tight", "after Read"]
    assert [i.name for i in items] == ["Mosquera box", "c", "Run the recipe"]
    assert [i.after for i in items] == [None, None, None], "a waiting row's reason is words, not a field to parse"


def test_a_stage_kind_names_its_set_up_stage_and_others_none():
    items = {i.id: i for i in up_next([_job("f", "find-lines", "waiting"), _job("g", "embed", "waiting")])}
    assert items["f"].stage == "Find Lines"
    assert items["g"].stage is None


def test_a_waiting_row_with_no_reason_says_what_it_is_in_the_queue_for():
    assert up_next([_job("h", "embed", "waiting")])[0].why == "in the queue"


def test_a_page_row_is_not_a_line_of_its_own():
    assert up_next([_job("run:step", "read-a-line", "waiting", parent_id="run")]) == []


def test_a_going_run_lists_its_stages_not_started_each_after_the_one_before_from_the_steps():
    status = {"steps": [{"steps": ["find-lines"], "job": "find-lines", "state": "done"},
                        {"steps": ["read-a-line"], "job": "read-a-line", "state": "running"},
                        {"steps": ["find-names-tag-words"], "job": "find-names-tag-words", "state": "waiting",
                         "child_id": "w3"},
                        {"steps": ["work-out-dates"], "job": "work-out-dates", "state": "waiting"}]}
    run = _job("rec", "run-a-recipe", "running", name="Run the recipe")
    items = up_next([run], {"rec": status})
    assert [(i.stage, i.after) for i in items] == [("Names", "Read"), ("Dates & Times", "Names")]
    assert items[0].id == "rec:w3" and items[0].why == "after Read"
    assert up_next([run]) == [], "no status read, no stages named"


def test_the_summary_carries_it():
    fields = app.openapi()["components"]["schemas"]["ActivitySummary"]["properties"]
    assert "up_next" in fields
