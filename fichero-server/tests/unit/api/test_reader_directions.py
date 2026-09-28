"""The Reader lays a page out in its own direction (#5147, Reader half), and a line move patches
the page in place with the caret still on the moved line (#5170).

WHY: the engine resolves every line's direction (rtl from the letters, ttb from the shape of the
lines), but the Reader drew every page left to right in rows -- an Arabic folio read backwards
line-end first, a Chinese page of columns came out as rows, and a Latin folio number on a Syriac
page was laid out as if it were Syriac. And after ⌥⌘↑/↓ or its ⌘Z the app reloaded the whole
page, losing scroll and caret, so moving several lines meant finding the line again after every
key. If this regresses, a right-to-left or vertical page renders as if it were English, or the
caret jumps away after a move.

What each file SAYS is read with plain lxml; the page's functions are cut from the SERVED HTML and
run in node (a source scan would pass with them broken).
"""

from __future__ import annotations

import json
import shutil
import unicodedata
from pathlib import Path

import pytest
from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.models import DocType, Document, FileType, Status
from tests.unit.api.test_page_text_follows_the_file import BOOT
from tests.unit.api.test_reader_line_map import _node, _view

CORPUS = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus"
ARABIC = CORPUS / "calfa_arabic-baseline-only_rasam417-0010.page.xml"
SYRIAC = CORPUS / "escriptorium_syriac_onb-syr1-0001.page.xml"
CHINESE = CORPUS / "calfa_chinese-vertical_chi1087-0065.page.xml"
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="needs node to run the page's own script")


def _import(db, path: Path) -> str:
    """A page document as ingest makes it -- with the scan's pixel size, which line shapes are
    measured in (the BULAC Chinese scan is 2876 x 4926) -- then the file through format.import."""
    doc = Document(name=path.stem, doc_type=DocType.file, file_type=FileType.image,
                   path=f"/p/{path.stem}.jpg", status=Status.completed,
                   metadata={"width": 2876, "height": 4926} if path == CHINESE else {})
    db.save(doc)
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(path)}, BOOT)
    return doc.id


def _line_texts(path: Path) -> list[str]:
    """Each PAGE TextLine's own TextEquiv/Unicode, by lxml."""
    root = etree.parse(str(path)).getroot()
    out = []
    for line in root.iter("{*}TextLine"):
        own = [u for u in line.iterfind("{*}TextEquiv/{*}Unicode")]
        out.append("".join(own[0].itertext()) if own else "")
    return out


def _letters(text: str) -> str:
    """'rtl' when the text's letters are Hebrew/Arabic/Syriac, 'ltr' when Latin, '' when none."""
    classes = {unicodedata.bidirectional(ch) for ch in text if ch.isalpha()}
    return "rtl" if classes & {"R", "AL"} else "ltr" if "L" in classes else ""


def _page_functions(html: str) -> str:
    start = html.index("function escapeHtml(text)")
    end = html.index("\n}\n", html.index("function transcriptPageMarkup(page)")) + 3
    return "globalThis.window = {};\n" + html[start:end]


def _body(html: str, page: dict) -> str:
    return _node(_page_functions(html) + f"""
console.log(JSON.stringify(pageBodyMarkup({json.dumps({"content": page["content"], "lines": page["lines"]})})));
""")


def test_each_line_in_the_map_says_its_direction(db, client):
    """The Syriac page's lines are Syriac letters, and one is its Latin folio number; the map
    says rtl and ltr of exactly those lines."""
    doc_id = _import(db, SYRIAC)
    page = _view(client, doc_id)[0]["pages"][0]
    by_file = {_letters(t) for t in _line_texts(SYRIAC) if _letters(t)}
    assert by_file == {"rtl", "ltr"}, "the file has a Latin line on a Syriac page"
    for line in page["lines"]:
        text = page["content"][line["char_start"]:line["char_end"]]
        if _letters(text):
            assert line["direction"] == _letters(text), text


@needs_node
def test_an_rtl_page_is_laid_out_right_to_left(db, client):
    doc_id = _import(db, ARABIC)
    assert {_letters(t) for t in _line_texts(ARABIC) if _letters(t)} == {"rtl"}
    payload, html = _view(client, doc_id)
    body = _body(html, payload["pages"][0])
    assert body.startswith('<div class="transcript-page-body" dir="rtl">')
    assert "<span" not in body                       # one direction: one text node, as before


@needs_node
def test_a_latin_line_on_a_syriac_page_is_its_own_isolate(db, client):
    """The page is rtl; the folio number is an ltr isolate. The text is untouched -- tags
    stripped, it is the page text to the character, so every offset walk still lands."""
    doc_id = _import(db, SYRIAC)
    payload, html = _view(client, doc_id)
    page = payload["pages"][0]
    body = _body(html, page)
    assert body.startswith('<div class="transcript-page-body" dir="rtl">')
    latin = [t.strip() for t in _line_texts(SYRIAC) if _letters(t) == "ltr"]
    for text in latin:
        assert f'<span dir="ltr">{text}' in body, body[:400]
    inner = body[body.index(">") + 1:body.rindex("</div>")]
    stripped = inner.replace('<span dir="ltr">', "").replace("</span>", "")
    assert stripped.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&") == page["content"]


@needs_node
def test_a_page_of_columns_is_laid_out_in_columns(db, client):
    """The BULAC Chinese page's lines are columns (every line far taller than wide, by lxml);
    the engine says ttb, and the Reader lays it vertical-rl."""
    root = etree.parse(str(CHINESE)).getroot()
    tall = 0
    lines = list(root.iter("{*}TextLine"))
    for line in lines:
        points = [tuple(map(int, p.split(","))) for p in line.find("{*}Coords").get("points").split()]
        xs, ys = [x for x, _ in points], [y for _, y in points]
        tall += (max(ys) - min(ys)) >= 2 * (max(xs) - min(xs))
    assert tall > len(lines) / 2
    doc_id = _import(db, CHINESE)
    payload, html = _view(client, doc_id)
    assert _body(html, payload["pages"][0]).startswith('<div class="transcript-page-body" data-direction="ttb">')
    assert 'data-direction="ttb"] {\n            writing-mode: vertical-rl;' in html


@needs_node
@pytest.mark.parametrize("path", [ARABIC, CHINESE], ids=["rtl", "vertical"])
def test_after_a_move_the_caret_is_on_the_moved_line(db, client, path):
    """The page re-reads itself from the served view and puts the caret back the same distance
    into the moved line, in the NEW offsets -- in an rtl page and in a page of columns."""
    from tests.unit.api.test_text_follows_the_order import _move_last_line_of_a_block_to_its_start

    doc_id = _import(db, path)
    before = _view(client, doc_id)[0]["pages"][0]
    _audit, moved, _first = _move_last_line_of_a_block_to_its_start(db, client, doc_id)
    old = next(line for line in before["lines"] if line["segment_id"] == moved)
    old_offset = old["char_start"] + (old["char_end"] - old["char_start"]) // 2
    _, html_after = _view(client, doc_id)
    got = _node(_page_functions(html_after) + f"""
const fresh = pagePayloadFromView({json.dumps(html_after)}, {json.dumps(before["id"])});
const offset = caretAfterMove({json.dumps(before["lines"])}, fresh.lines, {json.dumps(moved)}, {old_offset});
const line = fresh.lines.find((l) => l.segment_id === {json.dumps(moved)});
console.log(JSON.stringify({{ on: segmentAtOffset(fresh.lines, offset), into: offset - line.char_start,
                              moved: fresh.lines.findIndex((l) => l.segment_id === {json.dumps(moved)}) }}));
""")
    assert got["on"] == moved
    assert got["into"] == old_offset - old["char_start"]
    assert got["moved"] != next(i for i, l in enumerate(before["lines"]) if l["segment_id"] == moved)


GENJI = CORPUS / "digitalgenji_japanese-vertical_kouigenji-01.tei.xml"


@needs_node
def test_a_direction_set_on_the_page_reaches_the_reader_at_once(db, client):
    """#5171: the Genji states no writing mode (lxml), so it reads `ltr` until a person says
    `ttb`. Saying so changes no text, so nothing refreshed the stored map and the Reader kept
    drawing rows. The direction is resolved at render; the next view is columns."""
    root = etree.parse(str(GENJI)).getroot()
    assert not any("vertical" in (el.get("rend") or "") + (el.get("style") or "")
                   for el in root.iter() if isinstance(el.tag, str))
    doc_id = _import(db, GENJI)
    payload, html = _view(client, doc_id)
    assert _body(html, payload["pages"][0]).startswith('<div class="transcript-page-body">')
    registry.invoke(db, "source_setting.set",
                    {"level": "node", "key": "direction", "value": "ttb", "target_id": doc_id}, BOOT)
    payload, html = _view(client, doc_id)
    assert {line["direction"] for line in payload["pages"][0]["lines"]} == {"ttb"}
    assert _body(html, payload["pages"][0]).startswith('<div class="transcript-page-body" data-direction="ttb">')


def test_undoing_the_direction_puts_the_reader_back_at_once(db, client):
    """#5171 and its ⌘Z: the setting is an audited action, so its undo (the app's ⌘Z) must reach
    the Reader as directly as the setting did -- rows again, without a restart."""
    doc_id = _import(db, GENJI)
    made = client.post("/api/actions/invoke", json={"name": "source_setting.set", "params": {
        "level": "node", "key": "direction", "value": "ttb", "target_id": doc_id}})
    assert made.status_code == 200, made.text
    payload, html = _view(client, doc_id)
    assert _body(html, payload["pages"][0]).startswith('<div class="transcript-page-body" data-direction="ttb">')
    undone = client.post(f"/api/actions/audit/{made.json()['audit_id']}/undo")
    assert undone.status_code == 200, undone.text
    payload, html = _view(client, doc_id)
    assert {line["direction"] for line in payload["pages"][0]["lines"]} != {"ttb"}
    assert _body(html, payload["pages"][0]).startswith('<div class="transcript-page-body">')
