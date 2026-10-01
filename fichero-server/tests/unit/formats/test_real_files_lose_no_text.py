"""Every vendored real file reads with all of its text: nothing dropped on the way in.

WHY: on 2026-10-01 the TEI reader was found dropping seven verse lines of the TEI Consortium's own
Hamlet sample (`<l>text <lb/></l>`, the break after the text): no test noticed, because every test
asked for the lines it knew about and none asked whether ALL the text arrived. This one counts the
letters a reader produces against the letters the file itself holds, for every real file vendored,
so a reader that silently loses text fails here whatever the encoding that triggers it.

PAGE and ALTO are exact: every `TextLine`'s `TextEquiv/Unicode`, every `String@CONTENT`. TEI is
counted over the `<text>` body with the parts the model keeps elsewhere left out (the header,
notes, a `<choice>`'s other sides, apparatus readings, labels), so it is held to 97%, not 100%.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from _scan_files import scan_rglob
from lxml import etree

from fichero_server.formats import alto, pagexml, tei

FIXTURES = Path(__file__).parent / "fixtures"
_PARSER = etree.XMLParser(recover=True, huge_tree=True)
_TEI_ELSEWHERE = {"teiHeader", "note", "facsimile", "rdg", "orig", "sic", "abbr", "fw", "figDesc", "desc", "label"}


def _letters(text: str) -> int:
    return sum(ch.isalpha() for ch in text)


def _root(path: Path):
    return etree.fromstring(path.read_bytes(), _PARSER)


def _files(suffix: str, root_name: str) -> list[Path]:
    return [p for p in sorted(scan_rglob(FIXTURES, f"*{suffix}")) if etree.QName(_root(p)).localname == root_name]


def _read(module, data: bytes):
    return module.read_pages(data) if hasattr(module, "read_pages") else [module.read(data)]


@pytest.mark.parametrize("path", _files(".xml", "PcGts"), ids=lambda p: p.name)
def test_a_page_xml_file_reads_every_letter_of_its_lines(path):
    root = _root(path)
    want = 0
    for line in root.iter("{*}TextLine"):
        equiv = next((c for c in line if etree.QName(c).localname == "TextEquiv"), None)
        unicode = equiv.find("{*}Unicode") if equiv is not None else None
        want += _letters("".join(unicode.itertext())) if unicode is not None else 0
    got = sum(_letters(t) for p in _read(pagexml, path.read_bytes()) for s in p.segments
              if s.kind == "line" for _k, t in s.readings[:1])
    assert got == want


@pytest.mark.parametrize("path", _files(".alto.xml", "alto"), ids=lambda p: p.name)
def test_an_alto_file_reads_every_letter_of_its_strings(path):
    want = sum(_letters(s.get("CONTENT") or "") for s in _root(path).iter("{*}String"))
    got = sum(_letters(t) for p in _read(alto, path.read_bytes()) for s in p.segments
              if s.kind == "word" for _k, t in s.readings[:1])
    assert got == want


def _tei_body_letters(path: Path) -> int:
    text = _root(path).find("{http://www.tei-c.org/ns/1.0}text")
    count = 0

    def walk(element):
        nonlocal count
        tag = etree.QName(element).localname if isinstance(element.tag, str) else None
        if tag is None or tag in _TEI_ELSEWHERE:
            return
        if tag == "choice":
            sides = [c for c in element if isinstance(c.tag, str)]
            if sides:
                walk(sides[0])          # the reader takes one side; the other is kept apart
            return
        count += _letters(element.text or "")
        for child in element:
            walk(child)
            count += _letters(child.tail or "")

    if text is not None:
        walk(text)
    return count


@pytest.mark.parametrize("path", _files(".xml", "TEI"), ids=lambda p: p.name)
def test_a_tei_file_reads_its_text(path):
    want = _tei_body_letters(path)
    got = sum(_letters(t) for p in _read(tei, path.read_bytes()) for s in p.segments
              if s.kind != "word" for _k, t in s.readings[:1])
    assert got >= 0.97 * want, f"{got} of {want} letters read"
