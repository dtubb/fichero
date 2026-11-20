"""`designer.rank.reasons-in-words` and the silent-failure rule (#6733 item 4): a Read try that made no reading on any
page is a failure that says so, never "done"."""
from __future__ import annotations

from fichero_server.recipes.samples import nothing_made


def _page(readings):
    return {"id": "p", "readings": readings, "segments": {}, "statements": []}


def test_a_read_try_with_no_reading_on_any_page_says_so():
    said = nothing_made("read", {"per_page": [_page([]), _page([])], "names": []})
    assert said and "read nothing" in said


def test_a_read_try_with_a_reading_is_not_failed():
    assert nothing_made("read", {"per_page": [_page([]), _page([{"text": "x"}])], "names": []}) is None


def test_other_stages_are_not_judged_by_their_readings():
    assert nothing_made("find-lines", {"per_page": [_page([])], "names": []}) is None
