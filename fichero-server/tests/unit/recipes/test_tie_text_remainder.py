"""`wide.nomodel.untied-remainder-kept` (#5721): the page text the tie does not tie to a line is kept and named, never dropped."""
from __future__ import annotations

from fichero_server.checking import tie_text


def test_a_draft_pages_whole_text_is_the_remainder():
    scored = tie_text.tie_lines("completely unrelated words here", ["abc", "xyz"])
    assert tie_text.page_is_draft(scored)
    (rest,) = tie_text.remainder("completely unrelated words here", scored, ["s1", "s2"], draft=True)
    assert rest == {"segment_id": None, "text": "completely unrelated words here", "why": tie_text.DRAFT}


def test_a_stretch_below_the_threshold_is_listed_with_its_line():
    scored = [{"text": "hola mundo", "score": 0.9, "tied": True, "rough_read": "hola mundo"},
              {"text": "algo distinto", "score": 0.1, "tied": False, "rough_read": "zzz"}]
    assert tie_text.remainder("hola mundo algo distinto", scored, ["s1", "s2"], draft=False) == [
        {"segment_id": "s2", "text": "algo distinto", "why": tie_text.DOUBTFUL}]


def test_a_page_where_every_line_tied_has_no_remainder_and_blank_text_none():
    scored = [{"text": "a", "score": 1.0, "tied": True, "rough_read": "a"}]
    assert tie_text.remainder("a", scored, ["s1"], draft=False) == []
    assert tie_text.remainder("  ", scored, ["s1"], draft=True) == []
