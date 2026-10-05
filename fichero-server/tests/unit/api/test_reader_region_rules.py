"""The Reader marks each region's block of lines with a rule in the region's hue down its leading edge
(`source.editor.hierarchy.reader-shows-regions`, hierarchy A ruled 2026-10-05, #5426; the page's half).

WHY: the Reader showed a page's text as one run, so nothing in it said which lines belong to which region,
while the Preview colours every region its own hue. The app sends each region's line ids and its palette
NAME (`window.fichero.showRegions`); the page finds the block's span in its line map and lays a rule beside
the text, in the system colour of that name -- never RGB, so it follows Light, Dark and Increase Contrast,
and never an element inside the text, so the caret, the line map and the claim highlighter see the body as
it is. If this regresses, a block is ruled over the wrong lines, a right-to-left page is ruled on the wrong
edge, or a colour stops adapting.

The functions are cut from the SERVED page and run in node, over a real imported page's map.
"""

from __future__ import annotations

import json
import shutil

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from tests.unit.api.test_reader_directions import ARABIC, _import, _page_functions
from tests.unit.api.test_reader_line_map import _node, _view

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node to run the page's own script")


def _rule_functions(html: str) -> str:
    start = html.index("let regionBlocks = [];")
    end = html.index("function applyRegionRules()")
    return html[start:end]


def test_a_block_spans_its_regions_lines_on_their_page(db, client):
    doc_id = _import(db, ARABIC)
    payload, html = _view(client, doc_id)
    page = payload["pages"][0]
    lines = page["lines"]
    assert len(lines) >= 5
    blocks = [
        {"segmentIds": [lines[0]["segment_id"], lines[1]["segment_id"], lines[2]["segment_id"]], "hue": "blue"},
        {"segmentIds": [lines[4]["segment_id"], "a-line-on-another-page"], "hue": "orange"},
        {"segmentIds": ["nowhere"], "hue": "green"},
    ]
    got = _node(_page_functions(html) + _rule_functions(html) + f"""
const maps = new Map([[{json.dumps(page["id"])}, {json.dumps(lines)}]]);
console.log(JSON.stringify(regionRuleSpans(maps, {json.dumps(blocks)})));
""")
    assert got == [
        {"pageId": page["id"], "start": lines[0]["char_start"], "end": lines[2]["char_end"], "hue": "blue"},
        {"pageId": page["id"], "start": lines[4]["char_start"], "end": lines[4]["char_end"], "hue": "orange"},
    ], "each block from its first line's start to its last line's end; a block with no line here draws nothing"


def test_the_rule_sits_on_the_leading_edge_in_the_named_system_colour(db, client):
    doc_id = _import(db, ARABIC)
    _, html = _view(client, doc_id)
    got = _node("globalThis.window = { CSS: { supports: (p, v) => v !== '-apple-system-nosuch' } };\n"
                "globalThis.CSS = window.CSS;\n" + _rule_functions(html) + """
console.log(JSON.stringify([
    regionRuleSide("ltr"), regionRuleSide("rtl"), regionRuleSide("ttb"),
    regionRuleColour("blue"), regionRuleColour("nosuch"), regionRuleColour("x; background: url(evil)"),
]));
""")
    assert got[:3] == ["left", "right", "top"], "left to right: the left; right to left: the right"
    assert got[3] == "-apple-system-blue", "the system colour of the palette name, never RGB"
    assert got[4] == "-apple-system-control-accent", "a name WebKit does not know falls back to the accent"
    assert ";" not in got[5] and "(" not in got[5], "a name is letters only: nothing else reaches the style"


def test_the_rules_are_laid_beside_the_text_never_inside_it(db, client):
    doc_id = _import(db, ARABIC)
    _, html = _view(client, doc_id)
    assert "showRegions(blocks)" in html
    assert ".region-rule {" in html and "pointer-events: none" in html
    assert "article.appendChild(rule)" in html, "the rule is the page's, beside the body, not in the text"
    assert "applyRegionRules();\n    applyStaleHighlight();" in html, "a patched page is ruled again"
