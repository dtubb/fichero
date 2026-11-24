"""Pins what the recipe runner's pure helpers and run-stage lookup do today (`recipes/runner.py`).

Characterisation tests: they state the current behaviour, not a spec ruling. No network, no real library, no files.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from fichero_server.execution import jobs
from fichero_server.importers.derivatives import EMBED_KIND, NLP_KIND
from fichero_server.recipes import runner


def test_could_not_start_says_a_missing_library_plainly_and_the_first_line_otherwise():
    card = {"job": "", "steps": ["correct", "translate"]}

    lib = runner.could_not_start(card, ImportError("dlopen(libkraken.dylib): Library not loaded"))
    assert lib == ("correct, translate could not start: a library it needs would not load on this Mac. "
                   "Restart Fichero, or reinstall.")

    assert runner.could_not_start(card, ValueError("boom\nsecond line")) == "correct, translate could not start: boom"
    # An empty message falls back to the exception's class name.
    assert runner.could_not_start(card, RuntimeError("")) == "correct, translate could not start: RuntimeError"
    # The first line is cut at 160 characters.
    assert runner.could_not_start(card, ValueError("x" * 300)) == (
        "correct, translate could not start: " + "x" * 160)


def test_stages_the_run_takes_reads_embed_and_names_stages_and_is_empty_for_no_or_failed_run(db):
    jobs._ensure(db)
    stages = json.dumps({"runs": [{"card": "embed"}, {"job": "find-names-tag-words"}]})
    run_id = jobs.enqueue(db, "run-a-recipe", "stages-pin", started_by="owner", detail=stages)

    assert runner.stages_the_run_takes(db, run_id) == {EMBED_KIND, NLP_KIND}
    assert runner.stages_the_run_takes(db, None) == set()
    assert runner.stages_the_run_takes(db, "no-such-run-pin") == set()

    db.execute("UPDATE jobs SET state = 'failed' WHERE id = ?", [run_id])
    assert runner.stages_the_run_takes(db, run_id) == set()


def test_partial_words_names_the_first_three_lost_pages_and_counts_the_rest():
    def lost(page: str, reason: str) -> SimpleNamespace:
        return SimpleNamespace(page=page, reason=reason)

    three = [lost("IMG_001", "Kraken could not read its lines"), lost("IMG_002", "timeout"), lost("IMG_003", "bad image")]
    assert runner._partial_words(2, three, 3) == (
        "2 of 5 pages done; 3 failed: IMG_001: Kraken could not read its lines; IMG_002: timeout; IMG_003: bad image")

    four = three + [lost("IMG_004", "timeout")]
    assert runner._partial_words(2, four, 4) == (
        "2 of 6 pages done; 4 failed: IMG_001: Kraken could not read its lines; IMG_002: timeout; "
        "IMG_003: bad image; and 1 more")


def test_halted_stops_on_outright_failures_in_a_row_and_names_the_last_reason():
    cards = [{"steps": ["correct"]}]
    failing = [{"outright_in_a_row": 3, "failed_batches": [
        {"state": "done", "why": None},
        {"state": "failed", "why": "Kraken broke"},
    ]}]
    assert runner._halted(cards, failing) == (
        "step correct failed on 3 folders in a row without doing a page (Kraken broke)")

    # Below the threshold the run carries on; so does an empty run.
    assert runner._halted(cards, [{"outright_in_a_row": runner.OUTRIGHT_IN_A_ROW - 1}]) is None
    assert runner._halted([], []) is None

    # A failing run with no failed batch recorded says so, rather than naming nothing.
    assert runner._halted(cards, [{"outright_in_a_row": 3}]) == (
        "step correct failed on 3 folders in a row without doing a page (no reason given)")


def test_summed_adds_counts_and_lets_an_unknown_count_win_over_none():
    more = [[3, 4], [5, 6]]
    assert runner._summed(None, more) is more

    assert runner._summed([[1, 2], [1, 1]], [[3, 4], [5, 6]]) == [[4, 6], [6, 7]]
    # A step that cannot tell on one side takes the other side's count; it cannot tell only when both cannot.
    assert runner._summed([None, [1, 2]], [[3, 4], [5, 6]]) == [[3, 4], [6, 8]]
    assert runner._summed([[None, 1]], [[2, 3]]) == [[None, 4]]
    assert runner._summed([], []) == []
