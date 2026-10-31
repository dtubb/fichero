"""Start turns a saved recipe into the shipped workflows that run it, or refuses by name.

`source.recipe.makes-a-workflow`, `source.recipe.holds-no-second-copy`, `source.project.stays-local`,
`source.onboard.estimate-before-start` (#4950, #4951). Why it matters: a recipe is only a promise
until it becomes workflows the runner already knows; if a step's model could not reach its workflow
and Start ran the workflow anyway, the page would be read by a model the person never chose, and
nothing would say so. Pages must never leave the Mac in a project that keeps them local.
"""
# ruff: noqa: F811  (the `pages` fixture is imported and taken as an argument: pytest's idiom)
from __future__ import annotations

import pytest

from fichero_server.recipes import start
from fichero_server.recipes.start import _preset, estimate, plan_start
from fichero_server.workflows.default_workflows import preset_workflow_id
from tests.unit.recipes.test_recipe_execution_to_spec import pages  # noqa: F401,E402  (fixture: two photographs in the project)

LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"},
         "runs_on": "this-mac"}
READ = {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"},
        "runs_on": "this-mac"}
CORRECT = {"id": "correct", "job": "correct",
           "model": {"hf": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit", "revision": "main"},
           "runs_on": "this-mac"}
CLOUD_CORRECT = {"id": "correct", "job": "correct", "model": {"cloud": "openai", "model": "gpt-5"},
                 "runs_on": "cloud:openai"}


@pytest.fixture(autouse=True)
def the_steps_local_models_are_on_this_mac(monkeypatch):
    """These tests pin how steps map to workflows; whether this Mac can serve a step's local model,
    and the refusal when it cannot, is test_local_model_choice.py's (#5520)."""
    monkeypatch.setattr(start, "local_models_this_mac_cannot_serve", lambda runs, names=None: [])
    monkeypatch.setattr(start, "local_models_to_download", lambda runs: [])
    monkeypatch.setattr(start, "provider_without_key", lambda step: None)  # keys: test_missing_key_never_substitutes_5364.py


def _recipe(*steps):
    return {"fichero_recipe": 1, "id": "t", "version": "0.1.0", "title": "t", "steps": list(steps)}


def test_a_project_with_no_recipe_cannot_start():
    """Start with nothing saved would run nothing and record a yes to nothing."""
    plan = plan_start(None, stays_local=True)
    assert plan["workflows"] == [] and "no recipe" in plan["refusals"][0]


def test_steps_become_shipped_workflows_by_name_with_the_steps_model():
    """Kraken finds its own lines before reading, so lines+read are one run of Transcribe (Kraken),
    told which reader to use; the correction runs Review the Reading with the step's MLX model.
    Workflows are referred to by their stable preset id, never copied, and each named workflow
    really is in the store."""
    plan = plan_start(_recipe(LINES, READ, CORRECT), stays_local=True)
    assert plan["refusals"] == []
    kraken, review = plan["workflows"]
    assert kraken["steps"] == ["lines", "read"] and kraken["workflow"] == "Transcribe (Kraken)"
    assert (kraken["provider_override"], kraken["model_override"]) == ("kraken", "kraken-mccatmus")
    assert review["steps"] == ["correct"] and review["workflow"] == "Review the Reading"
    assert (review["provider_override"], review["model_override"]) == (
        "omlx", "mlx-community/Qwen2.5-VL-7B-Instruct-4bit")
    for w in plan["workflows"]:
        assert w["workflow_id"] == preset_workflow_id(w["workflow"])
        assert _preset(w["workflow"]) is not None, f"{w['workflow']} is not a shipped workflow"


def test_the_recipes_pinned_reader_is_the_one_the_run_reads_with():
    """Gap 2 (#4951): the shipped workflow names McCATMuS, but a recipe pinned to CATMuS Medieval
    must run CATMuS Medieval, passed as the run's Kraken reader, not the graph's."""
    medieval = {**READ, "model": {"zenodo": "10.5281/zenodo.12743230"}}
    [run] = plan_start(_recipe(LINES, medieval), stays_local=True)["workflows"]
    assert (run["provider_override"], run["model_override"]) == ("kraken", "kraken-catmus-medieval")


def test_a_repository_reader_runs_as_itself_and_an_unfetchable_one_is_refused_by_name():
    """A reader in Kraken's repository (PP-OCRv6 by its DOI) is planned under its own id, never
    swapped for a catalogue reader behind the recipe's back; a reader Kraken cannot fetch at all
    (a Hugging Face pin) is refused by name."""
    repo = {**READ, "model": {"zenodo": "10.5281/zenodo.21788410"}}
    plan = plan_start(_recipe(LINES, repo), stays_local=True)
    assert not plan["refusals"], plan["refusals"]
    assert any(w.get("model_override") == "kraken-zenodo-21788410" for w in plan["workflows"])
    hf = {**READ, "model": {"hf": "someone/kraken-reader", "revision": "abc"}}
    skipped = plan_start(_recipe(LINES, hf), stays_local=True)["skipped"]
    assert any(s["step"] == "read" and s["why"].startswith("Read each line:") for s in skipped), skipped


def test_a_job_no_card_runs_is_skipped_by_name():
    """`source.recipe.step-skipped-says-why` (#5390; was: refused). A step no card runs is skipped and
    named; the others still run. Names with a spaCy pin now run as the entity workflow with spaCy."""
    names = {"id": "names", "job": "find-names-tag-words",
             "model": {"spacy": "es_core_news_sm", "version": "bundled"}}
    links = {"id": "links", "job": "link-to-authorities", "model": {"builtin": "links"}}
    plan = plan_start(_recipe(LINES, READ, names, links), stays_local=True)
    # Named by the step's title, never its job id, since 638060a4b (#5801).
    assert any(s["step"] == "links" and "no card runs it yet" in s["why"] and "link-to-authorities" not in s["why"]
               for s in plan["skipped"]), plan["skipped"]
    assert plan["workflows"][-1]["workflow"] == "Extract Entities"
    assert (plan["workflows"][-1]["provider_override"], plan["workflows"][-1]["model_override"]) == (
        "spacy", "es_core_news_sm")


def test_work_out_dates_runs_the_extract_date_workflow_with_no_model():
    """#5514: `work-out-dates` was declared and never run. It runs the shipped Work Out Dates
    workflow, the same rule extractor as the Extract Date tool (one code path), and needs no model.
    A recipe asking for a Julian/Gregorian switch is skipped and says why, never read as Gregorian."""
    names = {"id": "names", "job": "find-names-tag-words",
             "model": {"spacy": "es_core_news_sm", "version": "bundled"}}
    dates = {"id": "dates", "job": "work-out-dates"}
    plan = plan_start(_recipe(LINES, READ, names, dates), stays_local=True)
    run = plan["workflows"][-1]
    assert run["workflow"] == "Work Out Dates" and run["steps"] == ["dates"]
    assert run["workflow_id"] == preset_workflow_id("Work Out Dates")
    preset = _preset("Work Out Dates")
    assert preset is not None and [n["tool"] for n in preset["nodes"]] == ["files", "date_extract"]

    switching = {**dates, "settings": {"calendars": ["julian", "gregorian"], "switch": "1582-10-15"}}
    plan = plan_start(_recipe(LINES, READ, names, switching), stays_local=True)
    assert any(s["step"] == "dates" and "Gregorian dates only" in s["why"] for s in plan["skipped"])


def test_a_project_that_keeps_pages_local_refuses_every_cloud_step():
    """`source.project.stays-local`: the refusal names the step and the rule; the same recipe in a
    project that allows the cloud plans the step with its provider and model."""
    local = plan_start(_recipe(LINES, READ, CLOUD_CORRECT), stays_local=True)
    assert any(s["step"] == "correct" and "off this Mac" in s["why"] for s in local["skipped"])
    allowed = plan_start(_recipe(LINES, READ, CLOUD_CORRECT), stays_local=False)
    assert allowed["refusals"] == []
    assert (allowed["workflows"][-1]["provider_override"], allowed["workflows"][-1]["model_override"]) == (
        "openai", "gpt-5")


def test_training_is_offered_never_run_at_start():
    """`source.recipe.train-never-automatic`: a train step waits to be offered."""
    train = {"id": "train-a-model", "job": "train-a-model", "offered_when": {"corrected_lines_at_least": 2000}}
    plan = plan_start(_recipe(LINES, READ, train), stays_local=True)
    assert plan["refusals"] == [] and plan["offered"] == ["train-a-model"]
    assert all("train-a-model" not in w["steps"] for w in plan["workflows"])


def test_a_recipe_that_fails_the_check_never_starts():
    """Start validates with the same check as everywhere else: a key that would carry
    credentials refuses it, whatever maps."""
    plan = plan_start({**_recipe(LINES, READ), "api_key": "sk-x"}, stays_local=True)
    assert any("never code or credentials" in r for r in plan["refusals"])


def test_a_step_with_no_model_is_skipped_never_run_with_a_default():
    """A gap the rules found (no model fits) skips the step, named with why (#5390; was: refused Start),
    and never runs the step's default."""
    gap = {"id": "correct", "job": "correct", "gap": "no model fits this step"}
    plan = plan_start(_recipe(LINES, READ, gap), stays_local=True)
    assert any("Review the reading has no model" in s["why"] for s in plan["skipped"])
    assert all("correct" not in r["steps"] for r in plan["runs"])


def test_the_estimate_is_free_on_this_mac_and_never_guesses_an_unpriced_model():
    """Local runs cost nothing; a cloud model with no price is unknown (None), never zero."""
    local = estimate(plan_start(_recipe(LINES, READ), stays_local=True)["workflows"], 120)
    assert local["pages"] == 120 and local["total_cost_usd"] == 0.0
    cloud = {**CLOUD_CORRECT, "model": {"cloud": "openai", "model": "no-such-model-xyz"}}
    unpriced = estimate(plan_start(_recipe(LINES, READ, cloud), stays_local=False)["workflows"], 120)
    assert unpriced["runs"][-1]["cost_usd"] is None and unpriced["total_cost_usd"] is None


PREP = {"id": "prep", "job": "prepare-the-image", "model": {"builtin": "image-preparer"}}


def test_wide_a_plan_whose_only_step_is_a_card_has_a_run_and_no_refusal():
    """`wide.start.enabled-on-any-run` (engine half, #5806): Prepare Images alone is an `OTHER_CARDS` card, not a workflow; the
    plan still has a run and no refusal, so Start is enabled on `runs`, never on `workflows`."""
    plan = plan_start(_recipe(PREP), stays_local=True)
    assert plan["refusals"] == [], plan["refusals"]
    assert plan["workflows"] == [] and [r["card"] for r in plan["runs"]] == ["prepare"]
    assert plan["skipped"] == [], "nothing is skipped: the sentence 'every step is skipped' would be false"
    assert plan["runs"][0]["operations"] == ["straighten", "crop", "clarity"], "the card says which operations it runs"


def test_wide_a_stage_ticked_after_the_first_start_is_in_the_next_plan(client, db, pages, tmp_path):
    """`wide.prepare.ticked-later-still-runs` (#5706, section F cause 4): saving a setup whose recipe gained steps after the first
    Start writes those steps into the proposal, so `only` holds them and the plan runs them; a stage taken out leaves it."""
    from pathlib import Path

    from fichero_server.recipes.project import read_proposed, write_proposed, write_start
    from tests.unit.recipes.test_recipe_execution_to_spec import _recipe as recipe_of
    from tests.unit.recipes.test_recipe_execution_to_spec import _save

    library = Path(db.path).parent
    before = recipe_of(tmp_path, LINES, READ)
    _save(client, before)
    write_start(library, {"started_at": "2026-10-31T09:00:00", "recipe_id": "t/run", "workflows": [], "pages": 0})
    assert read_proposed(library) is None

    _save(client, recipe_of(tmp_path, LINES, READ, PREP))
    assert read_proposed(library)["steps"] == ["prep"], "the step the recipe gained is proposed"
    plan = client.get("/api/recipes/project/start").json()
    assert [r["steps"] for r in plan["runs"]] == [["prep"]], plan["runs"]
    assert plan["refusals"] == []

    _save(client, recipe_of(tmp_path, LINES, READ))  # the stage is taken out again
    assert read_proposed(library) is None

    write_proposed(library, None)
    unstarted_library_recipe = recipe_of(tmp_path, LINES, READ, PREP)
    write_start(library, None)  # before the first yes the whole recipe runs and nothing is proposed
    _save(client, unstarted_library_recipe)
    assert read_proposed(library) is None


def test_wide_run_this_step_plans_one_stages_steps_alone_over_the_whole_project(client, db, pages, tmp_path):
    """`wide.output.run-this-step` (#5806): Start with `steps` is the same plan limited to those step ids, over the whole project,
    so a stage's page runs just its step without unticking the rest; an id the recipe lacks is refused in words."""
    from tests.unit.recipes.test_recipe_execution_to_spec import _recipe as recipe_of
    from tests.unit.recipes.test_recipe_execution_to_spec import _save

    _save(client, recipe_of(tmp_path, PREP, LINES, READ))
    whole = client.get("/api/recipes/project/start").json()
    assert [r["card"] for r in whole["runs"]] == ["prepare", "workflow"]
    one = client.get("/api/recipes/project/start", params={"steps": "prep"})
    assert one.status_code == 200, one.text
    plan = one.json()
    assert [r["steps"] for r in plan["runs"]] == [["prep"]] and plan["refusals"] == []
    assert plan["estimate"]["pages"] == whole["estimate"]["pages"], "over the whole project, not a sample"
    missing = client.get("/api/recipes/project/start", params={"steps": "nope"})
    assert missing.status_code == 422 and "no step nope" in missing.text
    refused = client.post("/api/recipes/project/start", json={"steps": ["nope"]})
    assert refused.status_code == 422 and "no step nope" in refused.text
