"""`activity.summary.eta-basis` (#5960), the background lines' half: a running kind's line carries the time left at the kind's median per item
and says what it rests on; a kind with no pace, or nothing left, carries none."""
from __future__ import annotations

from fichero_server.api.routes.system.activity import KIND_PACE_BASIS, BackgroundJob, background_lines


def _job(kind, current, total, state="running"):
    return BackgroundJob(id=kind, task_type=kind, name=kind, current=current, total=total, percent=0.0, state=state)


def test_the_items_left_at_the_median_per_item_with_its_basis():
    (line,) = background_lines([_job("embed", 10, 40)], {"embed": 2.0})
    assert (line.seconds_left, line.eta_basis) == (60.0, KIND_PACE_BASIS)


def test_no_pace_or_nothing_left_says_nothing():
    lines = background_lines([_job("embed", 10, 40), _job("thumbs", 5, 5)], {"thumbs": 1.0})
    assert [(x.seconds_left, x.eta_basis) for x in lines] == [(None, None), (None, None)]
