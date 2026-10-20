"""`activity.run.step-honest-about-lost-pages`: a step that read 2 of 5 pages is PARTIAL, not done, and says which pages
and why (M4 run: "Read read 2 of 5 pages (59 lines unread) and said done")."""
from __future__ import annotations

from fichero_server.recipes import runner
from fichero_server.workflows.run_account import PageFailure

CARD = {"card": "model", "steps": ["read-a-line"]}


def _end(db, monkeypatch, lost, failed):
    monkeypatch.setattr(runner, "_did_no_page", lambda *a, **k: (False, failed, lost))
    step = {"state": "done", "child_id": "c", "why": None}
    problems: list[str] = []
    runner._after_the_step(db, CARD, step, {"folder": "f"}, ["a", "b", "c", "d", "e"], "done", "c", None, {}, problems,
                           "read-a-line")
    return step, problems


def test_a_step_that_loses_pages_ends_partial_and_names_each_page_with_why(db, monkeypatch):
    lost = [PageFailure(page="IMG_001", reason="Kraken could not read its lines"),
            PageFailure(page="IMG_003", reason="out of memory"), PageFailure(page="IMG_004", reason="no image")]
    step, problems = _end(db, monkeypatch, lost, 3)
    assert step["state"] == "partial"
    assert step["why"].startswith("2 of 5 pages done; 3 failed: IMG_001: Kraken could not read its lines")
    assert step["failed_pages"][1] == {"page": "IMG_003", "reason": "out of memory"}
    assert len(problems) == 1 and "partial" in problems[0]


def test_a_step_that_loses_no_page_stays_done(db, monkeypatch):
    step, problems = _end(db, monkeypatch, [], 0)
    assert step["state"] == "done" and not problems and "failed_pages" not in step


def test_a_partial_step_is_worse_than_done_and_better_than_failed():
    step = {"state": "done", "child_id": None, "why": None}
    runner._settle(step, "partial", None, "2 of 5 pages done")
    assert step["state"] == "partial"
    runner._settle(step, "done", None, None)  # a later clean batch does not wipe a lost page
    assert step["state"] == "partial"
    runner._settle(step, "failed", None, "no model")
    assert step["state"] == "failed"


def test_the_recipes_row_does_not_end_plain_done_when_a_step_lost_pages(db, monkeypatch):
    """The Activity row of the run: "Done with failures: step read-a-line lost pages ..." (it was "Done: 1 steps run")."""
    lost = [PageFailure(page="IMG_001", reason="Kraken could not read its lines")]
    step, _ = _end(db, monkeypatch, lost, 1)
    assert step["failed_batches"][0]["state"] == "partial"
    words = runner._failures_words(db, [CARD], [step], 0)
    assert "lost pages" in words and "IMG_001: Kraken could not read its lines" in words


def test_a_second_batch_that_loses_a_page_adds_it_and_the_totals_cover_both(db, monkeypatch):
    """A recipe over many folders: every batch's lost pages are on the step (432), and the count is of both batches."""
    step = {"state": "done", "child_id": "c", "why": None}
    problems: list[str] = []
    for lost_page, docs in ((PageFailure(page="IMG_001", reason="no lines"), ["a", "b", "c"]),
                            (PageFailure(page="IMG_104", reason="out of memory"), ["d", "e", "f", "g"])):
        monkeypatch.setattr(runner, "_did_no_page", lambda *a, _l=lost_page, **k: (False, 1, [_l]))
        runner._after_the_step(db, CARD, step, {"folder": "f"}, docs, "done", "c", None, {}, problems, "read-a-line")
    assert step["state"] == "partial"
    assert [p["page"] for p in step["failed_pages"]] == ["IMG_001", "IMG_104"]
    assert step["why"].startswith("5 of 7 pages done; 2 failed: IMG_001: no lines; IMG_104: out of memory")


def test_a_clean_batch_after_a_lossy_one_keeps_the_step_partial_and_counts_its_pages(db, monkeypatch):
    step = {"state": "done", "child_id": "c", "why": None}
    problems: list[str] = []
    monkeypatch.setattr(runner, "_did_no_page", lambda *a, **k: (False, 1, [PageFailure(page="IMG_001", reason="x")]))
    runner._after_the_step(db, CARD, step, {"folder": "f"}, ["a", "b"], "done", "c", None, {}, problems, "r")
    monkeypatch.setattr(runner, "_did_no_page", lambda *a, **k: (False, 0, []))
    runner._after_the_step(db, CARD, step, {"folder": "g"}, ["c", "d", "e"], "done", "c", None, {}, problems, "r")
    assert step["state"] == "partial" and step["pages_tried"] == 5 and step["pages_lost"] == 1
