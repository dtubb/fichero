"""R3 live exit step 6 (plan-recipes-2026-10-17.md; `source.onboard.auto.results-summary`, `source.job.review-is-segment-native`):
the run summary counts the lines the review answered, the ones it corrected and the ones it could not read and left.

WHY: a run with a review step said only "Read 1 of 1 page"; nothing said the review had looked at the lines at all.
"""
from __future__ import annotations

import pytest

from fichero_server.recipes import run_view
from tests.unit.workflows.test_review_corrects_the_lines_5654 import (  # noqa: F401  (fixture)
    _lines,
    _review,
    page,
)


@pytest.mark.asyncio
async def test_the_summary_counts_the_lines_the_review_answered_corrected_and_left(page, monkeypatch):  # noqa: F811
    first, second, third = _lines(page)
    await _review(page, monkeypatch, f"{first.id} | certain | el dicho escrivano\n"
                                     f"{second.id} | certain | vezino de la ciudad\n{third.id} | unreadable")

    assert run_view.reviewed(page["db"], [page["doc"].id]) == {"pages": 1, "lines": 3, "corrected": 1, "unreadable": 1}


@pytest.mark.asyncio
async def test_the_count_is_three_queries_however_many_pages_the_run_has(page, monkeypatch):  # noqa: F811
    """Read on every GET of the summary: never a query per page (review 153)."""
    first = _lines(page)[0]
    await _review(page, monkeypatch, f"{first.id} | certain | el dicho escrivano")
    db, calls = page["db"], []
    real = db._execute

    def counting(*args, **kwargs):
        calls.append(args[0])
        return real(*args, **kwargs)

    monkeypatch.setattr(db, "_execute", counting)
    run_view.reviewed(db, [page["doc"].id])
    one = len(calls)
    calls.clear()
    run_view.reviewed(db, [page["doc"].id, *[f"page-{n}" for n in range(200)]])
    assert one == len(calls) == 3, calls


def test_a_page_with_no_review_counts_nothing(db):
    assert run_view.reviewed(db, ["no-such-page"]) == {"pages": 0, "lines": 0, "corrected": 0, "unreadable": 0}


def test_the_summary_says_the_review_in_words_when_the_run_had_one():
    """Said only for a run that had a review step: its figures are null otherwise."""
    made = run_view.RecipeRunSummary(job_id="j", state="done", finished=True, pages=2, pages_read=2, names=[], dates=0,
                                     statements=0, failed=[], pages_failed=0, skipped=[], not_run=[],
                                     lines_reviewed=12, lines_corrected=3, lines_review_unreadable=1, pages_reviewed=2)
    said = run_view._lines(made, 0, {"read-a-line", "correct"})
    assert "Reviewed 12 lines on 2 pages: 3 corrected, 1 it could not read and left as read" in said
    unreviewed = made.model_copy(update={"lines_reviewed": None})  # the run had no review step: no line for it
    assert not [s for s in run_view._lines(unreviewed, 0, {"read-a-line"}) if s.startswith("Reviewed")]
