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
    """A highlight is painted by offsets into the page body's text. With the map a sidecar, the
    body is still ONE run of the page text, so a claim from the middle of line 1 to the middle of
    line 2 covers both parts -- where a per-line element would have split it at the boundary."""
    doc_id = _import(db, CLM)
    payload, html = _view(client, doc_id)
    page = payload["pages"][0]
    first, second = page["lines"][0], page["lines"][1]
    claim = ((first["char_start"] + first["char_end"]) // 2, (second["char_start"] + second["char_end"]) // 2)
    page_js = {"id": page["id"], "number": 1, "content": page["content"], "hasContent": True}
    rendered = _node(_page_script(html) + f"""
const page = {json.dumps(page_js)};
const withMap = transcriptPageMarkup({{...page, lines: {json.dumps(page["lines"])}}});
const without = transcriptPageMarkup({{...page, lines: []}});
console.log(JSON.stringify({{withMap, without}}));
""")
    assert rendered["withMap"] == rendered["without"]
    body = re.search(r'<div class="transcript-page-body">(.*?)</div>', rendered["withMap"], re.S).group(1)
    assert "<" not in body                                          # no element inside the body
    text = body.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    assert text == page["content"]
    painted = text[claim[0]:claim[1]]
    assert page["content"][first["char_start"]:first["char_end"]][-1] in painted
    assert page["content"][second["char_start"]:second["char_end"]][0] in painted
    assert claim[0] < first["char_end"] <= second["char_start"] < claim[1]   # it really crosses the line


def test_a_stale_page_text_gets_no_map_rather_than_a_wrong_one(db, client):
    doc_id = _import(db, CLM)
    doc = db.get(Document, doc_id)
    doc.page_content = "Something else entirely.\n" + (doc.page_content or "")
    db.save(doc)
    payload, _ = _view(client, doc_id)
    assert payload["pages"][0]["lines"] == []
