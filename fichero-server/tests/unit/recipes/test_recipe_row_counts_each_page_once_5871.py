"""A recipe row counts each page ONCE across its stages (`activity.run.pages-counted-once`, #5959, #5871; was Fable runner review
#13, which summed the stages: 92 of 184). The row reads the least of the workflow stages' pages, and 0 while a stage has not started,
so 92 pages over three stages read "36 of 92", never "184 of 276". The stage doing the work is named by the row's reason."""
from __future__ import annotations

from types import SimpleNamespace

from fichero_server.api.routes.system.activity import _recipe_pages_done, _recipe_pages_in_all


def _step(done, total):
    return {"card": "workflow", "account": SimpleNamespace(pages_done=done, pages_total=total)}


def test_a_new_stage_holds_the_row_at_zero_of_the_runs_pages_not_92_of_184():
    status = {"steps": [_step(92, 92), _step(0, 92), {"card": "workflow", "account": None}]}
    assert _recipe_pages_done(status) == 0
    assert _recipe_pages_in_all(status, 92) == 92


def test_one_stage_reads_as_before_and_no_stage_as_zero():
    assert (_recipe_pages_done({"steps": [_step(30, 92)]}), _recipe_pages_in_all({"steps": [_step(30, 92)]}, 92)) == (30, 92)
    assert _recipe_pages_done({"steps": [{"card": "workflow", "account": None}]}) == 0
