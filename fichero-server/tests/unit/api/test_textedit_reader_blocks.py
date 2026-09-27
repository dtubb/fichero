"""`source.textedit.reader-shows-segments`'s region/direction packaging (#5001): `TextBlock`,
the grouping `document_text` returns alongside its flat spans. Built on `seeded_converted_page`.

A block boundary is a DIRECTION CHANGE, not a direction value: a whole-page `rtl` region is one
block; a boustrophedon region -- each line's own direction alternating -- is one block per line,
because there is no shared orientation two alternating lines can be laid out under at once. That
is the case that distinguishes a correct implementation from a group-by, and it is tested here
explicitly rather than assumed to fall out of the same code that handles the easy case.

`alternating` and `follows-baseline` are per-segment values with no single orientation
(`languages-scripts-signs.md`'s six-value list): a segment resolving to either never merges with
a neighbour, even one resolving to the same value -- decided and pinned here, not left implicit.
"""
from __future__ import annotations

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_conversion import live_rows_in_order
from fichero_server.models import Artifact

from .seeded_converted_page import seed_page

pytestmark = pytest.mark.source_model

CTX = ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _converted(db, client):
    _, page, art = seed_page(db)
    r = client.put(f"/api/artifacts/{art.id}/regions", json={"op": "move", "indices": [0], "bbox": [0.1, 0.1, 0.6, 0.05]})
    assert r.status_code == 200
    return page, art, live_rows_in_order(db, db.get(Artifact, art.id).geometry_superseded_by_pass_id)


def _set_direction(db, row, direction):
    row.direction = direction
    db.save(row)


def _blocks(client, page):
    return client.get(f"/api/segments/document/{page.id}/text").json()["blocks"]


class TestOneDirectionIsOneBlock:
    def test_a_whole_page_of_one_direction_is_one_block(self, db, client):
        page, art, rows = _converted(db, client)
        for row in rows:
            _set_direction(db, row, "rtl")
        blocks = _blocks(client, page)
        assert len(blocks) == 1
        assert blocks[0]["direction"] == "rtl"
        assert len(blocks[0]["spans"]) == len(rows)
        assert blocks[0]["text"] == client.get(f"/api/segments/document/{page.id}/text").json()["text"]

    def test_the_stated_direction_wins_over_the_derived_one_and_the_level_says_so(self, db, client):
        page, art, rows = _converted(db, client)
        _set_direction(db, rows[0], "ltr")
        blocks = _blocks(client, page)
        assert blocks[0]["direction"] == "ltr"
        assert blocks[0]["direction_level"] == "segment"


class TestADirectionChangeStartsANewBlock:
    def test_two_regions_of_different_direction_are_two_blocks(self, db, client):
        page, art, rows = _converted(db, client)
        for row in rows[:2]:
            _set_direction(db, row, "rtl")
        for row in rows[2:]:
            _set_direction(db, row, "ltr")
        blocks = _blocks(client, page)
        assert [b["direction"] for b in blocks] == ["rtl", "ltr"]
        assert len(blocks[0]["spans"]) == 2
        assert len(blocks[1]["spans"]) == len(rows) - 2

    def test_boustrophedon_alternating_lines_are_one_block_per_line_not_one_merged_block(self, db, client):
        """The case that distinguishes a correct implementation from a group-by: each line's OWN
        direction alternates ltr/rtl/ltr/rtl, so there is no shared orientation to merge under and
        every line is its own block."""
        page, art, rows = _converted(db, client)
        pattern = ["ltr", "rtl", "ltr", "rtl"]
        for row, direction in zip(rows, pattern):
            _set_direction(db, row, direction)
        blocks = _blocks(client, page)
        assert [b["direction"] for b in blocks] == pattern
        assert all(len(b["spans"]) == 1 for b in blocks)

    def test_a_run_within_an_alternating_page_still_merges(self, db, client):
        """Two CONSECUTIVE lines sharing a direction merge even inside an otherwise-alternating
        page -- the boundary is a change, not a fixed per-line split."""
        page, art, rows = _converted(db, client)
        pattern = ["ltr", "ltr", "rtl", "ltr"]
        for row, direction in zip(rows, pattern):
            _set_direction(db, row, direction)
        blocks = _blocks(client, page)
        assert [b["direction"] for b in blocks] == ["ltr", "rtl", "ltr"]
        assert len(blocks[0]["spans"]) == 2


class TestNonOrientableValuesNeverMerge:
    def test_follows_baseline_is_one_block_per_segment(self, db, client):
        page, art, rows = _converted(db, client)
        for row in rows:
            _set_direction(db, row, "follows-baseline")
        blocks = _blocks(client, page)
        assert [b["direction"] for b in blocks] == ["follows-baseline"] * len(rows)
        assert all(len(b["spans"]) == 1 for b in blocks)

    def test_alternating_as_a_per_segment_value_is_also_one_block_per_segment(self, db, client):
        """`alternating` can itself be the resolved value of one segment (stated directly, or
        cascaded from a document-level claim) rather than a description this code infers from
        neighbouring lines -- and it has no single orientation either, so it gets the same
        never-merge treatment as `follows-baseline`."""
        page, art, rows = _converted(db, client)
        for row in rows:
            _set_direction(db, row, "alternating")
        blocks = _blocks(client, page)
        assert [b["direction"] for b in blocks] == ["alternating"] * len(rows)
        assert all(len(b["spans"]) == 1 for b in blocks)


class TestRegionGrouping:
    def test_two_regions_of_the_same_direction_are_still_two_blocks(self, db, client):
        page, art, rows = _converted(db, client)
        for row in rows:
            _set_direction(db, row, "ltr")
        rows[0].parent_segment_id = "region-a"
        rows[1].parent_segment_id = "region-a"
        rows[2].parent_segment_id = "region-b"
        rows[3].parent_segment_id = "region-b"
        for row in rows:
            db.save(row)
        blocks = _blocks(client, page)
        assert len(blocks) == 2
        assert blocks[0]["region_segment_id"] == "region-a"
        assert blocks[1]["region_segment_id"] == "region-b"

    def test_a_line_with_no_region_parent_has_a_null_region(self, db, client):
        page, art, rows = _converted(db, client)
        blocks = _blocks(client, page)
        assert all(b["region_segment_id"] is None for b in blocks)
