"""Regions and lines come in reading order from where they are, not in the order a segmenter listed them.

WHY: TEst 12 IMG_009 read "El Secretario. Secretaría de la Alcaldía..." first, though the page top is "Francisco Mina es
vecino...": Kraken lists regions by type then its own order, so the Order tab's Region 1 was not the top block and the
Reader text followed. Invented geometry, no model: a header over two columns, a margin note, a right-to-left page, a
vertical page, and Kraken's payload end to end.
"""

from __future__ import annotations

import random

from fichero_server.media.layout_order import order_payload, reading_order


def test_top_down_then_left_to_right_whatever_order_they_were_listed_in():
    boxes = {"title": (0, 0, 100, 10), "left": (0, 20, 45, 100), "right": (55, 20, 100, 100), "foot": (0, 110, 100, 120)}
    names = list(boxes)
    for seed in range(20):
        shuffled = names[:]
        random.Random(seed).shuffle(shuffled)
        got = reading_order([boxes[n] for n in shuffled])
        assert [shuffled[i] for i in got] == ["title", "left", "right", "foot"]


def test_columns_are_read_column_by_column_not_row_by_row():
    boxes = [(0, 0, 40, 45), (0, 48, 40, 93), (60, 0, 100, 45), (60, 48, 100, 93)]   # two columns, aligned paragraphs
    assert reading_order(boxes) == [0, 1, 2, 3]


def test_right_to_left_pages_take_their_columns_from_the_right():
    boxes = [(0, 0, 40, 100), (60, 0, 100, 100)]
    assert reading_order(boxes, direction="rtl") == [1, 0]
    assert reading_order(boxes, direction="ttb") == [1, 0]
    assert reading_order(boxes, direction="ttb-lr") == [0, 1]


def test_marginalia_come_after_the_body_block_they_sit_beside():
    boxes = [(0, 0, 70, 40), (0, 50, 70, 90), (75, 45, 100, 85), (0, 100, 70, 140)]
    kinds = ["text", "text", "marginalia", "text"]
    got = reading_order(boxes, kinds=kinds)
    assert got == [0, 1, 2, 3], "the margin note sits beside block 1, so it follows block 1"


def test_a_payload_comes_out_with_regions_then_their_lines_in_order():
    def poly(x0, y0, x1, y1):
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    payload = {"width": 1000, "height": 1000, "regions": [
        {"id": "low", "type": "text", "polygon": poly(0, 500, 900, 900)},
        {"id": "high", "type": "text", "polygon": poly(0, 50, 900, 400)}],
        "lines": [
            {"region": "low", "polygon": poly(0, 700, 900, 760), "baseline": []},
            {"region": "low", "polygon": poly(0, 520, 900, 580), "baseline": []},
            {"region": "high", "polygon": poly(0, 200, 900, 260), "baseline": []},
            {"region": "high", "polygon": poly(0, 60, 900, 120), "baseline": []}]}
    out = order_payload(payload)
    assert [r["id"] for r in out["regions"]] == ["high", "low"]
    assert [line["polygon"][0][1] for line in out["lines"]] == [60, 200, 520, 700]


def test_a_payload_with_nothing_to_order_is_left_as_it_is():
    payload = {"width": 10, "height": 10, "regions": [], "lines": []}
    assert order_payload(payload) is payload


def test_find_regions_geometry_lists_regions_and_their_lines_in_reading_order():
    """Through `geometry_from_segmentation`: the order Find Regions saves (the Order tab's, the Reader's)."""
    from fichero_server.llm.kraken_runtime import geometry_from_segmentation
    from fichero_server.media.ocr_geometry import OCRGeometryLevel

    def poly(x0, y0, x1, y1):
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    payload = {"width": 1000, "height": 1000, "regions": [
        {"id": "second", "type": "text", "polygon": poly(50, 520, 900, 900)},
        {"id": "first", "type": "text", "polygon": poly(50, 50, 900, 400)}],
        "lines": [
            {"region": "second", "polygon": poly(60, 560, 880, 620), "baseline": []},
            {"region": "first", "polygon": poly(60, 80, 880, 140), "baseline": []}]}
    result = geometry_from_segmentation(payload)
    regions = [b for b in result.boxes if b.level is OCRGeometryLevel.REGION]
    lines = [b for b in result.boxes if b.level is OCRGeometryLevel.LINE]
    assert [round(b.bbox[1], 2) for b in regions] == [0.05, 0.52], "the top block is region 1"
    assert [round(b.bbox[1], 2) for b in lines] == [0.08, 0.56], "and its line comes first"
    assert [b.metadata["line_index"] for b in lines] == [0, 1]
