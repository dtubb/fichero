"""Fable runner review #22: five bad scans in a row (blank versos, a damaged folder) aborted a 500-page run as a
'systemic error' whatever the rest did; the same 5 failures later in the run did not. The verdict now depends on how many
failed, not where (`activity.run.systemic-error-rule`)."""
from __future__ import annotations

from fichero_server.workflows.builder import is_systemic


def test_five_bad_scans_in_a_row_do_not_stop_a_large_batch_that_mostly_reads():
    assert not is_systemic(total=500, error_count=5, max_consecutive=5)


def test_a_small_batch_still_stops_on_five_in_a_row():
    assert is_systemic(total=6, error_count=5, max_consecutive=5)


def test_a_large_batch_most_of_which_failed_stops():
    assert is_systemic(total=20, error_count=15, max_consecutive=5)
    assert not is_systemic(total=20, error_count=15, max_consecutive=4)  # not a run of five: the rate rule says it


def test_a_refusal_that_holds_for_every_page_stops_at_the_first():
    assert is_systemic(total=500, error_count=1, max_consecutive=1, refused_all=True)
