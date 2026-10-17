"""A kept Markdown export keeps each line of a page as a line (#5502).

Spec: `source.onboard.kept-exported.markdown-keeps-lines`. Markdown joins consecutive lines into one
paragraph unless each ends with a hard break (two spaces, CommonMark); the operator's export showed
each page as one paragraph.
"""
from __future__ import annotations

from fichero_server.export_service import render_markdown_text


def test_every_line_of_a_page_but_the_last_ends_with_a_hard_break():
    out = render_markdown_text("Book", [("p1", "one\ntwo\nthree"), ("p2", "four")])
    assert out == "# Book\n\n## p1\n\none  \ntwo  \nthree\n\n## p2\n\nfour\n"


def test_a_page_alone_keeps_its_lines_and_an_escaped_line_keeps_its_break():
    out = render_markdown_text("Page", [(None, "- not a list\nnext")])
    assert out == "# Page\n\n\\- not a list  \nnext\n"
