"""The job registry (`source.recipe.jobs-are-a-registry`, `source.recipe.steps-are-jobs`).

Why it matters: a recipe is checked before it runs only because every job declares what it takes
and gives. If a job loses its declaration, or the check stops refusing a step that has no input,
a recipe can start a 3,000-page run that fails at step 4 hours later. The descriptions are what
setup and the user manual show; a job without one leaves a blank screen.
"""
from __future__ import annotations

import pytest

from fichero_server.recipes import jobs


def test_every_job_explains_itself_and_declares_what_flows():
    for job in jobs.all_jobs():
        assert job.description.strip() and job.name.strip(), job.id
        assert job.gives, f"{job.id} gives nothing"
        assert job.compare.strip(), f"{job.id} has no way to be compared in an A/B"


def test_a_sensible_handwriting_recipe_checks_clean():
    steps = ["prepare-the-image", "find-lines", "read-a-line", "correct", "find-names-tag-words", "find-statements",
             "make-a-vector", "export"]
    assert jobs.unmet_inputs(steps) == []


def test_a_step_that_needs_what_no_earlier_step_gave_is_refused_by_name():
    problems = jobs.unmet_inputs(["read-a-line"])  # nothing found the lines
    assert problems == ["step 1 (Read each line) needs lines, which no earlier step gives"]


def test_a_job_this_copy_lacks_is_named_not_crashed_on():
    assert jobs.unmet_inputs(["find-lines", "summon_spirits"]) == [
        "step 2: this copy of Fichero has no job 'summon_spirits'"]


def test_a_job_registers_once_and_must_explain_itself():
    with pytest.raises(ValueError):
        jobs.register_job(jobs.get_job("find-lines"))
    with pytest.raises(ValueError):
        jobs.register_job(jobs.Job("x_new", "X", frozenset(), frozenset({"y"}), "z", "c", "  "))
