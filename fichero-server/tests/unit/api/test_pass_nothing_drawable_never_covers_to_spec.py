"""source.pass.nothing-drawable-never-covers (docs/contributor_manual/specs/source/segments-and-geometry.md, #4955).

Spec: "a result whose shapes are all unusable (zero width or height) never hides a lower-ranked result that has boxes to
draw, and the page says the chosen result had no usable shapes."
The first half is `resolve_drawn_pass` (pinned in test_the_engine_serves_the_drawn_pass.py); this holds the second: the
working pass with nothing to draw is served `shapeless` when another pass is drawn, and nothing is shapeless otherwise.
"""
from __future__ import annotations

from tests.unit.api.test_the_engine_serves_the_drawn_pass import (
    MACHINE,
    _import_text_only,
    _page,
    _pass,
    _served,
)


def test_source_pass_nothing_drawable_never_covers__the_page_says_the_chosen_result_had_no_usable_shapes(db, client):
    doc_id = _page(db)
    machine = _pass(db, doc_id, MACHINE)
    imported = _import_text_only(db, doc_id)

    by_id = {p["id"]: p for p in _served(client, doc_id)}
    assert by_id[imported]["working"] and not by_id[imported]["drawn"]
    assert by_id[imported]["shapeless"] is True, "the working pass has nothing to draw, and the page says so"
    assert by_id[machine]["drawn"] and by_id[machine]["shapeless"] is False


def test_source_pass_nothing_drawable_never_covers__a_text_only_page_has_nothing_to_cover(db, client):
    doc_id = _page(db)
    _import_text_only(db, doc_id)
    assert not any(p["shapeless"] for p in _served(client, doc_id)), "nothing is drawn, so nothing is covered"
