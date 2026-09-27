"""A PAGE file's two statements of order are merged, not one silently preferred (#5145).

WHY: Transkribus writes each region's place twice -- `<ReadingOrder>` and
`custom="readingOrder {index:n;}"` -- and a real file (the USS Albatross logbook, acceptance
re-run 2026-09-27b) names only ONE region in `<ReadingOrder>`, at index 2, while its two tables
say index 0 and 1 in `custom`. Read from the group alone, the named region came first and the
tables after it: the page text and the PAGE export both ran backwards. If this regresses, the
text below reads "notes" before the tables, or a region vanishes, or a disagreement between the
two statements is resolved without the export saying so.

The page here has the logbook's shape (built inline: the logbook itself carries no licence we
may vendor). The expected order is computed from the XML with plain lxml.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.formats import write_page
from fichero_server.page_export import page_from_library
from tests.unit.api.test_page_text_follows_the_file import _import

NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"


def _region(tag: str, rid: str, y: int, text: str, custom: str | None) -> str:
    attr = f' custom="{custom}"' if custom else ""
    line = (f'<TextLine id="{rid}_l"><Coords points="10,{y} 990,{y} 990,{y + 40} 10,{y + 40}"/>'
            f"<TextEquiv><Unicode>{text}</Unicode></TextEquiv></TextLine>")
    inner = line if tag == "TextRegion" else (
        f'<TableCell row="0" col="0" id="{rid}_c"><Coords points="10,{y} 990,{y} 990,{y + 40} 10,{y + 40}"/>'
        f"{line}</TableCell>")
    return (f'<{tag} id="{rid}"{attr}><Coords points="10,{y} 990,{y} 990,{y + 90} 10,{y + 90}"/>'
            f"{inner}</{tag}>")


def _page(order: str, regions: str) -> bytes:
    return (f'<PcGts xmlns="{NS}"><Page imageFilename="p.jpg" imageWidth="1000" imageHeight="1000">'
            f"{order}{regions}</Page></PcGts>").encode()


# The logbook's shape: the notes region is FIRST on the page and the only one the ReadingOrder
# names (index 2); the tables say index 0 and 1 in `custom`; a stray region says nothing.
LOGBOOK = _page(
    '<ReadingOrder><OrderedGroup id="ro"><RegionRefIndexed index="2" regionRef="notes"/>'
    "</OrderedGroup></ReadingOrder>",
    _region("TextRegion", "notes", 10, "NOTES", None)
    + _region("TableRegion", "table_a", 200, "TABLE A", "readingOrder {index:0;}")
    + _region("TableRegion", "table_b", 400, "TABLE B", "readingOrder {index:1;}")
    + _region("TextRegion", "stray", 600, "STRAY", None),
)


def _expected_order(data: bytes) -> list[str]:
    """lxml: every top-level region's index -- the ReadingOrder's where it names one, else the
    custom one -- then regions with neither in file order."""
    import re

    root = etree.fromstring(data)
    named = {el.get("regionRef"): int(el.get("index")) for el in root.iter(f"{{{NS}}}RegionRefIndexed")}
    page = root.find(f"{{{NS}}}Page")
    ranked, rest = [], []
    for position, el in enumerate(e for e in page if etree.QName(e).localname.endswith("Region")):
        rid = el.get("id")
        custom = re.search(r"index:(\d+)", el.get("custom") or "")
        index = named.get(rid, int(custom.group(1)) if custom else None)
        (ranked if index is not None else rest).append((index, position, rid))
    return [rid for *_k, rid in sorted(ranked)] + [rid for *_k, rid in rest]


def _import_bytes(db, tmp_path: Path, data: bytes) -> str:
    path = tmp_path / "p.page.xml"
    path.write_bytes(data)
    return _import(db, path)


def test_the_text_reads_in_the_merged_order_with_no_region_dropped(db, tmp_path):
    expected = _expected_order(LOGBOOK)
    assert expected == ["table_a", "table_b", "notes", "stray"]
    text = document_text(db, _import_bytes(db, tmp_path, LOGBOOK)).text
    positions = [text.index(word) for word in ("TABLE A", "TABLE B", "NOTES", "STRAY")]
    assert positions == sorted(positions), text


def test_the_export_writes_the_same_order_back(db, tmp_path):
    doc_id = _import_bytes(db, tmp_path, LOGBOOK)
    page, _choices = page_from_library(db, doc_id)
    data, _report = write_page("pagexml", page)
    root = etree.fromstring(data)
    words = [u.text for u in root.iter(f"{{{NS}}}Unicode")]
    assert [w for w in words if w in ("TABLE A", "TABLE B", "NOTES", "STRAY")] == [
        "TABLE A", "TABLE B", "NOTES", "STRAY"]
    # The written ReadingOrder, resolved to each region's text, runs the same way.
    text_of = {
        el.get("id"): "".join(u.text or "" for u in el.iter(f"{{{NS}}}Unicode"))
        for el in root.iter() if isinstance(el.tag, str) and etree.QName(el).localname.endswith("Region")
    }
    order = [text_of.get(el.get("regionRef")) for el in root.iter(f"{{{NS}}}RegionRefIndexed")]
    assert [t for t in order if t in ("TABLE A", "TABLE B", "NOTES", "STRAY")] == [
        "TABLE A", "TABLE B", "NOTES", "STRAY"]


def test_a_disagreement_is_resolved_for_the_reading_order_and_reported(db, tmp_path):
    """The ReadingOrder puts `notes` at 0; its own custom says 5. <ReadingOrder> is the
    schema's element for this, so it wins -- and the export's loss report says so."""
    data = _page(
        '<ReadingOrder><OrderedGroup id="ro"><RegionRefIndexed index="0" regionRef="notes"/>'
        '<RegionRefIndexed index="1" regionRef="table_a"/></OrderedGroup></ReadingOrder>',
        _region("TableRegion", "table_a", 200, "TABLE A", None)
        + _region("TextRegion", "notes", 10, "NOTES", "readingOrder {index:5;}"),
    )
    doc_id = _import_bytes(db, tmp_path, data)
    text = document_text(db, doc_id).text
    assert text.index("NOTES") < text.index("TABLE A")
    page, _choices = page_from_library(db, doc_id)
    _data, report = write_page("pagexml", page)
    notes = [loss for loss in report.losses if loss.what == "reading order"]
    assert len(notes) == 1 and "<ReadingOrder> kept" in str(notes[0])
