"""How a word was cut reaches the formats, or the loss report says it could not.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.export-carries-every-edit` (the cut's
source and confidence go to PAGE `custom`, `cut {source:ctc; confidence:0.82;}`; ALTO takes the confidence as the
String's `WC` and reports the source lost). Through the harness's own write, which validates every file.
"""

from __future__ import annotations

from lxml import etree

from fichero_server.formats import write_page
from fichero_server.formats.harness import PageSegment, SourcePage
from fichero_server.page_export import CUT_FACTS


def _page(cut):
    word = PageSegment(kind="word", ref="w1", parent_ref="l1", rect=[0.1, 0.1, 0.2, 0.05], readings=[("transcription", "en")])
    if cut is not None:
        word.foreign[CUT_FACTS] = cut
    return SourcePage(
        producer="Fichero", image_name="folio.jpg", image_size=(1000, 2000),
        segments=[
            PageSegment(kind="region", ref="r1", polygon=[[0.05, 0.05], [0.95, 0.05], [0.95, 0.3], [0.05, 0.3]]),
            PageSegment(kind="line", ref="l1", parent_ref="r1", polygon=[[0.1, 0.1], [0.9, 0.1], [0.9, 0.15], [0.1, 0.15]],
                        baseline=[[0.1, 0.14], [0.9, 0.14]], readings=[("transcription", "en el")]),
            word,
        ],
    )


def _elements(data: bytes, name: str):
    return [element for element in etree.fromstring(data).iter() if etree.QName(element).localname == name]


def test_page_xml_keeps_the_cuts_source_and_confidence_in_custom():
    data, _report = write_page("pagexml", _page({"source": "ctc", "confidence": 0.823}))

    (word,) = _elements(data, "Word")
    assert "cut {source:ctc; confidence:0.82;}" in word.get("custom")


def test_alto_writes_the_confidence_as_wc_and_reports_the_source_lost():
    data, report = write_page("alto", _page({"source": "ink-gap", "confidence": 0.3}))

    (string,) = _elements(data, "String")
    assert string.get("WC") == "0.30"
    assert any(loss.what == "how a word was cut" for loss in report.losses)


def test_a_word_nobody_cut_is_written_as_before():
    page_data, _ = write_page("pagexml", _page(None))
    alto_data, alto_report = write_page("alto", _page(None))

    (word,) = _elements(page_data, "Word")
    assert "cut {" not in (word.get("custom") or "")
    (string,) = _elements(alto_data, "String")
    assert string.get("WC") is None
    assert not any(loss.what == "how a word was cut" for loss in alto_report.losses)
