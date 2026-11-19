"""`recipes-run.steps.a-page-waits-for-its-inputs` and `recipes-run.steps.no-empty-done` (#6673): a step runs on a page only
when the steps it takes from finished on that page; a held page is waiting for the step that failed it, never done."""
from __future__ import annotations

from fichero_server.recipes import runner

LINES = {"card": "workflow", "job": "find-lines", "steps": ["lines"], "takes": ["page_image"], "gives": ["lines"]}
READ = {"card": "workflow", "job": "read-a-line", "steps": ["read"], "takes": ["lines"], "gives": ["line_readings"]}
CORRECT = {"card": "workflow", "job": "correct", "steps": ["correct"], "takes": ["line_readings"], "gives": ["corrected"]}
CARDS = [LINES, READ, CORRECT]


def test_a_page_whose_earlier_step_failed_is_held_and_the_others_go_on():
    steps = [{"state": "partial", "failed_ids": ["p2"]}, {"state": "waiting"}, {"state": "waiting"}]
    pages, waiting = runner._held_for_inputs(CARDS, steps, 1, ["p1", "p2", "p3"])
    assert pages == ["p1", "p3"]
    assert waiting == {"p2": "lines"}


def test_a_page_held_by_one_step_is_waiting_for_the_same_step_in_every_later_step():
    steps = [{"state": "partial", "failed_ids": ["p2"]},
             {"state": "waiting", "waiting_on": {"p2": "lines"}, "failed_ids": ["p3"]}, {"state": "waiting"}]
    pages, waiting = runner._held_for_inputs(CARDS, steps, 2, ["p1", "p2", "p3"])
    assert pages == ["p1"]
    assert waiting == {"p2": "lines", "p3": "read"}


def test_a_step_does_not_wait_on_a_step_it_takes_nothing_from():
    other = {**READ, "takes": ["page_image"]}
    steps = [{"state": "partial", "failed_ids": ["p2"]}, {"state": "waiting"}]
    pages, waiting = runner._held_for_inputs([LINES, {**other, "gives": ["x"]}], steps, 1, ["p1"])
    assert pages == ["p1"] and waiting == {}
    pages, waiting = runner._held_for_inputs([{**LINES, "gives": ["y"]}, other], steps, 1, ["p2"])
    assert pages == ["p2"] and waiting == {}


def test_the_summary_counts_done_waiting_and_failed_pages_per_step():
    step = {"state": "partial", "pages_tried": 5, "pages_lost": 2, "failed_ids": ["a", "b"], "waiting_on": {"c": "lines"}}
    assert runner._step_counts(step) == {"done": 3, "waiting": 1, "failed": 2}
    assert runner._step_counts({"state": "waiting", "waiting_on": {"c": "lines", "d": "lines"}}) == \
        {"done": 0, "waiting": 2, "failed": 0}


def test_a_batch_whose_pages_all_wait_leaves_the_step_waiting_not_done(monkeypatch):
    from fichero_server.execution import jobs

    monkeypatch.setattr(jobs, "save_detail", lambda *a, **k: None)
    monkeypatch.setattr(runner, "_step_pages", lambda *a, **k: ([], {"waiting_on": {"p1": "lines"}}, {}))
    for name in ("_blocked", "_await_downloads"):
        monkeypatch.setattr(runner, name, lambda *a: None)
    monkeypatch.setattr(runner, "_stop_asked", lambda *a: False)
    monkeypatch.setattr(runner, "_let_go_after_the_last_served_step", lambda *a: None)
    detail = {"runs": [READ], "steps": [{"state": "waiting"}], "batch_states": [None], "redo": []}
    runner._run_batch(None, "job", detail, {"units": ["p1"], "folder": "f"}, {}, "test", final=True)
    step = detail["steps"][0]
    assert step["state"] == "waiting" and step["why"] == "waiting for lines"
    assert runner._step_counts(step) == {"done": 0, "waiting": 1, "failed": 0}


def test_a_retry_flows_a_redone_page_through_the_steps_it_was_waiting_for():
    """`recipes-run.steps.retry-flows-through`: Retry is a new run, whose steps' failures are its own. The earliest failed step
    redoes its failed page; once it finishes, the page is no longer held, so it reaches every later step in order (the pages
    already done are filtered by `done.split_done`, as in a first run)."""
    first = [{"state": "partial", "failed_ids": ["p2"]}, {"state": "waiting", "waiting_on": {"p2": "lines"}}, {"state": "waiting"}]
    assert runner._held_for_inputs(CARDS, first, 1, ["p2"]) == ([], {"p2": "lines"})
    retry = [{"state": "done"}, {"state": "waiting"}, {"state": "waiting"}]  # a new run: its steps start clean
    assert runner._held_for_inputs(CARDS, retry, 1, ["p2"]) == (["p2"], {})
    retry[1] = {"state": "done"}
    assert runner._held_for_inputs(CARDS, retry, 2, ["p2"]) == (["p2"], {})


def test_a_retry_whose_earliest_step_fails_the_page_again_keeps_it_waiting():
    retry = [{"state": "partial", "failed_ids": ["p2"]}, {"state": "waiting", "waiting_on": {"p2": "lines"}}, {"state": "waiting"}]
    assert runner._held_for_inputs(CARDS, retry, 2, ["p2"]) == ([], {"p2": "lines"})
