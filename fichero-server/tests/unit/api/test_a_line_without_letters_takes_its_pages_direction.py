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
    assert bases["2"].startswith("inherited from the ") and "no letters" in bases["2"]
    assert sum(1 for b in bases.values() if b) == 1                 # only that line


def test_a_latin_folio_number_keeps_its_own_direction(db, client):
    """`1v` has a letter: it is ltr by its own text, and stays so."""
    assert "1v" in [t.strip() for t in _lines(SYRIAC)]
    doc_id = _import(db, SYRIAC)
    assert _directions_by_text(client, doc_id)["1v"] == {"ltr"}


def test_the_block_first_then_the_page():
    """As ruled: the block's direction (most of its characters), else the page's -- not the
    nearest line. `1773` heading a block of three short English notes and nine Persian lines is
    the block's rtl, though the line after it is English."""
    rtl, ltr = "rtl", "ltr"
    got, basis = settle_neutral_directions(
        [ltr, ltr, ltr, rtl, rtl], [True, False, False, False, False],
        ["b", "b", "b", "b", "b"], [4, 13, 6, 40, 40])
    assert (got[0], basis[0]) == (rtl, "block")
    got, basis = settle_neutral_directions(
        [ltr, rtl, rtl], [True, False, False], ["numbers", "text", "text"], [1, 30, 30])
    assert (got[0], basis[0]) == (rtl, "page")                  # alone in its zone: the page's
    got, basis = settle_neutral_directions([ltr, ltr], [True, True], ["b", "b"], [1, 1])
    assert (got, basis) == ([ltr, ltr], [None, None])           # nothing to inherit


AJAMI = CORPUS / "ajami_fulfulde_elit-wan-00130-001r.alto.xml"


def _alto_lines(path: Path) -> list[str]:
    root = etree.parse(str(path)).getroot()
    local = lambda el: etree.QName(el).localname if isinstance(el.tag, str) else ""
    return [" ".join(s.get("CONTENT") for s in line.iter() if local(s) == "String" and s.get("CONTENT"))
            for line in root.iter() if local(line) == "TextLine"]


def test_a_latin_digit_folio_on_an_arabic_script_page_reads_right_to_left(db, client):
    """Fulfulde in Ajami (Arabic script, right to left; CC-BY-4.0) with its folio number in Latin
    digits: the `1` has no direction of its own, and takes its page's -- not a left-to-right
    island on a right-to-left page."""
    lines = [t for t in _alto_lines(AJAMI) if t.strip()]
    assert "1" in lines and sum(1 for t in lines if _strong(t) & {"R", "AL"}) > 10     # the premise, from the file
    doc_id = _import(db, AJAMI)
    assert _directions_by_text(client, doc_id)["1"] == {"rtl"}
    page = _view(client, doc_id)[0]["pages"][0]
    basis = next(l.get("direction_basis") for l in page["lines"] if page["content"][l["char_start"]:l["char_end"]] == "1")
    assert basis and "no letters" in basis


def test_a_direction_stated_on_the_source_reaches_a_line_without_letters(db, client):
    """Nearest STATED direction first -- region, page, then SOURCE (#5172 as ruled): a direction
    set on the file or folder the page belongs to is its lines' by the cascade, stated, not
    inherited from the letters around it. The cascade stopped at the page itself, so a person who
    set a whole manuscript to `ttb` still saw its pages in rows. If this regresses, a direction
    set on a source silently does nothing to its pages."""
    from fichero_server.actions.registry import registry
    from fichero_server.models import DocType, Document
    from tests.unit.api.test_page_text_follows_the_file import BOOT

    doc_id = _import(db, AJAMI)
    source = Document(name="ELIT/WAN/00130", doc_type=DocType.folder)
    db.save(source)
    page_doc = db.get(Document, doc_id)
    page_doc.parent_id = source.id
    db.save(page_doc)
    registry.invoke(db, "source_setting.set",
                    {"level": "node", "key": "direction", "value": "ttb", "target_id": source.id}, BOOT)
    page = _view(client, doc_id)[0]["pages"][0]
    line = next(l for l in page["lines"] if page["content"][l["char_start"]:l["char_end"]] == "1")
    assert line["direction"] == "ttb" and not line.get("direction_basis")         # the source said so
    # The derivation (export, blocks) and the resolve route read the same cascade, not a copy.
    assert {b.direction for b in document_text(db, doc_id).blocks if b.text.strip()} == {"ttb"}
    resolved = client.get("/api/source-settings/resolve", params={"segment_id": line["segment_id"]})
    [direction] = [s for s in resolved.json()["settings"] if s["key"] == "direction"]
    assert (direction["value"], direction["level"], direction["basis"]) == ("ttb", "document", "recorded on this source")


LATIN = CORPUS / "escriptorium_latin-mufi_clm13027-38r.alto.xml"


def test_a_direction_stated_on_the_project_reaches_a_line_without_letters_everywhere(db, client):
    """The LAST stated rung is the project's, and every reader of the cascade takes it -- region,
    page, source, project, from ONE function (`direction_rungs`). The resolve route had the project
    rung and the derivation and the Reader did not, so a project stated `rtl` showed its folio
    number as `ltr` in the Reader while the Inspector said `rtl`. If this regresses, the Reader and
    the resolve route disagree about the same line again.

    A real Latin page (clm 13027, f. 38r, eScriptorium ALTO) whose folio line is `38`: with nothing
    stated its digits would take the page's `ltr` from its Latin letters -- so `rtl` here can only
    have come from the project."""
    from fichero_server.actions.registry import registry
    from tests.unit.api.test_page_text_follows_the_file import BOOT

    lines = [t for t in _alto_lines(LATIN) if t.strip()]
    assert "38" in lines and sum(1 for t in lines if _strong(t) == {"L"}) > 100    # the premise, from the file
    doc_id = _import(db, LATIN)
    registry.invoke(db, "source_setting.set", {"level": "project", "key": "direction", "value": "rtl"}, BOOT)
    page = _view(client, doc_id)[0]["pages"][0]
    line = next(l for l in page["lines"] if page["content"][l["char_start"]:l["char_end"]] == "38")
    assert line["direction"] == "rtl" and not line.get("direction_basis")         # the Reader: stated, not inherited
    derived = document_text(db, doc_id, include_furniture=True)                    # a folio number is furniture
    [block] = [b for b in derived.blocks if any(derived.text[s.start:s.end] == "38" for s in b.spans)]
    assert (block.direction, block.direction_level) == ("rtl", "project")          # the derivation
    resolved = client.get("/api/source-settings/resolve", params={"segment_id": line["segment_id"]})
    [direction] = [s for s in resolved.json()["settings"] if s["key"] == "direction"]
    assert (direction["value"], direction["level"]) == ("rtl", "project")          # the resolve route
