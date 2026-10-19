"""`source.disagree.recipe-step` (#5665): "Find where the readers disagree" is a recipe step in the Read stage.

Spec: docs/contributor_manual/specs/source/readings-and-apparatus.md. The step reads the page's lines again with
the readers it names, or with one reader sampled N times at a temperature (5 at 0.7 by default); each run reads
the working pass's lines with a vision model and keeps every reading as a reading of the line, beside the others.
"""
from __future__ import annotations

from fichero_server.recipes.jobs import get_job, unmet_inputs
from fichero_server.recipes.stages import stage_of
from fichero_server.recipes.start import DISAGREE_JOB, READ_LINES_WITH_A_MODEL, _shipped, plan_start
from tests.unit.recipes.test_installed_model_first_to_spec import LINES, SEVEN, mac  # noqa: F401 (fixture)

THREE = {"hf": "mlx-community/Qwen2.5-VL-3B-Instruct-4bit", "revision": "main"}
READ_WITH_SEVEN = {"id": "read", "job": "read-a-line", "model": SEVEN, "runs_on": "this-mac"}


def _recipe(*steps):
    return {"fichero_recipe": 1, "id": "t/disagree", "version": "0.1.0", "title": "t", "steps": list(steps)}


def test_the_job_is_registered_in_the_read_stage():
    job = get_job(DISAGREE_JOB)
    assert job is not None and job.name == "Find where the readers disagree"
    assert stage_of(DISAGREE_JOB).id == "read"
    assert unmet_inputs(["find-lines", DISAGREE_JOB]) == [], "it reads the lines found before it"
    assert unmet_inputs([DISAGREE_JOB]), "it needs lines"


def test_by_default_one_reader_is_sampled_five_times_at_0_7(mac):
    plan = plan_start(_recipe(LINES, READ_WITH_SEVEN, {"id": "doubt", "job": DISAGREE_JOB}), stays_local=True)

    sampled = [r for r in plan["runs"] if r["job"] == DISAGREE_JOB]
    assert len(sampled) == 5, plan["skipped"]
    name, _ = _shipped(READ_LINES_WITH_A_MODEL)
    assert {r["workflow"] for r in sampled} == {name}, "the lines are read again by a vision model"
    [reader] = [r for r in plan["runs"] if r["job"] == "read-a-line"]
    assert {r["model_override"] for r in sampled} == {reader["model_override"]}, (
        "the recipe's own line reader, when the step names none")
    assert all(r["tool_config"] == {"transcribe": {"temperature": 0.7}} for r in sampled)
    assert all(r["steps"] == ["doubt"] for r in sampled)


def test_the_samples_and_temperature_are_the_steps_settings(mac):
    step = {"id": "doubt", "job": DISAGREE_JOB, "model": THREE, "settings": {"samples": 3, "temperature": 0.9}}
    plan = plan_start(_recipe(LINES, READ_WITH_SEVEN, step), stays_local=True)

    sampled = [r for r in plan["runs"] if r["job"] == DISAGREE_JOB]
    assert len(sampled) == 3 and all(r["tool_config"]["transcribe"]["temperature"] == 0.9 for r in sampled)
    assert len({r["model_override"] for r in sampled}) == 1
    assert sampled[0]["model_override"] != [r for r in plan["runs"] if r["job"] == "read-a-line"][0]["model_override"]


def test_named_readers_each_read_once(mac):
    step = {"id": "doubt", "job": DISAGREE_JOB, "settings": {"readers": [SEVEN, THREE]}}
    plan = plan_start(_recipe(LINES, READ_WITH_SEVEN, step), stays_local=True)

    sampled = [r for r in plan["runs"] if r["job"] == DISAGREE_JOB]
    assert len(sampled) == 2 and len({r["model_override"] for r in sampled}) == 2


def test_with_one_reader_that_cannot_be_sampled_the_step_says_which_reader_to_add(mac):
    kraken_reader = {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}}
    plan = plan_start(_recipe(LINES, kraken_reader, {"id": "doubt", "job": DISAGREE_JOB}), stays_local=True)

    assert not [r for r in plan["runs"] if r["job"] == DISAGREE_JOB]
    (skipped,) = [s for s in plan["skipped"] if s["step"] == "doubt"]
    assert "add a second reader" in skipped["why"] and skipped["fix"] is None, "never a model to choose for this step"
