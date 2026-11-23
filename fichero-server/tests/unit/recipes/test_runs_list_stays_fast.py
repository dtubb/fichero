"""#6812: the list of runs reads an ended run's timeline once, not on every poll (`recipes-run.engine.runs-list-answers-while-a-run-goes`)."""
from __future__ import annotations

import asyncio
import json

from fichero_server.api.routes.system import recipes
from fichero_server.execution import jobs
from fichero_server.recipes import run_view, runner


def _ended_run(db, n):
    run_id = jobs._insert(db, runner.KIND, f"project-{n}", None, "owner")
    card = {"steps": ["read"], "card": "workflow"}
    step = jobs._insert(db, "workflow", f"w{n}", None, "owner")
    db.execute("UPDATE jobs SET state = 'done', detail = ? WHERE id = ?",
               [json.dumps({"runs": [card], "steps": [{**card, "state": "done", "child_id": step}]}), run_id])
    db.execute("UPDATE jobs SET state = 'done', parent_id = ? WHERE id = ?", [run_id, step])
    return run_id


def test_the_list_of_runs_reads_no_ended_runs_timeline_twice(db, monkeypatch):
    for n in range(20):
        _ended_run(db, n)
    reads = []
    real = jobs.work_under
    monkeypatch.setattr(jobs, "work_under", lambda db_, ids: reads.append(list(ids)) or real(db_, ids))

    first = asyncio.run(recipes.recipe_runs(db=db))
    assert len(first.items) == 20
    assert sum(len(r) for r in reads) == 20, "the first poll reads each ended run's timeline once"
    reads.clear()
    second = asyncio.run(recipes.recipe_runs(db=db))
    assert len(second.items) == 20
    assert reads == [], "the second poll reads none of them"
    assert [i.seconds for i in second.items] == [i.seconds for i in first.items]
    assert run_view._ENDED_TIMINGS, "the ended runs' timings are what was kept"
