"""`source.recipe.jobs-carry-descriptions` (#4949), the built half: every registered job carries a plain description
(its topic's sentence and paragraph) and declares how its outputs are compared; setup and the Inspector read that
text from the engine (`GET /api/topics/{id}`), never their own copy."""
from __future__ import annotations

import pytest

from fichero_server.recipes.jobs import all_jobs

JOBS = all_jobs()


@pytest.mark.parametrize("job", JOBS, ids=[j.id for j in JOBS])
def test_every_job_has_a_description_and_says_how_its_outputs_are_compared(job):
    topic = job.topic
    assert topic is not None, f"{job.id} has no topic"
    assert topic.title and topic.short.strip() and topic.long.strip(), job.id
    assert job.compare.strip(), job.id


def test_setup_reads_a_jobs_description_from_the_engine(client):
    job = next(j for j in JOBS if j.id == "read-a-line")
    r = client.get(f"/api/topics/{job.topic.id}")
    assert r.status_code == 200, r.text
    assert job.topic.short in str(r.json())
