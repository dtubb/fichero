"""A vertical page's direction comes from the shape of its lines when nothing states it (#5147).

WHY: a script that MAY be vertical (Han, kana, Hangul, Mongolian) resolves `ltr` on purpose --
"may be" is not a direction. But the BULAC Chinese pages state no direction and their lines are
columns, far taller than wide; the page had answered the question, and the Reader drew each
column as a horizontal row. If this regresses, the vertical page reads `ltr` again; if the rule
widens, a horizontal CJK page, or a page whose direction IS stated, stops reading as it says.

The vertical page is the real one (`calfa_chinese-vertical_chi1087-0065.page.xml`); the controls
are built inline. Line shapes are checked with plain lxml, not the engine's reader.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from tests.unit.api.test_page_text_follows_the_file import _import

CORPUS = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus"
VERTICAL = CORPUS / "calfa_chinese-vertical_chi1087-0065.page.xml"
NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"


def _text_blocks(client, doc_id: str) -> list[dict]:
    return client.get(f"/api/segments/document/{doc_id}/text").json()["blocks"]


def _page(lines: list[tuple[str, str]], direction: str | None = None) -> bytes:
    attr = f' readingDirection="{direction}"' if direction else ""
    body = "".join(
        f'<TextLine id="l{i}"{attr}><Coords points="{pts}"/><TextEquiv><Unicode>{text}</Unicode>'
        "</TextEquiv></TextLine>"
        for i, (pts, text) in enumerate(lines)
    )
    return (f'<PcGts xmlns="{NS}"><Page imageFilename="p.jpg" imageWidth="1000" imageHeight="1000">'
            f'<TextRegion id="r"><Coords points="0,0 1000,0 1000,1000 0,1000"/>{body}</TextRegion>'
            "</Page></PcGts>").encode()


def _import_bytes(db, tmp_path: Path, name: str, data: bytes) -> str:
    path = tmp_path / name
    path.write_bytes(data)
    return _import(db, path)


COLUMNS = [(f"{900 - 60 * i},50 {940 - 60 * i},50 {940 - 60 * i},900 {900 - 60 * i},900", t)
           for i, t in enumerate(["北堂書鈔目錄", "卷第一帝王部一", "帝王摠載一"])]
ROWS = [(f"50,{50 + 60 * i} 900,{50 + 60 * i} 900,{90 + 60 * i} 50,{90 + 60 * i}", t)
        for i, (_p, t) in enumerate(COLUMNS)]


def test_the_real_vertical_page_file_is_columns():
    """The premise, from the file: most of its lines are far taller than wide."""
    root = etree.parse(str(VERTICAL)).getroot()  # PAGE 2013: any namespace, by local name
    shapes = []
    for coords in root.iter():
        if not isinstance(coords.tag, str) or etree.QName(coords).localname != "Coords":
            continue
        if etree.QName(coords.getparent()).localname != "TextLine":
            continue
        pts = [tuple(map(float, p.split(","))) for p in coords.get("points").split()]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        shapes.append((max(xs) - min(xs), max(ys) - min(ys)))
    assert sum(1 for w, h in shapes if h >= 2 * w) * 2 > len(shapes)


def test_a_page_of_columns_reads_top_to_bottom(db, client):
    from fichero_server.models import Document

    doc_id = _import(db, VERTICAL)
    # The scan's size, as ingest records it from the image: shapes are measured in its pixels.
    doc = db.get(Document, doc_id)
    doc.metadata = {**(doc.metadata or {}), "width": 2876, "height": 4926}
    db.save(doc)
    blocks = _text_blocks(client, doc_id)
    text_blocks = [b for b in blocks if b.get("spans")]
    assert text_blocks and all(b["direction"] == "ttb" for b in text_blocks), [
        b["direction"] for b in text_blocks]


def test_the_same_text_in_rows_stays_left_to_right(db, client, tmp_path):
    blocks = _text_blocks(client, _import_bytes(db, tmp_path, "rows.xml", _page(ROWS)))
    assert {b["direction"] for b in blocks} == {"ltr"}


def test_the_basis_says_it_came_from_the_shape(db, client, tmp_path):
    doc_id = _import_bytes(db, tmp_path, "cols.xml", _page(COLUMNS))
    assert {b["direction"] for b in _text_blocks(client, doc_id)} == {"ttb"}
    from fichero_server.llm.language_policy import resolve_direction

    resolved = resolve_direction(text="北堂書鈔目錄", lines_are_vertical=True)
    assert resolved.language == "ttb" and "shape of the lines" in resolved.basis


def test_a_stated_direction_wins_over_the_shape(db, client, tmp_path):
    doc_id = _import_bytes(db, tmp_path, "stated.xml", _page(COLUMNS, direction="left-to-right"))
    assert {b["direction"] for b in _text_blocks(client, doc_id)} == {"ltr"}


def test_latin_in_columns_is_not_turned(db, client, tmp_path):
    """Tall boxes of a script that is not written vertically (a narrow margin note) stay ltr."""
    latin = [(pts, "Anno Domini") for pts, _t in COLUMNS]
    doc_id = _import_bytes(db, tmp_path, "latin.xml", _page(latin))
    assert {b["direction"] for b in _text_blocks(client, doc_id)} == {"ltr"}
