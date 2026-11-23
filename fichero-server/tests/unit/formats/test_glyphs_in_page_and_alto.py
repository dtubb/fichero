"""Character segments reach ALTO and PAGE XML as Glyphs.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.export-carries-every-edit` (word and
character segments go to ALTO `String` and `Glyph`, with `WC` / `GC` from the cut's confidence, and PAGE `Word` /
`Glyph`). Through the harness's own write, which validates every file.
"""

from __future__ import annotations

from lxml import etree

from fichero_server.formats import read_page, write_page
from fichero_server.formats.harness import PageSegment, SourcePage
from fichero_server.page_export import CUT_FACTS


def _character(ref, x, text, confidence=0.9):
    character = PageSegment(kind="character", ref=ref, parent_ref="w1", rect=[x, 0.1, 0.1, 0.05],
                            readings=[("transcription", text)] if text is not None else [])
    character.foreign[CUT_FACTS] = {"source": "ctc", "confidence": confidence}
    return character


def _page(*characters):
    return SourcePage(
        producer="Fichero", image_name="folio.jpg", image_size=(1000, 2000),
        segments=[
            PageSegment(kind="region", ref="r1", polygon=[[0.05, 0.05], [0.95, 0.05], [0.95, 0.3], [0.05, 0.3]]),
            PageSegment(kind="line", ref="l1", parent_ref="r1", polygon=[[0.1, 0.1], [0.9, 0.1], [0.9, 0.15], [0.1, 0.15]],
                        baseline=[[0.1, 0.14], [0.9, 0.14]], readings=[("transcription", "en el")]),
            PageSegment(kind="word", ref="w1", parent_ref="l1", rect=[0.1, 0.1, 0.2, 0.05],
                        readings=[("transcription", "en")]),
            *characters,
        ],
    )


def _elements(data: bytes, name: str):
    return [element for element in etree.fromstring(data).iter() if etree.QName(element).localname == name]


def test_alto_writes_each_character_as_a_glyph_in_its_word_with_gc():
    data, _report = write_page("alto", _page(_character("c1", 0.1, "e", 0.912), _character("c2", 0.2, "n", 0.4)))

    (string,) = [s for s in _elements(data, "String") if s.get("CONTENT") == "en"]
    glyphs = [child for child in string if etree.QName(child).localname == "Glyph"]
    assert [(g.get("CONTENT"), g.get("GC")) for g in glyphs] == [("e", "0.91"), ("n", "0.40")]
    assert glyphs[0].get("HPOS") == "100" and glyphs[0].get("WIDTH") == "100"


def test_alto_glyphs_come_back_as_the_words_characters():
    data, _report = write_page("alto", _page(_character("c1", 0.1, "e"), _character("c2", 0.2, "n")))

    page = read_page("alto", data)
    characters = [s for s in page.segments if s.kind == "character"]
    assert [(c.parent_ref, c.readings) for c in characters] == [
        ("w1", [("transcription", "e")]), ("w1", [("transcription", "n")]),
    ]


def test_alto_reports_a_character_it_cannot_write_as_one_glyph():
    data, report = write_page("alto", _page(_character("c1", 0.1, None), _character("c2", 0.2, "n")))

    assert [g.get("CONTENT") for g in _elements(data, "Glyph")] == ["n"]
    assert any(loss.what == "characters" for loss in report.losses)


def test_page_xml_writes_each_character_as_a_glyph_in_its_word():
    data, _report = write_page("pagexml", _page(_character("c1", 0.1, "e"), _character("c2", 0.2, "n")))

    (word,) = _elements(data, "Word")
    glyphs = [child for child in word if etree.QName(child).localname == "Glyph"]
    assert len(glyphs) == 2
    assert "cut {source:ctc; confidence:0.90;}" in glyphs[0].get("custom")


def test_alto_puts_a_character_with_no_word_in_invented_parents_that_validate():
    loose = _character("c1", 0.1, "e")
    loose.parent_ref = None
    data, report = write_page("alto", _page(loose))  # write_page validates the file against the ALTO schema

    assert [g.get("CONTENT") for g in _elements(data, "Glyph")] == ["e"]
    assert any(loss.what == "implicit parents" for loss in report.losses)
