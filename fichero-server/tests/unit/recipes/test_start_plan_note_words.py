"""The Start plan says what it will do on a run's pages in plain words (#5616)."""
from fichero_server.recipes.done import _note


def test_none_done_reads_runs_on_all_pages():
    assert _note(0, 203, "pages") == "runs on all 203 pages"


def test_all_done_reads_nothing_to_run():
    assert _note(203, 203, "pages") == "already done on all 203 pages; nothing to run"


def test_some_done_names_how_many_are_left():
    assert _note(154, 203, "pages") == "already done on 154 of 203 pages; runs on the other 49"


def test_a_card_that_cannot_tell_runs_on_every_page():
    assert _note(None, 7, "photographs") == "cannot tell what is done; runs on every page (7)"
