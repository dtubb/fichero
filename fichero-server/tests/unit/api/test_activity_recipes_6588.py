"""The Recipes view (`activity.window.recipes`, decision 37, #6588; the owner 2026-11-15: "so we can see what recipes worked").

Acceptance: two runs of one recipe, one with Kraken (3 of 20 failed) and one with Qwen (0 failed), read 15% and 0% failed
with each step's model; the recipe's row sums them."""
from __future__ import annotations

from datetime import timedelta

from fichero_server.core.timeutil import utc_now
from fichero_server.db import activity_records as records
from fichero_server.execution import jobs


def _run(db, thread_id, *, model, failed, minutes_ago):
    t0 = (utc_now() - timedelta(minutes=minutes_ago)).replace(tzinfo=None)
    db.execute(f"INSERT INTO {records.RUNS} (id, workflow_id, workflow_name, status, started_at, completed_at) "
               "VALUES (?, 'wf-letters', 'Read the letters', 'completed', ?, ?)", [thread_id, t0, t0 + timedelta(minutes=4)])

    def row(job_id, kind, parent, state, mdl=None, start=0, end=None):
        db.execute("INSERT INTO jobs (id, kind, subject, model, state, attempts, started_by, created_at, started_at, "
                   "finished_at, parent_id) VALUES (?, ?, ?, ?, ?, 0, 'person', ?, ?, ?, ?)",
                   [job_id, kind, job_id, mdl, state, t0, t0 + timedelta(seconds=start),
                    None if end is None else t0 + timedelta(seconds=end), parent])

    row(thread_id, "workflow", None, "done", end=240)
    row(f"{thread_id}:read", "workflow-step", thread_id, "done", end=240)
    for page in range(20):
        state = "failed" if page < failed else "done"
        row(f"{thread_id}:p{page}", "t-read-page", f"{thread_id}:read", state, mdl=model, start=page * 10, end=page * 10 + 4)


def test_two_runs_of_a_recipe_compare_by_failed_share_and_model(db, monkeypatch):
    from fichero_server.workflows import activity_recipes

    monkeypatch.setitem(jobs.KINDS, "t-read-page", jobs.Kind(run=lambda db, subject: None, model=None, name="Read a page"))
    jobs._ensure(db)
    _run(db, "run-kraken", model="kraken:catmus", failed=3, minutes_ago=60)
    _run(db, "run-qwen", model="ollama:qwen2-vl", failed=0, minutes_ago=10)

    (recipe,) = activity_recipes.recipes(db)
    assert recipe["name"] == "Read the letters" and recipe["run_count"] == 2
    newest, oldest = recipe["runs"]
    assert newest["id"] == "run-qwen" and newest["failed_pct"] == 0.0 and newest["pages_done"] == 20
    assert oldest["id"] == "run-kraken" and oldest["failed_pct"] == 15.0 and oldest["pages_failed"] == 3
    assert oldest["steps"][0]["model"] == "kraken:catmus" and newest["steps"][0]["model"] == "ollama:qwen2-vl"
    assert oldest["steps"][0]["seconds_per_page"] == 4.0, "the median of its pages' own times"
    assert recipe["pages_done"] == 37 and recipe["pages_failed"] == 3


def test_the_route_answers_the_view(client, db, monkeypatch):
    monkeypatch.setitem(jobs.KINDS, "t-read-page", jobs.Kind(run=lambda db, subject: None, model=None, name="Read a page"))
    jobs._ensure(db)
    _run(db, "run-1", model="kraken:catmus", failed=1, minutes_ago=5)
    answer = client.get("/api/activity/recipes?days=7")
    assert answer.status_code == 200, answer.text
    assert answer.json()["recipes"][0]["runs"][0]["steps"][0]["pages_failed"] == 1


def test_a_recipe_runs_steps_are_its_steps_in_order_under_the_project(client, db, monkeypatch):
    """WHY (owner 2026-11-16): Detect Segments, Read Lines and Transcribe listed as three recipes when they were the steps
    of one recipe run. A workflow run whose job hangs under a `run-a-recipe` job is a STEP of that recipe run, in the
    order they ran, and the recipe runs list under the project's recipe; a workflow run on its own stays its own recipe."""
    from fichero_server.workflows import activity_recipes

    monkeypatch.setitem(jobs.KINDS, "t-read-page", jobs.Kind(run=lambda db, subject: None, model=None, name="Read a page"))
    jobs._ensure(db)
    t0 = (utc_now() - timedelta(minutes=30)).replace(tzinfo=None)
    db.execute("INSERT INTO jobs (id, kind, subject, state, attempts, started_by, created_at, started_at) "
               "VALUES ('recipe-1', 'run-a-recipe', 'all', 'done', 0, 'person', ?, ?)", [t0, t0])
    for order, (thread_id, name) in enumerate([("s-segments", "Detect Segments"), ("s-lines", "Read Lines"),
                                               ("s-htr", "Transcribe HTR")]):
        _run(db, thread_id, model="kraken:blla", failed=order, minutes_ago=30 - order)
        db.execute(f"UPDATE {records.RUNS} SET workflow_name = ? WHERE id = ?", [name, thread_id])
        db.execute("UPDATE jobs SET parent_id = 'recipe-1' WHERE id = ?", [thread_id])
    _run(db, "solo", model="ollama:qwen2-vl", failed=0, minutes_ago=5)

    found = {r["name"]: r for r in activity_recipes.recipes(db)}

    project = found[activity_recipes.project_recipe_name(db)]
    (recipe_run,) = project["runs"]
    assert recipe_run["id"] == "recipe-1"
    assert [s["name"] for s in recipe_run["steps"]] == ["Detect Segments", "Read Lines", "Transcribe HTR"]
    assert [s["pages_failed"] for s in recipe_run["steps"]] == [0, 1, 2]
    assert recipe_run["steps"][0]["model"] == "kraken:blla"
    assert recipe_run["pages_failed"] == 3 and recipe_run["pages_done"] == 57
    assert "Detect Segments" not in found and "Read Lines" not in found, "a step is never a recipe of its own"
    assert found["Read the letters"]["run_count"] == 1, "a workflow run on its own stays its own recipe"
    answer = client.get("/api/activity/recipes?days=7")
    assert answer.status_code == 200, answer.text
    listed = {r["name"]: r for r in answer.json()["recipes"]}
    assert [s["name"] for s in listed[project["name"]]["runs"][0]["steps"]] == [
        "Detect Segments", "Read Lines", "Transcribe HTR"]
