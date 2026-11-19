"""`recipes-run.kraken.no-silent-line-loss` (#6673): a line whose polygon Kraken could not build (it stores None) keeps its
baseline with a box round it, so it is still read; the page counts such lines and says so. Fakes, no Kraken."""
from __future__ import annotations

from types import SimpleNamespace

from fichero_server.llm import kraken_runtime as kr


def _line(baseline, boundary):
    return SimpleNamespace(baseline=baseline, boundary=boundary, regions=[])


SEGMENTATION = SimpleNamespace(lines=[
    _line([(10, 100), (210, 104)], [(10, 80), (210, 80), (210, 120), (10, 120)]),
    _line([(20, 300), (320, 300)], None),  # TopologyException: side location conflict
], regions={})


def test_a_line_with_no_polygon_keeps_its_baseline_boxed_round_it():
    lines = kr._raw_lines(SEGMENTATION)
    assert len(lines) == 2
    assert lines[1]["baseline"] == [[20.0, 300.0], [320.0, 300.0]]
    xs = [p[0] for p in lines[1]["polygon"]]
    ys = [p[1] for p in lines[1]["polygon"]]
    assert len(lines[1]["polygon"]) == 4 and min(xs) == 20.0 and max(xs) == 320.0 and min(ys) < 300.0 < max(ys)
    assert lines[1]["boxed"] is True and "boxed" not in lines[0]
    assert kr.boxed_lines(lines) == 1


def test_a_boxed_line_is_a_usable_line_the_reader_reads():
    assert len(kr._usable(kr._raw_lines(SEGMENTATION))) == 2


def test_the_page_says_how_many_lines_were_boxed_and_keeps_every_line(monkeypatch):
    said: list[str] = []
    from fichero_server.execution import jobs

    monkeypatch.setattr(jobs, "note_call_log", said.append)
    lines = kr._raw_lines(SEGMENTATION)
    payload = {"width": 400, "height": 400, "lines": lines, "regions": [], "boxed_lines": kr.boxed_lines(lines)}
    result = kr.geometry_from_segmentation(payload)
    line_boxes = [b for b in result.boxes if b.level is kr.OCRGeometryLevel.LINE]
    assert len(line_boxes) == 2
    assert [b.metadata.get("boxed_from_baseline") for b in line_boxes] == [None, True]
    assert result.metadata["lines_without_outline"] == 1
    assert said == ["1 line had no outline; boxed from their baselines"]


def test_a_line_with_no_baseline_either_is_not_invented():
    lines = kr._raw_lines(SimpleNamespace(lines=[_line([], None)], regions={}))
    assert lines[0]["polygon"] == [] and "boxed" not in lines[0]
