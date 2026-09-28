"""The Reader knows which LINE its caret is on (Q5, 3c part c), so ⌥⌘↑/↓ in the text can move
that line in the reading order.

The server sends a sidecar map per page -- {segment_id, char_start, char_end} in the page text's
offsets -- and the page resolves the caret's offset against it. Nothing wraps a line in an element:
the claim highlighter walks the page body's text nodes by offset, and a per-line element would split
a highlight that crosses a line. So these pin both halves: the map is right, and the page body is
still the page text and nothing else.

The page script runs in node (the functions are cut from the SERVED page, not a copy), because a
source scan would pass with the resolver broken.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.models import Document, Segment
from tests.unit.api.test_page_text_follows_the_file import CLM, _import

NODE = shutil.which("node")


def _view(client, doc_id: str) -> tuple[dict, str]:
    response = client.get(f"/view/document/{doc_id}")
    assert response.status_code == 200, response.text
    payload = json.loads(re.search(r"const documentData = (\{.*?\});\n", response.text, re.S).group(1))
    return payload, response.text


def _page_script(html: str) -> str:
    start = html.index("function escapeHtml(text)")
    markup = html.index("function transcriptPageMarkup(page)")
    end = html.index("\n}\n", markup) + 3
    return "globalThis.window = {};\n" + html[start:end]


def _node(script: str) -> object:
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_map_names_each_line_and_covers_its_text(db, client):
    doc_id = _import(db, CLM)
    payload, _ = _view(client, doc_id)
    page = payload["pages"][0]
    lines = page["lines"]
    assert len(lines) > 3
    assert page["content"] == document_text(db, doc_id).text    # the text itself is untouched
    kinds = {s.id: s.kind for s in db.all(Segment) if s.document_id == doc_id}
    assert {kinds[line["segment_id"]] for line in lines} == {"line"}
    assert len({line["segment_id"] for line in lines}) == len(lines)   # one run per line
    ends = [0] + [line["char_end"] for line in lines]
    for line, previous_end in zip(lines, ends):
        assert previous_end <= line["char_start"] < line["char_end"] <= len(page["content"])
        assert "\n" not in page["content"][line["char_start"]:line["char_end"]].strip("\n")


@pytest.mark.skipif(NODE is None, reason="needs node to run the page's own script")
def test_the_caret_on_line_n_resolves_to_line_n(db, client):
    doc_id = _import(db, CLM)
    payload, html = _view(client, doc_id)
    lines = payload["pages"][0]["lines"]
    probes = [(line["segment_id"], offset) for line in lines
              for offset in (line["char_start"], (line["char_start"] + line["char_end"]) // 2, line["char_end"])]
    got = _node(_page_script(html) + f"""
const lines = {json.dumps(lines)};
console.log(JSON.stringify({json.dumps([o for _, o in probes])}.map((o) => segmentAtOffset(lines, o))));
""")
    assert got == [segment_id for segment_id, _ in probes]


@pytest.mark.skipif(NODE is None, reason="needs node to run the page's own script")
def test_a_claim_across_two_lines_still_has_one_text_to_paint(db, client):
    """A highlight is painted by offsets into the page body's text. Each manuscript line now ends at a
    `.line-break` element (#5208), so the body is several text nodes -- and a claim from the middle of
    line 1 to the middle of line 2 must still be found and lit whole: its excerpt is looked for in the
    nodes' text JOINED (`excerptPieces`), one piece per node. WHY: the highlighters looked in one node
    at a time, and a claim crossing a line would silently stop being highlighted."""
    doc_id = _import(db, CLM)
    payload, html = _view(client, doc_id)
    page = payload["pages"][0]
    first, second = page["lines"][0], page["lines"][1]
    claim = ((first["char_start"] + first["char_end"]) // 2, (second["char_start"] + second["char_end"]) // 2)
    assert claim[0] < first["char_end"] <= second["char_start"] < claim[1]   # it really crosses the line
    excerpt = page["content"][claim[0]:claim[1]]
    page_js = {"id": page["id"], "number": 1, "content": page["content"], "hasContent": True}
    rendered = _node(_page_script(html) + f"""
const page = {json.dumps(page_js)};
const withMap = transcriptPageMarkup({{...page, lines: {json.dumps(page["lines"])}}});
const body = withMap.match(/<div class="transcript-page-body">([\\s\\S]*?)<\\/div>/)[1];
const texts = body.split(/<[^>]+>/).map((t) => t.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&"));
const pieces = excerptPieces(texts, {json.dumps(excerpt)});
console.log(JSON.stringify({{ texts, pieces }}));
""")
    texts, pieces = rendered["texts"], rendered["pieces"]
    assert "".join(texts) == page["content"], "tags stripped, the body is the page text to the character"
    assert len(pieces) >= 2, "the claim crosses the line break, so it touches more than one node"
    assert "".join(texts[p["index"]][p["start"]:p["end"]] for p in pieces) == excerpt, "and is lit whole"


def test_a_stale_page_text_gets_no_map_rather_than_a_wrong_one(db, client):
    doc_id = _import(db, CLM)
    doc = db.get(Document, doc_id)
    doc.page_content = "Something else entirely.\n" + (doc.page_content or "")
    db.save(doc)
    payload, _ = _view(client, doc_id)
    assert payload["pages"][0]["lines"] == []


@pytest.mark.skipif(NODE is None, reason="needs node to run the page's own script")
def test_the_move_keys_name_the_caret_line_and_a_step_the_app_knows(db, client):
    """⌥⌘↑ / ⌥⌘↓ / ⌥⌘⇞ / ⌥⌘⇟ post `lineMove` with the caret's line (3c part d). The step names
    are the ones `ReaderLineMove.step(named:)` parses -- a name the app does not know moves nothing,
    silently -- and any other chord, or a caret off every line, posts nothing."""
    doc_id = _import(db, CLM)
    _, html = _view(client, doc_id)
    at = {"pageId": "p1", "segmentId": "line-7"}
    got = _node(_page_script(html) + f"""
const at = {json.dumps(at)};
const chord = (key, extra = {{}}) => ({{ key, altKey: true, metaKey: true, shiftKey: false, ctrlKey: false, ...extra }});
console.log(JSON.stringify({{
    moves: ["ArrowUp", "ArrowDown", "PageUp", "PageDown"].map((key) => lineMoveMessage(chord(key), at)),
    noMeta: lineMoveMessage(chord("ArrowUp", {{ metaKey: false }}), at),
    withShift: lineMoveMessage(chord("ArrowUp", {{ shiftKey: true }}), at),
    otherKey: lineMoveMessage(chord("ArrowLeft"), at),
    offLine: lineMoveMessage(chord("ArrowUp"), null),
}}));
""")
    assert got["moves"] == [{"segmentId": "line-7", "pageId": "p1", "step": step}
                            for step in ("up", "down", "toStart", "toEnd")]
    assert got["noMeta"] is None and got["withShift"] is None
    assert got["otherKey"] is None and got["offLine"] is None


def _counting_derivations(monkeypatch) -> list[str]:
    """Every `document_text` call from here on, by page id. Both the cache refresh and the render
    import it at call time, so patching the module attribute counts both."""
    from fichero_server.api.routes.document import segment_readings

    calls: list[str] = []
    real = segment_readings.document_text

    def counting(db, document_id, *args, **kwargs):
        calls.append(document_id)
        return real(db, document_id, *args, **kwargs)

    monkeypatch.setattr(segment_readings, "document_text", counting)
    return calls


def test_a_render_of_a_freshly_cached_page_derives_nothing(db, client, monkeypatch):
    """The map is stored with `page_content` by the same refresh, from the same derivation. A render
    that derived again doubled the Reader's open time on a dense page (0.5-1 s a derivation)."""
    doc_id = _import(db, CLM)
    calls = _counting_derivations(monkeypatch)
    payload, _ = _view(client, doc_id)
    assert payload["pages"][0]["lines"]
    assert calls == []


def test_a_move_derives_exactly_once_and_the_render_reads_its_map(db, client, monkeypatch):
    from tests.unit.api.test_text_follows_the_order import _move_last_line_of_a_block_to_its_start

    doc_id = _import(db, CLM)
    calls = _counting_derivations(monkeypatch)
    _audit, moved, first = _move_last_line_of_a_block_to_its_start(db, client, doc_id)
    payload, _ = _view(client, doc_id)
    assert calls == [doc_id]                                  # the refresh, and nothing at render
    order = [line["segment_id"] for line in payload["pages"][0]["lines"]]
    assert order.index(moved) < order.index(first)            # the map is the moved text's map
