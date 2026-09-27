"""A TEI line with no zone of its own is placed in the zone its page break names (#5141).

WHY: the Digital Genji writes `<pb corresp="#zone_0005" .../>` and then bare `<lb/>`s. The file
DOES place those lines -- in that zone, and no more precisely -- but they imported as
`shape: unstated`, anchored to the whole page, and exported with no shape at all. The Genji's
spreads hold two pages each (two zones on one surface), so "somewhere on the image" put every
line on the wrong half as often as the right one. If this regresses, a line's anchor leaves its
zone, or the export stops referring to the zone the file named.

The expected side is read from the file with plain lxml, not with the engine's TEI reader.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.formats import read_page, write_page
from fichero_server.models import Segment
from fichero_server.page_export import page_from_library
from tests.unit.api.test_page_text_follows_the_file import _import

GENJI = (Path(__file__).parents[1] / "formats" / "fixtures" / "corpus"
         / "digitalgenji_japanese-vertical_kouigenji-01.tei.xml")
TEI = "{http://www.tei-c.org/ns/1.0}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def _first_page_by_lxml() -> tuple[str, list[float], list[str]]:
    """The first `<pb>`'s zone id, that zone as a normalised rect on its surface, and the text
    of each line (`<seg>` after an `<lb/>`) up to the next `<pb>`."""
    root = etree.parse(str(GENJI)).getroot()
    body = root.find(f"{TEI}text/{TEI}body")
    pbs = list(body.iter(f"{TEI}pb"))
    zone_id = pbs[0].get("corresp").lstrip("#")
    zone = next(z for z in root.iter(f"{TEI}zone") if z.get(XML_ID) == zone_id)
    surface = zone.getparent()
    sx, sy = float(surface.get("ulx")), float(surface.get("uly"))
    sw, sh = float(surface.get("lrx")) - sx, float(surface.get("lry")) - sy
    ulx, uly, lrx, lry = (float(zone.get(k)) for k in ("ulx", "uly", "lrx", "lry"))
    rect = [(ulx - sx) / sw, (uly - sy) / sh, (lrx - ulx) / sw, (lry - uly) / sh]
    lines, on_page = [], False
    for el in body.iter(f"{TEI}pb", f"{TEI}seg"):
        if el.tag == f"{TEI}pb":
            if on_page:
                break
            on_page = True
        elif on_page:
            lines.append("".join(el.itertext()).strip())
    return zone_id, rect, lines


def _inside(inner: list[float], outer: list[float], tol: float = 1e-6) -> bool:
    return (inner[0] >= outer[0] - tol and inner[1] >= outer[1] - tol
            and inner[0] + inner[2] <= outer[0] + outer[2] + tol
            and inner[1] + inner[3] <= outer[1] + outer[3] + tol)


def test_each_line_is_anchored_inside_its_page_breaks_zone(db):
    zone_id, zone_rect, texts = _first_page_by_lxml()
    assert zone_rect[2] < 1.0, "the zone is half a spread, so the page is not the answer"

    doc_id = _import(db, GENJI)
    lines = sorted((s for s in db.all(Segment) if s.document_id == doc_id and s.kind == "line"),
                   key=lambda s: s.metadata.get("file_position", 0))
    assert [ln.metadata.get("shape") for ln in lines if ln.metadata.get("shape") == "unstated"] == []
    assert len(lines) == len(texts)
    for line in lines:
        assert line.anchor.rect is not None
        assert _inside(list(line.anchor.rect), zone_rect), (line.anchor.rect, zone_rect)


def test_the_export_refers_to_the_zone_and_reads_back_in_it(db):
    zone_id, zone_rect, texts = _first_page_by_lxml()
    doc_id = _import(db, GENJI)
    page, _choices = page_from_library(db, doc_id)
    data, _report = write_page("tei", page)

    root = etree.fromstring(data)
    zones = [z for z in root.iter(f"{TEI}zone")]
    assert [z.get(XML_ID) for z in zones] == [zone_id], "one zone, the file's own, not one per line"
    assert [pb.get("facs") for pb in root.iter(f"{TEI}pb")] == [f"#{zone_id}"]
    assert all(lb.get("facs") is None for lb in root.iter(f"{TEI}lb"))

    again = read_page("tei", data)
    placed = [s for s in again.segments if s.kind == "line"]
    assert len(placed) == len(texts)
    assert all(s.rect is not None and _inside(s.rect, zone_rect, tol=1e-3) for s in placed)
    assert [s.readings[0][1] for s in placed] == texts
