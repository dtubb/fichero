"""The Kraken training set keeps a person's word and character cuts and leaves a machine's out.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.corrections-train` (word and character
cuts made by a person are included as PAGE `Word` / `Glyph`; a machine's cut no person touched is left out;
regions and lines stay). Every page of a set goes through `drop_flagged_lines`; the file is Fichero's own PAGE XML.
"""
from __future__ import annotations

from lxml import etree

from fichero_server.formats import write_page
from fichero_server.formats.harness import PageSegment, SourcePage
from fichero_server.page_export import CUT_FACTS
from fichero_server.training.kraken_set import drop_flagged_lines


def _cut(kind, ref, parent, x, text, source):
    segment = PageSegment(kind=kind, ref=ref, parent_ref=parent, rect=[x, 0.1, 0.1, 0.05],
                          readings=[("transcription", text)])
    if source is not None:
        segment.foreign[CUT_FACTS] = {"source": source, "confidence": 1.0 if source == "person" else 0.8}
    return segment


def _file(*cuts) -> str:
    page = SourcePage(
        producer="Fichero", image_name="folio.jpg", image_size=(1000, 2000),
        segments=[
            PageSegment(kind="region", ref="r1", polygon=[[0.05, 0.05], [0.95, 0.05], [0.95, 0.3], [0.05, 0.3]]),
            PageSegment(kind="line", ref="l1", parent_ref="r1", polygon=[[0.1, 0.1], [0.9, 0.1], [0.9, 0.15], [0.1, 0.15]],
                        baseline=[[0.1, 0.14], [0.9, 0.14]], readings=[("transcription", "en el")]),
            *cuts,
        ],
    )
    data, _report = write_page("pagexml", page)
    return data.decode("utf-8")


def _ids(content: str, name: str) -> list[str]:
    root = etree.fromstring(content.encode("utf-8"))
    return [el.get("id") for el in root.iter() if etree.QName(el).localname == name]


def test_a_persons_words_and_characters_stay_and_a_machines_go():
    content, dropped = drop_flagged_lines(_file(
        _cut("word", "person_word", "l1", 0.1, "en", "person"),
        _cut("character", "person_char", "person_word", 0.1, "e", "person"),
        _cut("character", "machine_char", "person_word", 0.2, "n", "ctc"),
        _cut("word", "machine_word", "l1", 0.5, "el", "ink-gap"),
    ), set())

    assert _ids(content, "Word") == ["person_word"]
    assert _ids(content, "Glyph") == ["person_char"]
    assert _ids(content, "TextLine") == ["l1"] and _ids(content, "TextRegion") == ["r1"]
    assert dropped == [], "only flagged lines are counted as left out"


def test_a_word_no_cut_made_stays():
    content, _dropped = drop_flagged_lines(_file(_cut("word", "drawn", "l1", 0.1, "en", None)), set())

    assert _ids(content, "Word") == ["drawn"]
