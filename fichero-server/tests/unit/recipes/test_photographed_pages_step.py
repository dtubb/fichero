"""source.onboard.photographed-pages-asked (#5390): setup asks whether the pages are photographs, default off.

Through `POST /api/recipes/assemble`, as the prepare-images tests do.
"""
from __future__ import annotations

from tests.unit.recipes.test_prepare_images_step import _assemble


def _jobs(plan) -> list[str]:
    return [s["job"] for s in plan["steps"]] + [b["job"] for b in plan["by_hand"]]


def test_photographs_yes_adds_split_and_prepare_before_lines(client, with_material):
    jobs = _jobs(_assemble(client, purposes=["transcribe"], photographs=True))
    assert jobs.index("split-pages") < jobs.index("prepare-the-image") < jobs.index("find-lines")


def test_photographs_is_off_unless_the_person_says_so(client, with_material):
    for answers in ({}, {"photographs": False}):
        jobs = _jobs(_assemble(client, purposes=["transcribe"], **answers))
        assert "split-pages" not in jobs and "prepare-the-image" not in jobs


def test_photographs_with_nothing_to_line_or_read_adds_nothing(client, with_material):
    jobs = _jobs(_assemble(client, photographs=True))
    assert "split-pages" not in jobs and "prepare-the-image" not in jobs
