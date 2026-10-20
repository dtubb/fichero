"""Fable runner review #13: a recipe row showed only the LAST started stage's pages, so a 92-page recipe at Read 92 of 92
read 0 of 92 the moment Names started. It counts every started stage's pages (`activity.details.progress-counts`)."""
from __future__ import annotations

from types import SimpleNamespace

from fichero_server.api.routes.system.activity import _recipe_pages_done, _recipe_pages_in_all


def _step(done, total):
    return {"account": SimpleNamespace(pages_done=done, pages_total=total)}


def test_a_new_stage_does_not_take_the_finished_stages_pages_away():
    status = {"steps": [_step(92, 92), _step(0, 92), {"account": None}]}
    assert _recipe_pages_done(status) == 92
    assert _recipe_pages_in_all(status, 92) == 184


def test_one_stage_reads_as_before_and_no_stage_as_zero():
    assert (_recipe_pages_done({"steps": [_step(30, 92)]}), _recipe_pages_in_all({"steps": [_step(30, 92)]}, 92)) == (30, 92)
    assert _recipe_pages_done({"steps": [{"account": None}]}) == 0
