"""A page's text carries each character once, however many levels of the file carry it (#5148).

WHY: PAGE XML states text at every level, and real files do: the BULAC Chinese table of contents
gives each TextRegion a TextEquiv that is its lines joined. The derived page text read both, so
the Reader showed the page twice -- line by line, then the same lines again as one paragraph --
and search, export and every consumer of `page_content` got the doubled text. A region's own
TextEquiv, where its lines have text, is a rival reading OF THE REGION, not more of the page. If
this regresses, a line's text appears twice in the page text and in the served Reader page.

The expected text is read from the file with plain lxml: the lines' own TextEquiv, in order.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.models.segments import SegmentPass
from tests.unit.api.test_page_text_follows_the_file import _import

NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
BOOT = ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _region(rid: str, y: int, lines: list[str]) -> str:
    body = "".join(
        f'<TextLine id="{rid}_l{i}"><Coords points="10,{y + 50 * i} 990,{y + 50 * i} '
        f'990,{y + 50 * i + 40} 10,{y + 50 * i + 40}"/><TextEquiv><Unicode>{text}</Unicode>'
        "</TextEquiv></TextLine>"
        for i, text in enumerate(lines)
    )
    joined = " ".join(lines)
    return (f'<TextRegion id="{rid}"><Coords points="10,{y} 990,{y} 990,{y + 400} 10,{y + 400}"/>'
            f"{body}<TextEquiv><Unicode>{joined}</Unicode></TextEquiv></TextRegion>")


PAGE = (
    f'<PcGts xmlns="{NS}"><Page imageFilename="p.jpg" imageWidth="1000" imageHeight="1000">'
    + _region("r1", 10, ["北堂書鈔目錄", "卷第一", "帝王部一"])
    + _region("r2", 500, ["北堂書鈔目錄 一"])
    + "</Page></PcGts>"
).encode()


def _lines_by_lxml(data: bytes) -> list[str]:
    root = etree.fromstring(data)
    return [line.find(f"{{{NS}}}TextEquiv/{{{NS}}}Unicode").text for line in root.iter(f"{{{NS}}}TextLine")]


def _imported(db, tmp_path: Path) -> str:
    path = tmp_path / "0065.xml"
    path.write_bytes(PAGE)
    doc_id = _import(db, path)
    [pass_row] = [p for p in db.all(SegmentPass) if p.document_id == doc_id]
    # Choosing the working pass is what writes `page_content`, the text the Reader serves.
    registry.invoke(db, "pass.choose_working", {"document_id": doc_id, "pass_id": pass_row.id}, BOOT)
    return doc_id


def test_the_page_text_is_the_lines_once_in_order(db, tmp_path):
    lines = _lines_by_lxml(PAGE)
    derived = document_text(db, _imported(db, tmp_path))
    # Lines of one horizontal block are joined with a space, blocks with a newline: what is
    # pinned is the SEQUENCE of line texts, each once.
    assert derived.text.split() == " ".join(lines).split(), derived.text
    assert derived.text.count("卷第一") == 1


def test_the_served_reader_page_carries_it_once(db, client, tmp_path):
    doc_id = _imported(db, tmp_path)
    import json
    import re

    html = client.get(f"/view/document/{doc_id}").text
    # The page the Reader renders is `documentData.pages[].content` (the payload also carries
    # `page_content` for offsets; that is the same text, not a second rendering).
    data = json.loads(re.search(r"const documentData = (\{.*?\});\n", html, re.S).group(1))
    [page] = data["pages"]
    # "卷第一" is in ONE line and in its region's joined TextEquiv: twice if both are read.
    assert page["content"].count("卷第一") == 1, page["content"]
    assert page["content"].split() == " ".join(_lines_by_lxml(PAGE)).split()


def test_the_regions_own_reading_is_kept_as_its_reading(db, client, tmp_path):
    """Not reading it into the page is not deleting it: the region still carries its TextEquiv,
    for the readings route and the export."""
    doc_id = _imported(db, tmp_path)
    segs = client.get(f"/api/segments/document/{doc_id}").json()["segments"]
    region = next(s for s in segs if s["kind"] == "region" and "卷第一" in (s.get("text") or ""))
    readings = client.get(f"/api/segments/{region['id']}/readings").json()
    assert any("北堂書鈔目錄 卷第一 帝王部一" == (r.get("content") or r.get("text")) for r in readings["items"])
