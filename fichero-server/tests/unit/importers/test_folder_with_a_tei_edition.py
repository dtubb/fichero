"""A folder holding a TEI edition and its scans: every page reaches the scan it names (#5143).

WHY: a TEI file is one edition of many pages (`<pb>`), each placed on a `<surface>` whose
`<graphic>` names its scan. Dropped as a folder, the Digital Genji was named "TEI is an edition"
and imported as a text document: no page reached any image. Imported onto one image, it took
the first page and dropped the rest. Here each page pairs with the image its surface names (by
name or stem, a IIIF URL's image part included), each image carries exactly the lines of its
own page breaks -- two printed pages on one scan are one pass -- and pages whose scan is not in
the folder are named, not dropped. If this regresses, an image gets another page's lines, a line
arrives twice, or a page vanishes without a word.

The expected side is read from the file with plain lxml. The folder mirrors the corpus's: the
TEI file and the scans R0000022-R0000027 (blank here; only their names matter).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

import fichero_server.api.routes.document.format_import  # noqa: F401  (registers format.import)
import fichero_server.api.routes.ingest  # noqa: F401  (registers import.folder)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ContentRepresentation, Document
from fichero_server.models.segments import Segment, SegmentPass

GENJI = (Path(__file__).resolve().parents[1] / "formats" / "fixtures" / "corpus"
         / "digitalgenji_japanese-vertical_kouigenji-01.tei.xml")
TEI = "{http://www.tei-c.org/ns/1.0}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
SCANS = [f"R00000{n}.jpg" for n in range(22, 28)]


def _lines_by_scan() -> dict[str, list[str]]:
    """lxml: each `<pb>`'s zone -> its surface -> the scan its graphic names; the page's lines
    are the `<seg>`s up to the next `<pb>`, each one line of print -- a waka inside one
    (`<lg><l>..</l></lg>`) included, with the text that follows it."""
    root = etree.parse(str(GENJI)).getroot()
    scan_of_zone = {}
    for surface in root.iter(f"{TEI}surface"):
        url = surface.find(f"{TEI}graphic").get("url")
        scan = next(part for part in url.split("/") if part.startswith("R0000"))
        for zone in surface.iter(f"{TEI}zone"):
            scan_of_zone[zone.get(XML_ID)] = f"{scan}.jpg"
    lines: dict[str, list[str]] = {}
    scan = None
    for el in root.find(f"{TEI}text").iter(f"{TEI}pb", f"{TEI}seg"):
        if el.tag == f"{TEI}pb":
            scan = scan_of_zone[el.get("corresp").lstrip("#")]
        elif scan is not None:
            lines.setdefault(scan, []).append("".join(el.itertext()).strip())
    return lines


@pytest.fixture
def edition_folder(tmp_path) -> Path:
    from PIL import Image

    folder = tmp_path / "genji"
    folder.mkdir()
    (folder / "kouigenji-01-kiritsubo.tei.xml").write_bytes(GENJI.read_bytes())
    for name in SCANS:
        Image.new("RGB", (69, 47), "white").save(folder / name)
    return folder


def _line_texts(db, document_id: str) -> list[str]:
    [pass_row] = [p for p in db.all(SegmentPass) if p.document_id == document_id]
    lines = sorted((s for s in db.all(Segment) if s.pass_id == pass_row.id and s.kind == "line"),
                   key=lambda s: s.metadata["file_position"])
    text = {r.segment_id: r.content for r in db.query(ContentRepresentation, document_id=document_id)}
    return [text[line.id] for line in lines]


def _all_texts(db, document_id: str) -> list[str]:
    return [r.content for r in db.query(ContentRepresentation, document_id=document_id)]


def test_each_scan_carries_exactly_the_lines_of_its_own_pages(db, edition_folder):
    expected = _lines_by_scan()
    ctx = ActionContext(actor="historian", library_path=str(Path(db.path).parent), is_bootstrap=True)
    result = registry.invoke(db, "import.folder", {"path": str(edition_folder)}, ctx).result
    report = result["interchange"]
    assert report["not_imported"] == {}

    documents = {d.name: d for d in (db.get(Document, i) for i in result["document_ids"]) if d}
    assert "kouigenji-01-kiritsubo.tei.xml" not in documents, "the edition is passes, not a text document"
    for scan in SCANS:
        doc_id = documents[scan].id
        # Line for line, in order: nothing dropped, nothing duplicated, no page's lines on
        # another's scan -- and no text beyond the lines (a waka read as five regions put its
        # verses beside the line and lost the text after the poem).
        assert _line_texts(db, doc_id) == expected[scan], scan
        assert sorted(_all_texts(db, doc_id)) == sorted(expected[scan]), scan

    # Nothing dropped silently: every page whose scan is not in the folder is named.
    [(name, why)] = report["unpaired"].items()
    assert name == "kouigenji-01-kiritsubo.tei.xml"
    root = etree.parse(str(GENJI)).getroot()
    elsewhere = [pb for pb in root.find(f"{TEI}text").iter(f"{TEI}pb")
                 if _scan_of(root, pb) not in SCANS]
    assert elsewhere, "the corpus file has pages whose scans are not in the folder"
    assert why.startswith(f"{len(elsewhere)} of ")
    for pb in elsewhere:
        assert f"page {pb.get('n')} ({pb.get('corresp')})" in why


def _scan_of(root, pb) -> str:
    zone_id = pb.get("corresp").lstrip("#")
    zone = next(z for z in root.iter(f"{TEI}zone") if z.get(XML_ID) == zone_id)
    url = zone.getparent().find(f"{TEI}graphic").get("url")
    return next(part for part in url.split("/") if part.startswith("R0000")) + ".jpg"


def test_dropping_it_again_duplicates_no_pass(db, edition_folder):
    ctx = ActionContext(actor="historian", library_path=str(Path(db.path).parent), is_bootstrap=True)
    registry.invoke(db, "import.folder", {"path": str(edition_folder)}, ctx)
    before = len(db.all(SegmentPass))
    registry.invoke(db, "import.folder", {"path": str(edition_folder)}, ctx)
    assert len(db.all(SegmentPass)) == before
