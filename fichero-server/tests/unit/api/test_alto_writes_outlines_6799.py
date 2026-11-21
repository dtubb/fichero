"""An ALTO export writes a segment's outline, not only its box (#6799, `source.format.alto-out-outlines`).

WHY: measured 2026-11-20, 0 `Polygon` elements in 10 ALTO exports of 1,044 Kraken lines (a median
of 71 points a line came out as the 4 corners of its box), and 0 in re-exports of eScriptorium
ALTO files that arrived with over a hundred line polygons each. Each test goes through a library:
segments made the way a segmenter makes them, or a real file imported, then `page_from_library`,
the ALTO writer (which validates against the vendored ALTO 4.4 XSD) and the ALTO reader.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.formats import read_page, write_page
from fichero_server.formats.harness import xml_id
from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.models.anchors import SourceAnchor
from fichero_server.page_export import page_from_library
from tests.unit.api.test_page_text_follows_the_file import CLM, _import

pytestmark = pytest.mark.source_model

KRAKEN = ActionContext(actor="kraken", run_id="run-1", library_path=None, is_bootstrap=True)


def _local(el) -> str:
    return etree.QName(el).localname


def _polygons(data: bytes) -> dict[str, list[list[float]]]:
    """Each element's `Shape/Polygon` points in the file's unit, by the element's ID."""
    root = etree.fromstring(data)
    out = {}
    for el in root.iter():
        if not isinstance(el.tag, str) or _local(el) not in ("TextBlock", "TextLine", "String"):
            continue
        for shape in (c for c in el if _local(c) == "Shape"):
            numbers = [float(n) for n in shape[0].get("POINTS").replace(",", " ").split()]
            out[el.get("ID")] = [numbers[i:i + 2] for i in range(0, len(numbers), 2)]
    return out


def _wavy_line(n: int) -> list[list[float]]:
    """A Kraken-shaped line outline of `n` points: a top edge and a bottom edge that wander."""
    top = [[0.1 + 0.8 * i / (n // 2 - 1), 0.30 + 0.004 * math.sin(i)] for i in range(n // 2)]
    bottom = [[0.9 - 0.8 * i / (n - n // 2 - 1), 0.34 + 0.004 * math.cos(i)] for i in range(n - n // 2)]
    return top + bottom


def _segment(db, doc_id: str, pass_id: str, kind: str, polygon, parent: str | None = None) -> str:
    body = {
        "document_id": doc_id, "pass_id": pass_id, "kind": kind,
        "anchor": SourceAnchor(document_id=doc_id, polygon=polygon).model_dump(mode="json"),
    }
    if parent:
        body["parent_segment_id"] = parent
    return registry.invoke(db, "segment.create", body, KRAKEN).result["segment_ids"][0]


def test_a_71_point_line_goes_out_as_its_outline_and_comes_back_with_the_same_points(db):
    doc = Document(name="c01_012.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/p/c01_012.jpg", status=Status.completed)
    db.save(doc)
    pass_id = registry.invoke(db, "segment.pass_create", {"document_id": doc.id, "name": "kraken"}, KRAKEN).result["id"]
    region = _segment(db, doc.id, pass_id, "region",
                      [[0.08, 0.28], [0.5, 0.27], [0.92, 0.28], [0.92, 0.36], [0.08, 0.36]])
    line = _segment(db, doc.id, pass_id, "line", _wavy_line(71), parent=region)
    word = _segment(db, doc.id, pass_id, "word",
                    [[0.1, 0.30], [0.2, 0.299], [0.21, 0.32], [0.2, 0.34], [0.1, 0.341], [0.095, 0.32]], parent=line)
    registry.invoke(db, "representation.create", {
        "document_id": doc.id, "segment_id": word, "kind": "transcription", "content": "un"}, KRAKEN)

    page, _ = page_from_library(db, doc.id)
    data, report = write_page("alto", page)   # validated against the vendored ALTO 4.4 XSD
    written = _polygons(data)
    by_ref = {s.ref: s for s in page.segments}
    assert {len(points) for points in written.values()} == {5, 71, 6}, written.keys()
    assert "outlines" not in report.lost

    width, height = (int(etree.fromstring(data).find(".//{*}Page").get(n)) for n in ("WIDTH", "HEIGHT"))
    back = {s.ref: s for s in read_page("alto", data).segments}
    for ref in (region, line, word):
        sent, got = by_ref[ref].polygon, back[xml_id(ref)].polygon
        assert len(got) == len(sent), ref
        # The file holds whole pixels, so a point comes back within half a pixel of where it went.
        for (sx, sy), (gx, gy) in zip(sent, got):
            assert abs(sx - gx) * width <= 0.5 and abs(sy - gy) * height <= 0.5, (ref, sx, sy, gx, gy)


def test_a_real_escriptorium_page_keeps_its_line_and_block_outlines_through_the_library(db):
    source = etree.parse(str(CLM)).getroot()
    # Every outline the file drew but one: a block whose polygon is its own box (four corners), which
    # ALTO's box already says.
    outlines = [el for el in source.iter() if isinstance(el.tag, str) and _local(el) == "Polygon"]
    assert len(outlines) == 125
    expected = len(outlines) - 1
    doc_id = _import(db, CLM)
    page, _ = page_from_library(db, doc_id)
    data, _report = write_page("alto", page)
    assert len(_polygons(data)) == expected


def test_a_box_is_written_as_a_box_and_not_as_a_four_point_shape(db):
    """ALTO's `Shape` is "the bounding shape of a block, if it is not rectangular"."""
    doc = Document(name="boxes.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/p/boxes.jpg", status=Status.completed)
    db.save(doc)
    pass_id = registry.invoke(db, "segment.pass_create", {"document_id": doc.id, "name": "apple"}, KRAKEN).result["id"]
    registry.invoke(db, "segment.create", {
        "document_id": doc.id, "pass_id": pass_id, "kind": "line",
        "anchor": SourceAnchor(document_id=doc.id, rect=[0.1, 0.2, 0.6, 0.04]).model_dump(mode="json"),
    }, KRAKEN)
    page, _ = page_from_library(db, doc.id)
    data, _report = write_page("alto", page)
    assert _polygons(data) == {}
