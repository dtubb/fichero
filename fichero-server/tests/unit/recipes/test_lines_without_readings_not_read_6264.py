"""A page with lines but no readings is not read (#6264), tested to the spec `source.recipe.read-resumes-per-line`
(docs/contributor_manual/specs/source/models-chains-and-projects.md).

WHY: on the M1 Air (b18), Start on a 31-page document read 12 pages; the other 19 had lines from an earlier run and
their readings taken back, were counted as read, and the names step then left each out ("no line of its working
pass has a reading"). The done check reads what the reader reads: a reading taken back is no reading.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fichero_server.models import ContentRepresentation
from fichero_server.recipes.done import is_done, split_done
from tests.unit.recipes.test_unread_lines_not_read_5758 import _page

CARD = {"job": "read-a-line", "model_override": None}


def _taken_back(db, page):
    for reading in db.query(ContentRepresentation, document_id=page):
        reading.retracted_at = datetime.now(timezone.utc)
        db.save(reading)


def test_a_page_with_lines_and_no_readings_is_not_read_and_one_with_readings_is(db):
    lines_only, read = _page(db, 4, 0), _page(db, 4, 4)
    assert is_done(db, CARD, lines_only) is False and is_done(db, CARD, read) is True
    assert split_done(db, CARD, [lines_only, read]) == ([lines_only], 1)


def test_a_page_whose_readings_were_taken_back_is_read_again(db):
    page = _page(db, 4, 4)
    _taken_back(db, page)
    assert is_done(db, CARD, page) is False
    assert split_done(db, CARD, [page]) == ([page], 0)
