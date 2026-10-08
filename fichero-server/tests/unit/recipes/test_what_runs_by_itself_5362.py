"""What runs by itself, one engine read (#5362), tested to the spec
(docs/contributor_manual/specs/ui/activity-and-automatic-work.md, `activity.auto.what-runs-by-itself`).

The read must say what the import and the correction then do: here it is read through
`GET /api/recipes/project/automatic`, and an import after Start is checked to run exactly the steps it said.
The models are stubbed at their boundary only, as in `test_recipe_execution_to_spec.py` (its fixtures are used).
"""
# ruff: noqa: F811 -- pytest fixtures imported from test_recipe_execution_to_spec are named as test arguments
from __future__ import annotations

from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures: engine, pages)
    _finished,
    _import,
    _recipe,
    _runs,
    _start,
    _steps,
    _wait,
    engine,
    pages,
)


def _automatic(client):
    r = client.get("/api/recipes/project/automatic")
    assert r.status_code == 200, r.text
    return r.json()


def _by_job(entries):
    return {e["job"]: e for e in entries if e["job"]}


def test_activity_auto_what_runs_by_itself__says_what_an_import_and_a_correction_run(
        client, db, pages, tmp_path, engine):
    """`activity.auto.what-runs-by-itself`: the project says what runs on an import and on a correction, and
    why. Before Start the recipe does not run on an import, and the read says so; after Start, with two steps
    ticked under What runs by itself, an import runs those two and the read named them, the others said
    skipped with why. Pictures and search always run; a correction re-embeds the page."""
    steps = _steps(tmp_path)[1:3] + [_steps(tmp_path)[5]]  # lines, read, export
    recipe = _recipe(tmp_path, *steps)
    answers = {"purpose": "transcribe", "cloud_allowed": True}
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200

    before = _automatic(client)
    on_add = _by_job(before["on_add"])
    assert on_add["thumbnail"]["runs"] is True and on_add["embed"]["runs"] is True
    assert on_add["run-a-recipe"]["runs"] is False and "Start has not been pressed" in on_add["run-a-recipe"]["why"]
    on_correction = _by_job(before["on_correction"])
    assert on_correction["make-a-vector"]["runs"] is True
    assert on_correction["read-names-again"]["runs"] == on_add["nlp-draft"]["runs"]

    _finished(client, _start(client))
    answers["automatic"] = {"runs": True, "steps": ["lines", "read"]}
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200

    after = _automatic(client)
    runs = [e["steps"] for e in after["on_add"] if e["runs"] and e["steps"]]
    assert runs == [["lines", "read"]], after
    skipped = [e for e in after["on_add"] if e["job"] is None]
    assert [e["steps"] for e in skipped] == [["export"]] and "What runs by itself" in skipped[0]["why"]
    assert "run-a-recipe" not in _by_job(after["on_add"])

    _import(client, tmp_path, "arrived.png")
    assert _wait(lambda: any(r["documents"] is not None for r in _runs(client)))
    row = next(r for r in _runs(client) if r["documents"] is not None)
    assert [s["steps"] for s in row["steps"]] == runs, "the import ran what the read said"


def test_activity_auto_what_runs_by_itself__nothing_runs_automatically_is_said(client, db, pages, tmp_path, engine):
    """With Nothing runs automatically, the read says the recipe does not run on an import, and why."""
    recipe = _recipe(tmp_path, *_steps(tmp_path)[1:3])
    answers = {"purpose": "transcribe", "cloud_allowed": True}
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200
    _finished(client, _start(client))
    answers["automatic"] = {"runs": False}
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200

    entry = _by_job(_automatic(client)["on_add"])["run-a-recipe"]
    assert entry["runs"] is False and "Nothing runs automatically" in entry["why"]
