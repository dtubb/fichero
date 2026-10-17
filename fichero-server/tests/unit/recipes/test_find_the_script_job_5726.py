"""`source.job.find-the-script` (#5726, R1 2026-10-17): the classify step is a job a recipe can name.

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY: `classify_script` existed only inside Transcribe
(Auto-Detect); a project whose script is unknown had to run a whole transcription to learn it. The shipped workflow Classify
Script is now a recipe job: registered with a place in the step order and a topic, planned with the step's own model, and in no
purpose's default steps.
"""
from __future__ import annotations

from fichero_server.recipes import start
from fichero_server.recipes.assemble import PURPOSE_STEPS, STEP_ORDER
from fichero_server.recipes.jobs import get_job
from fichero_server.recipes.start import plan_start

JOB = "find-the-script"
STEP = {"id": "script", "job": JOB, "model": {"cloud": "anthropic", "model": "claude"}, "runs_on": "cloud:anthropic"}


def test_the_job_is_registered_with_a_place_in_the_order_and_a_topic():
    """source.job.find-the-script: "registered with a place in the step order and a topic"; takes the page image, gives the script."""
    job = get_job(JOB)
    assert job is not None and job.topic is not None and job.topic.kind == "job"
    assert job.takes == frozenset({"page_image"}) and job.gives == frozenset({"script"})
    assert JOB in STEP_ORDER and STEP_ORDER.index(JOB) < STEP_ORDER.index("find-lines")


def test_no_purpose_runs_it_by_default():
    """source.job.find-the-script: "it is in no purpose's default steps, so no recipe changes until a person ticks it"."""
    assert all(JOB not in steps for steps in PURPOSE_STEPS.values())


def test_a_step_naming_it_plans_classify_script_with_the_steps_model(monkeypatch):
    """source.job.find-the-script: a step naming it plans the Classify Script workflow, the step's model as the run's override."""
    monkeypatch.setattr(start, "provider_without_key", lambda step: None)
    recipe = {"fichero_recipe": 1, "id": "t", "version": "0.1.0", "title": "t", "steps": [STEP]}

    plan = plan_start(recipe, stays_local=False)

    assert not plan["skipped"], plan["skipped"]
    run = plan["workflows"][0]
    assert run["workflow"] == "Classify Script" and run["steps"] == ["script"]
    assert (run["provider_override"], run["model_override"]) == ("anthropic", "claude")
