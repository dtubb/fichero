"""A split carries each line and its readings to the page it falls on (#5452).

Spec: `source.split.carries-readings-over`. A spread is read (three lines: one on the left page, one
on the right, one reaching across the gutter), then split through the route's own split. Each half
must hold its lines with their readings, re-normalised to the half, the spread must keep everything,
and a recipe's "already done" must see the work on the halves.
"""
from __future__ import annotations

from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.api.routes.ingest.image_editing import split_image_impl
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import (
    Artifact,
    ContentRepresentation,
    DocType,
    Document,
    FileType,
    Segment,
    SegmentPass,
)
from fichero_server.recipes import done
from PIL import Image


class _SplitRequest:
    def __init__(self, bboxes):
        self.bboxes = bboxes


def _box(x: float, y: float, w: float, text: str, start: int) -> OCRGeometryBox:
    h = 0.05
    px = lambda fx, fy: [round(fx * 1000), round(fy * 1000)]
    return OCRGeometryBox(
        text=text, bbox=[x, y, w, h], level="line", confidence=0.9, char_start=start, char_end=start + len(text),
        provider="openai", model="gpt-4o",
        metadata={"polygon_px": [px(x, y), px(x + w, y), px(x + w, y + h), px(x, y + h)],
                  "baseline_px": [px(x, y + h * 0.8), px(x + w, y + h * 0.8)], "pixel_frame": {"width": 1000, "height": 1000}})


def _read_spread(db, tmp_path):
    path = tmp_path / "spread.png"
    Image.new("RGB", (1000, 1000), "white").save(path)
    spread = Document(name="spread", doc_type=DocType.file, file_type=FileType.image, path=str(path))
    db.save(spread)
    lines = [("left page line", 0.05, 0.10, 0.30), ("right page line", 0.60, 0.30, 0.30),
             ("across the gutter", 0.40, 0.50, 0.30)]
    content, boxes = "", []
    for text, x, y, w in lines:
        boxes.append(_box(x, y, w, text, len(content)))
        content += text + "\n"
    db.save(Artifact(document_id=spread.id, artifact_type="transcription", provider="openai", model="gpt-4o",
                     content=content, ocr_geometry=OCRGeometryResult(provider="openai", text=content, boxes=boxes)))
    return spread


def _split(db, spread):
    left, right = split_image_impl(db, spread.id, _SplitRequest([(0, 0, 500, 1000), (500, 0, 500, 1000)]))
    return left, right


def _lines(db, doc_id):
    out = []
    for pass_row in db.query(SegmentPass, document_id=doc_id):
        out += [s for s in db.query(Segment, pass_id=pass_row.id) if s.deleted_at is None and s.kind == "line"]
    return out


def _text(db, segment):
    return next(r.content for r in db.query(ContentRepresentation, segment_id=segment.id))


def test_each_line_and_its_reading_goes_to_the_half_it_falls_on(db, tmp_path):
    spread = _read_spread(db, tmp_path)
    left, right = _split(db, spread)
    assert sorted(_text(db, s) for s in _lines(db, left.id)) == ["left page line"]
    assert sorted(_text(db, s) for s in _lines(db, right.id)) == ["across the gutter", "right page line"]
    line = next(s for s in _lines(db, right.id) if _text(db, s) == "right page line")
    # 0.60..0.90 of the spread is 0.2..0.8 of the right half; the polygon moved the same way.
    assert [round(v, 6) for v in line.anchor.rect[:1] + line.anchor.rect[2:3]] == [0.2, 0.6]
    assert round(min(p[0] for p in line.anchor.polygon), 6) == 0.2
    assert line.document_id == right.id and line.anchor.document_id == right.id
    assert document_text(db, left.id).text.strip() == "left page line"
    assert "right page line" in document_text(db, right.id).text


def test_a_line_across_the_gutter_is_flagged_and_kept_whole(db, tmp_path):
    spread = _read_spread(db, tmp_path)
    _left, right = _split(db, spread)
    crossing = next(s for s in _lines(db, right.id) if _text(db, s) == "across the gutter")
    assert crossing.metadata["crosses_gutter"] is True
    assert crossing.anchor.rect[0] == 0.0  # clamped to the half, not cut into two lines
    other = next(s for s in _lines(db, right.id) if _text(db, s) == "right page line")
    assert "crosses_gutter" not in other.metadata


def test_the_spread_keeps_its_passes_and_readings(db, tmp_path):
    spread = _read_spread(db, tmp_path)
    _split(db, spread)  # converts the result's boxes to a pass, then carries; the spread's own copy stays
    assert sorted(_text(db, s) for s in _lines(db, spread.id)) == ["across the gutter", "left page line", "right page line"]
    assert len(db.query(Artifact, document_id=spread.id)) == 1


def test_a_recipe_sees_the_work_done_on_the_halves(db, tmp_path):
    left, right = _split(db, _read_spread(db, tmp_path))
    for half in (left, right):
        assert done.is_done(db, {"job": "find-lines"}, half.id) is True
        assert done.is_done(db, {"job": "read-a-line"}, half.id) is True


def test_the_workflow_split_carries_the_same_way(db, tmp_path, test_package):
    """The Split Pages workflow cuts the same halves; its children get the same carried lines."""
    from fichero_server.workflows.tools.image_edit_chains import (
        persist_workflow_child_regions,
    )

    spread = _read_spread(db, tmp_path)
    parts = []
    for n, bbox in enumerate(([0, 0, 500, 1000], [500, 0, 500, 1000]), start=1):
        out = tmp_path / "parts" / f"p{n}.png"
        out.parent.mkdir(exist_ok=True)
        Image.new("RGB", (500, 1000), "white").save(out)
        parts.append({"bbox": bbox, "source_size": [1000, 1000], "output_file": str(out)})
    report = persist_workflow_child_regions(
        {"documents": [{"id": spread.id}], "library_path": str(test_package)}, {},
        results=[{"source": spread.path, "parts": parts}],
        part_key="parts", role="split_part", method="workflow-split", name="part")
    left, right = (db.get(Document, c["document_id"]) for c in report["children"])
    assert [_text(db, s) for s in _lines(db, left.id)] == ["left page line"]
    assert sorted(_text(db, s) for s in _lines(db, right.id)) == ["across the gutter", "right page line"]
    assert report["carried"][0]["lines"] == 3 and report["carried"][0]["crossing"] == 1


def test_regions_and_words_go_with_their_lines_and_keep_their_parents(db, tmp_path):
    """A region, its line and the line's words on the left page all go to the left half, each still inside the
    one it sat in; a word whose centre is past the gutter still goes with its line.
    WHY: carrying only lines left a half's words and regions on the spread, so a word-level read or a region
    step on the half found nothing and ran again."""
    import fichero_server.api.main  # noqa: F401  (registers every action)
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.models.anchors import SourceAnchor

    spread = _read_spread(db, tmp_path)
    ctx = ActionContext(actor="kraken", run_id="run-1", library_path=None, is_bootstrap=True)
    pass_id = registry.invoke(db, "segment.pass_create", {"document_id": spread.id, "name": "regions"}, ctx).result["id"]

    def make(kind, rect, parent=None):
        return registry.invoke(db, "segment.create", {
            "document_id": spread.id, "pass_id": pass_id, "kind": kind, "parent_segment_id": parent,
            "anchor": SourceAnchor(document_id=spread.id, rect=rect).model_dump(mode="json")}, ctx).result["segment_ids"][0]

    region = make("region", [0.05, 0.6, 0.4, 0.2])
    line = make("line", [0.05, 0.65, 0.4, 0.05], region)
    make("word", [0.05, 0.65, 0.1, 0.05], line)
    make("word", [0.47, 0.65, 0.06, 0.05], line)  # its centre is just past the gutter
    left, right = _split(db, spread)
    carried = [s for p in db.query(SegmentPass, document_id=left.id) for s in db.query(Segment, pass_id=p.id)
               if s.metadata.get("carried_from_segment_id") in {region, line} or s.kind == "word"]
    by_kind = {k: [s for s in carried if s.kind == k] for k in ("region", "line", "word")}
    assert len(by_kind["region"]) == 1 and len(by_kind["line"]) == 1 and len(by_kind["word"]) == 2
    assert by_kind["line"][0].parent_segment_id == by_kind["region"][0].id
    assert all(w.parent_segment_id == by_kind["line"][0].id for w in by_kind["word"])
    assert not [s for p in db.query(SegmentPass, document_id=right.id) for s in db.query(Segment, pass_id=p.id)
                if s.kind == "word"]


def test_a_line_goes_by_its_own_centre_even_inside_a_region_that_crosses_the_gutter(db, tmp_path):
    """A region drawn over the whole spread (its centre on the left page) holds a line on the right page: the line
    goes to the right half, by its own centre, not the region's.
    WHY: following the region moved a whole page of lines to the wrong half."""
    import fichero_server.api.main  # noqa: F401  (registers every action)
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.models.anchors import SourceAnchor

    spread = _read_spread(db, tmp_path)
    ctx = ActionContext(actor="kraken", run_id="run-1", library_path=None, is_bootstrap=True)
    pass_id = registry.invoke(db, "segment.pass_create", {"document_id": spread.id, "name": "regions"}, ctx).result["id"]

    def make(kind, rect, parent=None):
        return registry.invoke(db, "segment.create", {
            "document_id": spread.id, "pass_id": pass_id, "kind": kind, "parent_segment_id": parent,
            "anchor": SourceAnchor(document_id=spread.id, rect=rect).model_dump(mode="json")}, ctx).result["segment_ids"][0]

    region = make("region", [0.02, 0.6, 0.9, 0.3])  # centre 0.47: the left page
    line = make("line", [0.6, 0.7, 0.3, 0.05], region)  # centre 0.75: the right page
    left, right = _split(db, spread)
    on = lambda doc: {s.metadata.get("carried_from_segment_id") for p in db.query(SegmentPass, document_id=doc.id)
                      for s in db.query(Segment, pass_id=p.id)}
    assert line in on(right) and line not in on(left)
