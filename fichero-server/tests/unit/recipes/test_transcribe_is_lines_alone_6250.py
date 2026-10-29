"""`source.recipe.transcribe-is-lines-alone` (#6250, APPROVED 2026-10-28): every purpose's assembled steps build on
Find lines then Read each line. Review the reading (`correct`), a page reader and Check are add-ons a person turns on;
no purpose proposes them by itself. Correct stays in the purpose table only as the step Set Up's question turns on
(`_correct_left_off`, #5677/#5812): unasked, it is a left-off row, never a step. Through the assemble route."""
from __future__ import annotations

import pytest

from fichero_server.recipes.assemble import PURPOSE_STEPS
from tests.unit.recipes.test_installed_model_first_to_spec import mac  # noqa: F401  (fixture)

ANSWERS = {"languages": ["es"], "scripts": ["Latn"], "materials": ["handwriting"], "mac_memory_gb": 32}
ADD_ONS = {"correct", "read-a-page", "check"}
pytestmark = pytest.mark.usefixtures("with_material", "mac")


def _jobs(client, purposes, cloud_allowed=False):
    r = client.post("/api/recipes/assemble", json={**ANSWERS, "purposes": purposes, "cloud_allowed": cloud_allowed})
    assert r.status_code == 200, r.text
    # Leave out (marks specks and damage before reading; no model) rides on Find lines by itself: not what a purpose
    # proposes, and the ruling did not take it out.
    return [s["job"] for s in r.json()["steps"] if s["job"] != "leave-out"]


@pytest.mark.parametrize("cloud_allowed", [False, True])
def test_transcribe_is_find_lines_then_read_each_line(client, cloud_allowed):
    assert _jobs(client, ["transcribe"], cloud_allowed) == ["find-lines", "read-a-line"]


def test_a_purpose_builds_on_the_lines_alone(client):
    jobs = _jobs(client, ["map-places"])
    assert jobs[:3] == ["find-lines", "read-a-line", "find-names-tag-words"] and not set(jobs) & ADD_ONS, jobs


def test_no_purpose_adds_review_a_page_reader_or_check_by_itself(client):
    added = {p: sorted(set(_jobs(client, [p], cloud_allowed=True)) & ADD_ONS) for p, steps in PURPOSE_STEPS.items() if steps}
    assert not any(added.values()), added
