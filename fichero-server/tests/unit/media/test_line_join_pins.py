"""Pins what the line-join helpers do today (`media/line_join.py`).

Characterisation tests: they state the current behaviour, not a spec ruling. Pure geometry on the stored
fractions; no image, no network, no real library is opened and no file is written.
"""
from __future__ import annotations

from fichero_server.media import line_join

SQUARE = [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]]
# A bow-tie: its two lower-left-to-upper-right edges cross in the middle.
BOW_TIE = [[0.1, 0.1], [0.3, 0.3], [0.3, 0.1], [0.1, 0.3]]


def test_reading_separator_is_a_space_except_for_unspaced_scripts():
    assert line_join.reading_separator("Latn") == " "
    assert line_join.reading_separator("Hani") == ""
    # No script given: the separator is a space, the default for a spaced script.
    assert line_join.reading_separator(None) == " "


def test_joined_baseline_runs_each_line_left_to_right_then_joins_them_in_order():
    left_to_right = [[0.0, 0.0], [10.0, 0.0]]
    right_to_left = [[30.0, 0.0], [20.0, 0.0]]
    # The second line is stored right to left, so it is turned to read the same way as the first.
    assert line_join.joined_baseline([left_to_right, right_to_left], None) == [
        [0.0, 0.0], [10.0, 0.0], [20.0, 0.0], [30.0, 0.0]]


def test_joined_baseline_reads_right_to_left_under_rtl_and_skips_lines_with_no_baseline():
    line = [[0.0, 0.0], [10.0, 0.0]]
    # Under rtl a left-to-right stored line is the one turned round.
    assert line_join.joined_baseline([line], "rtl") == [[10.0, 0.0], [0.0, 0.0]]
    # Lines with no baseline, or one point only, are skipped; a line with none at all gives None.
    assert line_join.joined_baseline([None, [], [[1.0, 1.0]], line], None) == [[0.0, 0.0], [10.0, 0.0]]
    assert line_join.joined_baseline([], None) is None
    assert line_join.joined_baseline([None, [[1.0, 1.0]]], None) is None


def test_join_order_reads_the_members_in_the_page_reading_order():
    top_left = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]
    top_right = [[20.0, 0.0], [30.0, 0.0], [30.0, 10.0], [20.0, 10.0]]
    below = [[0.0, 20.0], [10.0, 20.0], [10.0, 30.0], [0.0, 30.0]]
    outlines = [top_left, top_right, below]
    # Left to right: the top row first, then the line below it.
    assert line_join.join_order(outlines, "ltr") == [0, 1, 2]
    # Right to left: the top-right line comes before the top-left one.
    assert line_join.join_order(outlines, "rtl") == [1, 0, 2]
    # No members, no order.
    assert line_join.join_order([], "ltr") == []


def test_simple_outline_returns_a_simple_polygon_unchanged_and_traces_a_crossing_one_to_a_simple_boundary():
    assert line_join.simple_outline(SQUARE) == (SQUARE, False)

    traced, simplified = line_join.simple_outline(BOW_TIE)
    assert simplified is True
    # The traced outline is simple, and stays within the bow-tie's bounding box. The raster adds a margin of
    # a few cells (1/4096 each) around the shape, so the box is checked to 1e-3 rather than exactly.
    assert not line_join.crosses_itself(traced)
    xs = [p[0] for p in traced]
    ys = [p[1] for p in traced]
    assert min(xs) >= 0.1 - 1e-3 and max(xs) <= 0.3 + 1e-3
    assert min(ys) >= 0.1 - 1e-3 and max(ys) <= 0.3 + 1e-3
