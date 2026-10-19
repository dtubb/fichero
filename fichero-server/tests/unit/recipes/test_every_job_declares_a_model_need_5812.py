"""Every job says whether it needs a model, and Start reads that one answer (#5812).

`source.recipe.every-job-declares-needs-a-model` (docs/contributor_manual/specs/source/readings-and-apparatus.md).
WHY: Find where the readers disagree showed "Choose a model" and a text-model search for a step that needs none; the
engine had a private `_NO_MODEL_JOBS` set that the setup page and the finder did not share.
"""

from __future__ import annotations

import pytest

from fichero_server.recipes import jobs, start


def test_every_registered_job_declares_it_as_a_yes_or_no():
    undeclared = [job.id for job in jobs.all_jobs() if not isinstance(job.needs_a_model, bool)]
    assert undeclared == []


def test_a_job_registered_without_the_answer_is_refused():
    with pytest.raises(ValueError, match="does not say whether it needs a model"):
        jobs.register_job(jobs.Job("a-new-job", frozenset(), frozenset(), "reading", "x"))


def test_a_job_that_needs_a_model_has_a_model_to_choose():
    """The two cannot drift apart: a yes-job carries a `model` setting; a no-job carries none, but the one sampled
    reader of the disagree step, which is optional and the plan's own."""
    for job in jobs.all_jobs():
        has_setting = "model" in job.settings
        if job.id == start.DISAGREE_JOB:
            assert job.needs_a_model is False and has_setting
        else:
            assert job.needs_a_model == has_setting, job.id


@pytest.mark.parametrize("job_id", ["export", "publish", "work-out-dates", "find-documents-in-a-folder",
                                    "prepare-the-image", "find-where-readers-disagree"])
def test_the_jobs_start_used_to_hide_in_its_own_set_say_no(job_id):
    assert start._needs_a_model(job_id) is False


def test_only_the_step_that_needs_a_model_is_skipped_for_having_none():
    recipe = {"steps": [{"id": "dates", "job": "work-out-dates", "layer": "graph"},
                        {"id": "page", "job": "read-a-page", "layer": "reading"}]}
    skipped = {s["step"]: s["why"] for s in start.plan_start(recipe, stays_local=True)["skipped"]}
    assert "page" in skipped and "has no model" in skipped["page"]
    assert "dates" not in skipped
