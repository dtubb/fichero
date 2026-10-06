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
import os
import re
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
    assert "<span dir" not in body                   # one direction: no isolate, as before


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
    # Every tag stripped -- the isolates and the line breaks (#5208) -- leaves the page text.
    stripped = re.sub(r"<[^>]+>", "", inner)
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


# A fake DOM just big enough for the page's OWN refreshPage/caretInBody/bodyOffset: one article,
# one page body holding one text node, a selection and a scroll container. Swapping the body drops
# the scroll to the top -- what a browser may do when the focused element leaves the page and the
# caret is put back -- so a kept scroll is kept by the page, not by the stand-in.
_FAKE_DOM = r"""
// refreshPage redraws the region rules (#5426) after a patch; they are pinned by test_reader_region_rules.py,
// and this fake DOM has no layout to measure them in, so here that call does nothing.
function applyRegionRules() {}
const scroller = { scrollTop: 0 };
const textOf = (html) => html.replace(/<[^>]*>/g, "").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
const article = { querySelector: () => article.body, closest: () => article };
function makeBody(html) {
    const body = { nodeType: 1, closest: (sel) => sel.startsWith("article") ? article : body };
    body.text = { nodeType: 3, nodeValue: textOf(html), parentElement: body };
    Object.defineProperty(body, "textContent", { get: () => body.text.nodeValue });
    Object.defineProperty(body, "outerHTML", { set: (markup) => { article.body = makeBody(markup); scroller.scrollTop = 0; } });
    return body;
}
const selection = { focusNode: null, focusOffset: 0, collapse(node, offset) { this.focusNode = node; this.focusOffset = offset; } };
globalThis.Node = { TEXT_NODE: 3 };
globalThis.NodeFilter = { SHOW_TEXT: 4 };
globalThis.CSS = { escape: (s) => s };
globalThis.document = {
    querySelector: () => article,
    createTreeWalker: (body) => { let done = false; return { nextNode: () => (done ? null : (done = true, body.text)) }; },
};
window.getSelection = () => selection;
var pendingEdit = null;
const staleLines = new Map();
const documentData = { pages: [] };
function sourceHeaders() { return {}; }
function scrollParent() { return scroller; }
function makeEditable() {}
function applyShownLines() {}
function applyStaleHighlight() {}
const served = [];
globalThis.fetch = async () => ({ ok: true, text: async () => served.shift() });
"""


@needs_node
def test_a_move_and_its_undo_keep_the_scroll_and_the_caret(db, client):
    """#5170 through the page's OWN refreshPage, across a real move AND its ⌘Z (the audit undo the
    app calls): the scroll stays where the person left it and the caret stays on the moved line,
    the same distance in -- and after the undo it is back at the very offset it started from. If
    this regresses, every ⌥⌘↑/↓ or ⌘Z throws the person back to the top, or off the line."""
    from tests.unit.api.test_text_follows_the_order import _move_last_line_of_a_block_to_its_start

    doc_id = _import(db, ARABIC)
    before, html_before = _view(client, doc_id)
    page = before["pages"][0]
    audit_id, moved, _first = _move_last_line_of_a_block_to_its_start(db, client, doc_id)
    _, html_moved = _view(client, doc_id)
    undone = client.post(f"/api/actions/audit/{audit_id}/undo")
    assert undone.status_code == 200, undone.text
    _, html_undone = _view(client, doc_id)
    line = next(l for l in page["lines"] if l["segment_id"] == moved)
    start = line["char_start"] + (line["char_end"] - line["char_start"]) // 2
    got = _node(_page_functions(html_before) + _FAKE_DOM + f"""
const page = {json.dumps(page)};
pageLineMaps.set(page.id, page.lines);
pageTexts.set(page.id, page.content);
article.dataset = {{ pageId: page.id }};
article.body = makeBody(pageBodyMarkup(page));
const premise = article.body.text.nodeValue === page.content;
selection.collapse(article.body.text, {start});
scroller.scrollTop = 1234;
const where = () => {{ const at = lineAtCaret(); return {{ scroll: scroller.scrollTop, on: at && at.segmentId,
    offset: selection.focusOffset, lines: pageLineMaps.get(page.id).map((l) => l.segment_id) }}; }};
(async () => {{
    served.push({json.dumps(html_moved)}, {json.dumps(html_undone)});
    const movedOk = await refreshPage(page.id);
    const afterMove = where();
    const undoneOk = await refreshPage(page.id);
    console.log(JSON.stringify({{ premise, movedOk, afterMove, undoneOk, afterUndo: where() }}));
}})();
""")
    assert got["premise"] and got["movedOk"] and got["undoneOk"]
    ids = [l["segment_id"] for l in page["lines"]]
    assert got["afterMove"]["lines"] != ids                          # the move really moved the line
    moved_line = next(l for l in pagePayload(html_moved, page["id"])["lines"] if l["segment_id"] == moved)
    assert got["afterMove"] == {**got["afterMove"], "scroll": 1234, "on": moved,
                                "offset": moved_line["char_start"] + (start - line["char_start"])}
    assert got["afterUndo"] == {"scroll": 1234, "on": moved, "offset": start, "lines": ids}   # back where it began


def pagePayload(html: str, page_id: str) -> dict:
    import re
    data = json.loads(re.search(r"const documentData = (\{.*?\});\n", html, re.S).group(1))
    return next(p for p in data["pages"] if p["id"] == page_id)


@needs_node
def test_each_manuscript_line_is_its_own_line_and_the_text_is_unchanged(db, client):
    """#5208 (Daniel): the Reader flowed a region's lines as one paragraph, but a diplomatic reading keeps
    the manuscript's lines. Each separator between two lines of the map is wrapped as a `.line-break`,
    which the page's CSS follows with a line break (a new column in a `ttb` page). WHY the text must be
    unchanged: every caret, claim and search offset walks these text nodes; if the break were a
    character, or dropped the separator, each of them would land one place off per line."""
    import html as html_module

    doc_id = _import(db, SYRIAC)
    payload, html = _view(client, doc_id)
    page = payload["pages"][0]
    body = _body(html, page)
    lines = page["lines"]
    joined = sum(1 for a, b in zip(lines, lines[1:]) if b["char_start"] == a["char_end"] + 1)
    assert joined >= 2, "the recorded page has several lines to break between"
    assert body.count('<span class="line-break">') == joined, "one break per boundary, no more"
    assert html_module.unescape(re.sub(r"<[^>]+>", "", body)) == page["content"], "not one character moved"
    assert ".line-break::after" in html and 'content: "\\A"' in html, "the served page draws the break"


APP_FIXTURES = next(p for p in Path(__file__).resolve().parents if (p / "fichero" / "Tests").is_dir()) \
    / "fichero" / "Tests" / "Fixtures" / "segments"


def _stable_text(answer: dict) -> dict:
    """The /text answer with its random ids replaced by tokens in order of appearance, so the recorded
    fixture only drifts when the ANSWER does."""
    tokens: dict[str, str] = {}

    def token(value, prefix):
        if value is None:
            return None
        return tokens.setdefault(value, f"{prefix}{len(tokens)}")

    for span in answer["spans"]:
        span["segment_id"] = token(span["segment_id"], "seg-")
        span["representation_id"] = token(span["representation_id"], "rep-")
    for block in answer.get("blocks") or []:
        block["region_segment_id"] = token(block["region_segment_id"], "seg-")
        for span in block["spans"]:
            span["segment_id"] = token(span["segment_id"], "seg-")
            span["representation_id"] = token(span["representation_id"], "rep-")
    answer["pass_id"] = "pass" if answer.get("pass_id") else None
    for omitted in answer.get("omitted") or []:
        omitted["segment_id"] = token(omitted.get("segment_id"), "seg-")
    return answer


@pytest.mark.parametrize("path, fixture", [
    (CHINESE, "calfa_chinese-vertical_chi1087-0065.page-text.json"),
    (SYRIAC, "syriac_onb-syr1-0001.page-text.json"),
])
def test_the_page_text_s_directions_are_recorded_for_the_app_s_labels(db, client, path, fixture):
    """#5199: the app's on-image labels lay a line out in its RESOLVED direction, from the page text's
    blocks (`GET /api/segments/document/{id}/text`), never guessed from the characters. Recorded here, from
    the real imported pages, so the app's test reads the engine's exact answer: the Chinese page's lines
    are columns (ttb), the Syriac page's lines rtl with its Latin folio number ltr. Regenerated with
    FICHERO_UPDATE_FIXTURES=1; failing on drift otherwise."""
    doc_id = _import(db, path)
    answer = client.get(f"/api/segments/document/{doc_id}/text")
    assert answer.status_code == 200, answer.text
    recorded = _stable_text(answer.json())
    directions = {block["direction"] for block in recorded["blocks"] or []}
    assert directions == ({"ttb"} if path == CHINESE else {"rtl", "ltr"}), directions
    target = APP_FIXTURES / fixture
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        target.write_text(json.dumps(recorded, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(target.read_text()) == recorded, "the app's page-text fixture drifted"
