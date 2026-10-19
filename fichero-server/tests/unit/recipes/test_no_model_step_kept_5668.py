"""A step with no model never refuses Start (#5668, found by the end-to-end onboarding run), tested to the spec:
`source.onboard.no-model-step-kept` (docs/contributor_manual/specs/source/models-chains-and-projects.md):
"a step with no model stays in the recipe marked 'needs a model'; steps that do not depend on it run, and those
that do wait with that reason."

WHY: choosing Organise brings Split into entries, a text model's job; on a Mac with no text model its step had no
model, the recipe check refused it, and Start was refused for everything, Read and Names included.
"""

from __future__ import annotations

from fichero_server.recipes.start import plan_start
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture: no model installed)
from tests.unit.recipes.test_recipe_execution_to_spec import pages  # noqa: F401  (fixture: the project's pages)

STAGE_JOBS = ["find-lines", "read-a-line", "find-documents-in-a-folder", "split-into-entries", "find-names-tag-words"]


def test_organise_with_no_text_model_here_starts_read_and_names_and_lists_entries_as_needing_a_model(
        client, mac, pages):
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"],
               "jobs": STAGE_JOBS, "cloud_allowed": False}
    recipe = client.post("/api/recipes/assemble", json=answers).json()
    entries = next(s for s in recipe["steps"] if s["job"] == "split-into-entries")
    assert entries["model"] is None  # nothing on this Mac does it: the premise
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200

    plan = client.get("/api/recipes/project/start").json()

    assert plan["refusals"] == [], plan["refusals"]
    (kept,) = [s for s in plan["skipped"] if s["step"] == entries["id"]]
    assert "has no model" in kept["why"] and kept["fix"] == "choose-model"
    ran = {sid for run in plan["runs"] for sid in run["steps"]}
    jobs_of = {s["id"]: s["job"] for s in recipe["steps"]}
    assert {"read-a-line", "find-names-tag-words", "find-documents-in-a-folder"} <= {jobs_of[s] for s in ran}
    assert entries["id"] not in ran


def test_a_step_that_needs_what_a_model_less_step_makes_waits_for_it():
    """"… those that do wait with that reason": Names takes the reading; with the only reader model-less, Names
    is skipped saying it waits for Read, and Find Lines (which needs neither) still runs."""
    recipe = {"fichero_recipe": 1, "id": "t/r", "version": "0.1.0", "title": "t", "steps": [
        {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}},
        {"id": "read", "job": "read-a-line", "model": None,
         "problem": {"sentence": "Fichero has no model for “Read a line” yet."}},
        {"id": "names", "job": "find-names-tag-words", "model": {"spacy": "es_core_news_sm", "version": "bundled"}},
    ]}

    plan = plan_start(recipe, stays_local=True)

    assert plan["refusals"] == [], plan["refusals"]
    why = {s["step"]: s["why"] for s in plan["skipped"]}
    assert "has no model" in why["read"]
    assert why["names"] == ("Find names waits for Read each line, which has no model yet: choose a model for Read each "
                           "line, and Find names runs after it")  # by title, what to do said (#5801)
    assert [r["steps"] for r in plan["runs"]] == [["lines"]]
