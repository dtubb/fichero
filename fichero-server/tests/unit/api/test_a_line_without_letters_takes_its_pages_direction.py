"""A line with no direction of its own -- a folio number, a year -- takes its page's (#5172).

WHY: digits are bidi-WEAK: they have no direction. The cascade, with nothing stated and no
script recorded, could only ASSUME `ltr` for them, so `2` on a Syriac folio (and `1773` on a
Persian one, `2` and `1` on an Aljamiado one) came out `ltr`: its own block, reported as an
English line on a right-to-left page. It renders the same either way, which is why nobody would
see it -- but anything reading `blocks` or the Reader's map (an export's per-block direction, a
count of a page's languages) was told the wrong thing. If this regresses, the folio number is an
ltr block again; if the rule widens, a Latin folio number (`1v`, which HAS a letter) stops being
ltr.

The pages are the real Vienna Syriac folios (CC-BY-SA); what each line says is read with lxml.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.api.routes.document.segment_readings import document_text, settle_neutral_directions
from tests.unit.api.test_reader_directions import CORPUS, SYRIAC, _import
from tests.unit.api.test_reader_line_map import _view

FOLIO_2 = CORPUS / "escriptorium_syriac_onb-syr1-0002.page.xml"


def _lines(path: Path) -> list[str]:
    root = etree.parse(str(path)).getroot()
    out = []
    for line in root.iter("{*}TextLine"):
        own = line.find("{*}TextEquiv/{*}Unicode")
        out.append("".join(own.itertext()) if own is not None else "")
    return out


def _strong(text: str) -> set[str]:
    return {unicodedata.bidirectional(ch) for ch in text} & {"L", "R", "AL"}


def _directions_by_text(client, doc_id: str) -> dict[str, set[str]]:
    page = _view(client, doc_id)[0]["pages"][0]
    out: dict[str, set[str]] = {}
    for line in page["lines"]:
        out.setdefault(page["content"][line["char_start"]:line["char_end"]], set()).add(line["direction"])
    return out


def test_the_folio_number_is_digits_on_a_syriac_page():
    """The premise, from the file."""
    lines = [t for t in _lines(FOLIO_2) if t.strip()]
    assert "2" in lines
    assert sum(1 for t in lines if _strong(t) & {"R", "AL"}) > 10


def test_a_digit_only_line_takes_its_pages_direction(db, client):
    doc_id = _import(db, FOLIO_2)
    blocks = document_text(db, doc_id).blocks
    assert {b.direction for b in blocks if b.text.strip()} == {"rtl"}, [(b.direction, b.text[:10]) for b in blocks]
    assert _directions_by_text(client, doc_id)["2"] == {"rtl"}     # and the Reader says the same
    page = _view(client, doc_id)[0]["pages"][0]
    bases = {page["content"][l["char_start"]:l["char_end"]]: l.get("direction_basis") for l in page["lines"]}
    assert "no letters" in bases["2"]                               # and says it was inherited
    assert sum(1 for b in bases.values() if b) == 1                 # only that line


def test_a_latin_folio_number_keeps_its_own_direction(db, client):
    """`1v` has a letter: it is ltr by its own text, and stays so."""
    assert "1v" in [t.strip() for t in _lines(SYRIAC)]
    doc_id = _import(db, SYRIAC)
    assert _directions_by_text(client, doc_id)["1v"] == {"ltr"}


def test_neutrals_between_and_alone():
    assert settle_neutral_directions(["rtl", "ltr", "rtl"], [False, True, False]) == ["rtl", "rtl", "rtl"]
    assert settle_neutral_directions(["ltr", "rtl"], [True, False]) == ["rtl", "rtl"]      # first: the next
    assert settle_neutral_directions(["ltr", "ltr"], [True, True]) == ["ltr", "ltr"]      # nothing to take
