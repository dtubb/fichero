"""Start turns a saved recipe into the shipped workflows that run it, or refuses by name.

`source.recipe.makes-a-workflow`, `source.recipe.holds-no-second-copy`, `source.project.stays-local`,
`source.onboard.estimate-before-start` (#4950, #4951). Why it matters: a recipe is only a promise
until it becomes workflows the runner already knows; if a step's model could not reach its workflow
and Start ran the workflow anyway, the page would be read by a model the person never chose, and
nothing would say so. Pages must never leave the Mac in a project that keeps them local.
"""
from __future__ import annotations

from fichero_server.recipes.start import _preset, estimate, plan_start
from fichero_server.workflows.default_workflows import preset_workflow_id

LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"},
         "runs_on": "this-mac"}
READ = {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"},
        "runs_on": "this-mac"}
CORRECT = {"id": "correct", "job": "correct",
           "model": {"hf": "mlx-community/Qwen2.5-VL-7B-Instruct-4bit", "revision": "main"},
           "runs_on": "this-mac"}
CLOUD_CORRECT = {"id": "correct", "job": "correct", "model": {"cloud": "openai", "model": "gpt-5"},
                 "runs_on": "cloud:openai"}


def _recipe(*steps):
    return {"fichero_recipe": 1, "id": "t", "version": "0.1.0", "title": "t", "steps": list(steps)}


def test_a_project_with_no_recipe_cannot_start():
    """Start with nothing saved would run nothing and record a yes to nothing."""
    plan = plan_start(None, stays_local=True)
    assert plan["workflows"] == [] and "no recipe" in plan["refusals"][0]


def test_steps_become_shipped_workflows_by_name_with_the_steps_model():
    """Kraken finds its own lines before reading, so lines+read are one run of Transcribe (Kraken);
    the correction runs Paleographer Review with the step's MLX model. Workflows are referred to by
    their stable preset id, never copied, and each named workflow really is in the store."""
    plan = plan_start(_recipe(LINES, READ, CORRECT), stays_local=True)
    assert plan["refusals"] == []
    kraken, review = plan["workflows"]
    assert kraken["steps"] == ["lines", "read"] and kraken["workflow"] == "Transcribe (Kraken)"
    assert review["steps"] == ["correct"] and review["workflow"] == "Paleographer Review"
    assert (review["provider_override"], review["model_override"]) == (
        "omlx", "mlx-community/Qwen2.5-VL-7B-Instruct-4bit")
    for w in plan["workflows"]:
        assert w["workflow_id"] == preset_workflow_id(w["workflow"])
        assert _preset(w["workflow"]) is not None, f"{w['workflow']} is not a shipped workflow"


def test_a_reader_no_workflow_runs_is_refused_by_name_not_substituted():
    """The shipped Kraken workflow reads with McCATMuS; a recipe that picked another reader must not
    be read with McCATMuS behind its back."""
    other = {**READ, "model": {"zenodo": "10.5281/zenodo.21788410"}}
    plan = plan_start(_recipe(LINES, other), stays_local=True)
    assert any(r.startswith("step read:") and "21788410" in r for r in plan["refusals"])


def test_a_job_no_workflow_does_is_refused_by_name():
    """Nothing runs except workflows: a step with no workflow behind it is named, not skipped."""
    names = {"id": "names", "job": "find-names-tag-words",
             "model": {"spacy": "es_core_news_sm", "version": "bundled"}}
    plan = plan_start(_recipe(LINES, READ, names), stays_local=True)
    assert any("step names" in r and "find-names-tag-words" in r for r in plan["refusals"])


def test_a_project_that_keeps_pages_local_refuses_every_cloud_step():
    """`source.project.stays-local`: the refusal names the step and the rule; the same recipe in a
    project that allows the cloud plans the step with its provider and model."""
    local = plan_start(_recipe(LINES, READ, CLOUD_CORRECT), stays_local=True)
    assert any("step correct" in r and "off this Mac" in r for r in local["refusals"])
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


def test_a_step_with_no_model_refuses_start():
    """A gap the rules found (no model fits) must stop Start, not run the step's default."""
    gap = {"id": "correct", "job": "correct", "gap": "no model fits this step"}
    plan = plan_start(_recipe(LINES, READ, gap), stays_local=True)
    assert any("step correct has no model" in r for r in plan["refusals"])


def test_the_estimate_is_free_on_this_mac_and_never_guesses_an_unpriced_model():
    """Local runs cost nothing; a cloud model with no price is unknown (None), never zero."""
    local = estimate(plan_start(_recipe(LINES, READ), stays_local=True)["workflows"], 120)
    assert local["pages"] == 120 and local["total_cost_usd"] == 0.0
    cloud = {**CLOUD_CORRECT, "model": {"cloud": "openai", "model": "no-such-model-xyz"}}
    unpriced = estimate(plan_start(_recipe(LINES, READ, cloud), stays_local=False)["workflows"], 120)
    assert unpriced["runs"][-1]["cost_usd"] is None and unpriced["total_cost_usd"] is None
