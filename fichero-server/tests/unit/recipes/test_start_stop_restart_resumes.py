"""A recipe run can be stopped (or lost with the engine) and started again: Start again skips what is done and finishes
(owner release condition 2026-10-24; `source.recipe.done-is-not-redone`, #5390; `activity.recipe-run.stop-reaches-its-step`).

Through the public surface with the real scheduler, as test_stop_reaches_inline_steps_5609 does: two fixture pages, the
lines + read step (the stub Kraken reader counts the pages it reads), then the entries step (counted per page). The run is
held on the entries step's first page and then (a) stopped, or (b) lost as an engine that dies leaves it (its worker gone,
its row left running), and the engine's own `resume` runs. Started again, the read step reads no page again, the entries
step splits only the page it had not split, and the run ends done.
"""
# ruff: noqa: F811 -- pytest fixtures imported from the sibling tests are named as test arguments
from __future__ import annotations

from fichero_server.execution import jobs
from fichero_server.workflows.tools import diary_entries
from tests.unit.recipes.test_diary_entries_step import ENTRIES, _entries, splitter  # noqa: F401  (fixture)
from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _recipe,
    _run_status,
    _start,
    _wait,
    engine,
    pages,
)
from tests.unit.recipes.test_stop_reaches_inline_steps_5609 import LINES, READ, Gate, _save, _stop


def test_stopped_then_started_again_skips_what_is_done_and_finishes(client, db, pages, tmp_path, engine, splitter,
                                                                     monkeypatch, with_material):
    gate = Gate(monkeypatch, diary_entries, "split_page_into_entries")
    split = _pages_split(monkeypatch)
    try:
        _save(client, _recipe(tmp_path, LINES, READ, ENTRIES))
        first = _start(client)
        assert gate.entered.wait(60), _run_status(client, first)
        assert _stop(client, first) == "stopping"
        gate.release.set()
        assert _finished(client, first)["state"] == "cancelled"
    finally:
        gate.release.set()
    read_before, split_before = sorted(engine.read), list(split)
    assert read_before and len(split_before) == 1

    run = _finished(client, _start(client))

    assert run["state"] == "done", run
    assert sorted(engine.read) == read_before, "the read step read a page it had already read"
    assert len(split) == len(set(split)) and split_before[0] in split, f"pages split {split}: a split page was split again"
    assert {len(_entries(db, page)) for page in set(split)} == {2}, "a page holds its entries twice"


def _pages_split(monkeypatch) -> list[str]:
    """The page of every call that writes a page's entries (wraps whatever is in place, the Gate included)."""
    seen: list[str] = []
    inner = diary_entries.split_page_into_entries

    async def counted(db, page, *args, **kwargs):
        seen.append(page.id)
        return await inner(db, page, *args, **kwargs)

    monkeypatch.setattr(diary_entries, "split_page_into_entries", counted)
    return seen


class _EngineDied(BaseException):
    """The worker thread ends as the engine's death ends it: nothing in the run gets to write its row."""


def test_lost_with_the_engine_then_resumed_skips_what_is_done_and_finishes(client, db, pages, tmp_path, engine,
                                                                            splitter, monkeypatch, with_material):
    real = diary_entries.split_page_into_entries
    calls = {"n": 0}

    def dies_on_the_first_page(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _EngineDied()
        return real(*args, **kwargs)

    monkeypatch.setattr(diary_entries, "split_page_into_entries", dies_on_the_first_page)
    split = _pages_split(monkeypatch)
    _save(client, _recipe(tmp_path, LINES, READ, ENTRIES))
    job_id = _start(client)
    assert _wait(lambda: calls["n"] >= 1), _run_status(client, job_id)
    read_before = sorted(engine.read)
    assert read_before

    # The engine starts again: a fresh scheduler, and its own resume of the rows the dead one left.
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ? AND state IN ('running', 'failed')", [job_id])
    jobs.resume(db)
    r = client.post(f"/api/activity/jobs/{job_id}/retry")
    assert r.status_code in (200, 409), r.text  # Resume if the engine set it aside; already going again otherwise
    run = _finished(client, job_id)

    assert run["state"] == "done", run
    assert sorted(engine.read) == read_before, "the read step read a page again after the engine came back"
    again = split[1:]  # the first call died before it wrote: that page is split again, once; every other page once
    assert len(again) == len(set(again)) and split[0] in again, f"pages split after the restart: {again}"
    assert {len(_entries(db, page)) for page in set(again)} == {2}, "a page holds its entries twice"

