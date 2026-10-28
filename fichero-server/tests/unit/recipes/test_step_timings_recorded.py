"""`recipes-run.timing.per-step-recorded` (#6215): each step of a recipe run carries started, ended, seconds, pages
done and seconds a page (the median of its pages' own times), the run its total, and the summary names the slowest
step. All read from rows (the jobs table, the workflow run's stored timeline), so the figures survive a restart."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fichero_server.execution import jobs
from fichero_server.recipes import run_view

T0 = datetime(2026, 10, 26, 22, 0, tzinfo=timezone.utc)


def _file(doc, ms, node="read", status="success"):
    return {"type": "file", "node_id": node, "document_id": doc, "file_path": f"/{doc}.png", "status": status,
            "started_at": T0.isoformat(), "running_at": T0.isoformat(), "duration_ms": ms}


def _row(db, job_id, start_s, end_s):
    jobs._ensure(db)
    db.execute("INSERT INTO jobs (id, kind, subject, state, attempts, started_by, created_at, started_at, finished_at) "
               "VALUES (?, 'workflow', 's', 'done', 0, 'workflow', ?, ?, ?)",
               [job_id, T0, T0 + timedelta(seconds=start_s), None if end_s is None else T0 + timedelta(seconds=end_s)])


def test_a_page_time_is_its_own_summed_over_nodes_and_the_median_is_used():
    timeline = {"steps": [_file("a", 2000), _file("a", 1000, node="lines"), _file("b", 4000), _file("c", 60000),
                          _file("d", 9999, status="failed"), {"type": "node", "duration_ms": 999999}]}
    assert sorted(run_view.page_seconds(timeline)) == [3.0, 4.0, 60.0]
    t = run_view.step_timing(T0, T0 + timedelta(seconds=70), run_view.page_seconds(timeline), T0)
    assert (t.seconds, t.pages_done, t.seconds_per_page) == (70.0, 3, 4.0)  # median, not the mean (22.3)


def test_a_running_step_counts_to_now_and_a_step_not_started_has_no_seconds():
    assert run_view.step_timing(T0, None, [], T0 + timedelta(seconds=5)).seconds == 5.0
    assert run_view.step_timing(None, None, [], T0).seconds is None


def test_a_two_step_run_carries_each_steps_timing_and_the_same_after_a_restart(db, monkeypatch):
    _row(db, "run", 0, 100)
    _row(db, "thread-lines", 1, 31)
    _row(db, "thread-read", 31, 99)
    import json

    from fichero_server.db import activity_records as records
    import fichero_server.workflows.run_account as accounts

    for thread, files in (("thread-lines", [_file("a", 10000, "lines"), _file("b", 20000, "lines")]),
                          ("thread-read", [_file("a", 30000), _file("b", 36000), _file("c", 2000)])):
        db.execute(f"INSERT INTO {records.RUNS} (id, workflow_id, workflow_name, status, progress_timeline) "
                   "VALUES (?, 'w', 'w', 'completed', ?)", [thread, json.dumps({"steps": files})])

    async def _no_account(*_a, **_k):
        return None

    monkeypatch.setattr(accounts, "run_account", _no_account)

    def status():
        return {"job_id": "run", "state": "done", "reason": None, "started_by": "person", "steps": [
            {"steps": ["find-lines"], "card": "workflow", "state": "done", "child_id": "thread-lines"},
            {"steps": ["read-a-line"], "card": "workflow", "state": "done", "child_id": "thread-read"},
            {"steps": ["find-names-tag-words"], "card": "names", "state": "not run", "child_id": None}]}

    first = asyncio.run(run_view.with_accounts(db, status()))
    lines, read, names = first["steps"]
    assert first["seconds"] == 100.0
    assert (lines["timing"].seconds, lines["timing"].pages_done, lines["timing"].seconds_per_page) == (30.0, 2, 15.0)
    assert (read["timing"].seconds, read["timing"].pages_done, read["timing"].seconds_per_page) == (68.0, 3, 30.0)
    assert "timing" not in names

    again = asyncio.run(run_view.with_accounts(db, status()))  # a fresh read from the rows: nothing kept in memory
    assert [s.get("timing") for s in again["steps"]] == [s.get("timing") for s in first["steps"]]

    words = run_view.slowest_words([run_view.RecipeRunStep(**s) for s in first["steps"]])
    assert words == f"Slowest step: {run_view.RecipeRunStep(**read).title}: 30 s a page on 3 pages"


def test_a_step_with_no_pages_of_its_own_is_named_by_its_whole_time():
    steps = [run_view.RecipeRunStep(steps=["find-names-tag-words"], card="names", state="done",
                                    timing=run_view.StepTiming(seconds=12.5))]
    assert run_view.slowest_words(steps).endswith(": 12.5 s")
    assert run_view.slowest_words([]) is None


def test_a_step_over_two_batches_spans_both_and_each_batch_has_its_own_figures(db, monkeypatch):
    """Per batch: a step run on two folders' batches is timed from the first batch's start to the last's end, its
    pages' median over both, and each batch carries its own figures, all from the rows (the run's checkpoint keeps
    each batch's job, `batch_jobs`)."""
    import json

    from fichero_server.db import activity_records as records
    import fichero_server.workflows.run_account as accounts

    _row(db, "run", 0, 200)
    _row(db, "read-1", 10, 40)
    _row(db, "read-2", 100, 160)
    for thread, files in (("read-1", [_file("a", 10000), _file("b", 20000)]),
                          ("read-2", [_file("c", 50000)])):
        db.execute(f"INSERT INTO {records.RUNS} (id, workflow_id, workflow_name, status, progress_timeline) "
                   "VALUES (?, 'w', 'w', 'completed', ?)", [thread, json.dumps({"steps": files})])

    async def _no_account(*_a, **_k):
        return None

    monkeypatch.setattr(accounts, "run_account", _no_account)
    status = {"job_id": "run", "state": "done", "reason": None, "started_by": "person", "steps": [
        {"steps": ["read-a-line"], "card": "workflow", "state": "done", "child_id": "read-2",
         "batch_jobs": [{"folder": "f1", "child_id": "read-1"}, {"folder": "f2", "child_id": "read-2"}]}]}

    (read,) = asyncio.run(run_view.with_accounts(db, status))["steps"]
    t = read["timing"]
    assert (t.seconds, t.pages_done, t.seconds_per_page) == (150.0, 3, 20.0)
    assert [(b.folder, b.seconds, b.pages_done, b.seconds_per_page) for b in t.batches] == [
        ("f1", 30.0, 2, 15.0), ("f2", 60.0, 1, 50.0)]


def test_a_run_of_many_batches_reads_every_timeline_at_once(db, monkeypatch):
    """Review of 1a6dd1c06: a step's timeline is read once for the whole run, never once a batch (a 40-folder run was 40
    SELECTs a step on every status poll)."""
    import json

    from fichero_server.db import activity_records as records
    import fichero_server.workflows.run_account as accounts

    _row(db, "run", 0, 1000)
    steps = []
    for step in ("lines", "read"):
        batch_jobs = []
        for i in range(12):
            job = f"{step}-{i}"
            _row(db, job, i * 10, i * 10 + 5)
            db.execute(f"INSERT INTO {records.RUNS} (id, workflow_id, workflow_name, status, progress_timeline) "
                       "VALUES (?, 'w', 'w', 'completed', ?)", [job, json.dumps({"steps": [_file(f"p{i}", 1000)]})])
            batch_jobs.append({"folder": f"f{i}", "child_id": job})
        steps.append({"steps": [step], "card": "workflow", "state": "done", "child_id": f"{step}-11",
                      "batch_jobs": batch_jobs})

    async def _no_account(*_a, **_k):
        return None

    monkeypatch.setattr(accounts, "run_account", _no_account)
    reads = []
    real_one, real_all = db.execute_fetchone, db.execute_fetchall
    monkeypatch.setattr(db, "execute_fetchone", lambda q, *a, **k: (reads.append(q), real_one(q, *a, **k))[1])
    monkeypatch.setattr(db, "execute_fetchall", lambda q, *a, **k: (reads.append(q), real_all(q, *a, **k))[1])
    out = asyncio.run(run_view.with_accounts(db, {"job_id": "run", "state": "done", "reason": None,
                                                  "started_by": "person", "steps": steps}))
    assert [len(s["timing"].batches) for s in out["steps"]] == [12, 12]
    assert all(s["timing"].pages_done == 12 for s in out["steps"])
    assert sum("progress_timeline" in q for q in reads) == 1


def test_pages_of_one_document_are_each_their_own_page():
    """A page inside a document carries its parent as `document_id` and itself as `page_id`: keyed by the parent, a
    real 86-page run read "Read each line: 6832.3 s a page on 1 page" (every page summed into one)."""
    from fichero_server.recipes.run_view import page_seconds

    timeline = {"steps": [{"type": "file", "status": "success", "duration_ms": 80_000, "document_id": "doc", "page_id": p,
                           "file_path": f"{p}.jpg"} for p in ("p1", "p2", "p3")]}
    assert page_seconds(timeline) == [80.0, 80.0, 80.0]


def _call(db, parent, provider="openai", model="gpt-5"):
    import json

    job_id = jobs._insert(db, "ask-a-model", "page", f"{provider}:{model}", "workflow")
    db.execute("UPDATE jobs SET parent_id = ?, state = 'done', detail = ? WHERE id = ?", [
        parent, json.dumps({"usage": [{"provider": provider, "model": model, "kind": "chat", "input_tokens": 1000,
                                       "output_tokens": 500, "total_tokens": 1500}]}), job_id])


def test_each_step_carries_its_cost_beside_its_seconds_6234(db, monkeypatch):
    """`recipes-run.timing.cost-per-step` (#6234): a step's cost is its calls' sum as the Activity tree rolls it up; one
    unpriced call makes it null; a step with no calls (local) has none, never a bare $0. The summary names the dearest."""
    import fichero_server.workflows.run_account as accounts

    _row(db, "run", 0, 100)
    for job, start, end in (("cloud", 0, 30), ("mixed", 30, 60), ("local", 60, 99)):
        _row(db, job, start, end)
    _call(db, "cloud")
    _call(db, "cloud")
    _call(db, "mixed")
    _call(db, "mixed", provider="nobody", model="a-model-with-no-price")

    async def _no_account(*_a, **_k):
        return None

    monkeypatch.setattr(accounts, "run_account", _no_account)
    status = {"job_id": "run", "state": "done", "reason": None, "started_by": "person", "steps": [
        {"steps": ["read-a-line"], "card": "workflow", "state": "done", "child_id": "cloud"},
        {"steps": ["find-names-tag-words"], "card": "names", "state": "done", "child_id": "mixed"},
        {"steps": ["find-lines"], "card": "workflow", "state": "done", "child_id": "local"}]}

    cloud, mixed, local = asyncio.run(run_view.with_accounts(db, status))["steps"]
    expected = jobs.tree(db, "cloud")["cost_usd"]
    assert expected and cloud["timing"].cost_usd == expected
    assert mixed["timing"].cost_usd is None, "one unpriced call: no sum, never a floor shown as the cost"
    assert local["timing"].cost_usd is None, "a local step says its time, never $0"

    words = run_view.dearest_words([run_view.RecipeRunStep(**s) for s in (cloud, mixed, local)])
    assert words == f"Dearest step: {run_view.RecipeRunStep(**cloud).title}: ${expected:.2f}"
    assert run_view.dearest_words([run_view.RecipeRunStep(**local)]) is None


def test_a_finished_steps_cost_is_read_once_not_on_every_poll_6234(db, monkeypatch):
    """A poll reads a finished batch's calls once: its cost never changes, so later polls read none of its page rows,
    however many pages it read (100k pages: O(pages) per poll would not scale; review b24). A running batch is read live."""
    _row(db, "done-batch", 0, 30)
    _row(db, "live-batch", 30, None)
    for _ in range(40):
        _call(db, "done-batch")
    _call(db, "live-batch")
    read = []
    real = db.execute_fetchall

    def counting(*a, **k):
        rows = real(*a, **k)
        read.append(len(rows))
        return rows

    monkeypatch.setattr(db, "execute_fetchall", counting)
    ended = jobs.times(db, ["done-batch", "live-batch"])
    first = jobs.cost_under(db, ["done-batch", "live-batch"], ended)
    read.clear()
    _call(db, "live-batch")

    again = jobs.cost_under(db, ["done-batch", "live-batch"], ended)

    assert sum(read) <= 2, read  # the live batch's two calls; none of the finished batch's 40
    assert first and again > first
