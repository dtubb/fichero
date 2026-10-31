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


def test_the_prepare_step_is_off_by_default_and_a_person_can_take_it_out(client, with_material):
    """Review finding (Stage 2 HIGH 2): the step now runs the page operations on every page, so it must have an off switch:
    it is in the plan only when photographs is answered yes (default off) or a sample shows faded pages, and Ready's
    Take Out (`removed_jobs`) removes it even then; proposing the plan again does not bring it back."""
    assert "prepare-the-image" not in _jobs(_assemble(client, purposes=["transcribe"]))
    on = _assemble(client, purposes=["transcribe"], photographs=True)
    assert "prepare-the-image" in _jobs(on)
    off = _assemble(client, purposes=["transcribe"], photographs=True, removed_jobs=["prepare-the-image"])
    assert "prepare-the-image" not in _jobs(off)
    assert [t["job"] for t in off["removed"]] == ["prepare-the-image"]
