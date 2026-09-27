"""The page's text follows the FILE's order and the script's direction, through the LIBRARY (#5137).

Found by the acceptance run (`acceptance-2026-09-27.md`, defects 7-9), not by the format harness:
the harness never puts a library in the middle. Here each real file goes in through
`format.import`, the text comes back through `document_text` (what `GET
/api/segments/document/{id}/text` serves) and the export through `page_from_library`, and the
expected side is read from the file with plain lxml, never with our readers.

What breaks without these: a two-column page read across both columns line by line (Clm 13027
38r came back 0, 61, 1, 2, 62 ...); vertical Chinese in a scrambled column order; and Syriac,
a right-to-left script, labelled `ltr` because the file said nothing about direction.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.models import DocType, Document, FileType, Segment, Status
from fichero_server.page_export import page_from_library

CORPUS = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus"
CLM = CORPUS / "escriptorium_latin-mufi_clm13027-38r.alto.xml"
CHINESE = CORPUS / "calfa_chinese-vertical_chi1087-0065.page.xml"
SYRIAC = CORPUS / "escriptorium_syriac_onb-syr1-0001.page.xml"
BOOT = ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _import(db, path: Path) -> str:
    doc = Document(name=path.stem, doc_type=DocType.file, file_type=FileType.image,
                   path=f"/p/{path.stem}.jpg", status=Status.completed)
    db.save(doc)
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(path)}, BOOT)
    return doc.id


def _local(el) -> str:
    return etree.QName(el).localname


def _alto_words_in_file_order(path: Path) -> list[str]:
    """ALTO: blocks in file order (the reader's `as-written`), each block's words as written."""
    root = etree.parse(str(path)).getroot()
    return [el.get("CONTENT") for el in root.iter() if isinstance(el.tag, str)
            and _local(el) == "String" and el.get("CONTENT")]


def _page_lines_in_file_order(path: Path) -> list[str]:
    """PAGE: regions in the `ReadingOrder` (then any it omits, in file order), each region's
    lines in the order the file wrote them; a line's text is its own `TextEquiv/Unicode`."""
    root = etree.parse(str(path)).getroot()
    regions = {el.get("id"): el for el in root.iter() if isinstance(el.tag, str) and _local(el) == "TextRegion"}
    ordered = [el.get("regionRef") for el in root.iter() if isinstance(el.tag, str)
               and _local(el) == "RegionRefIndexed"]
    ordered = sorted(ordered, key=lambda ref: next(
        int(el.get("index")) for el in root.iter() if isinstance(el.tag, str)
        and _local(el) == "RegionRefIndexed" and el.get("regionRef") == ref))
    sequence = [regions[r] for r in ordered if r in regions] + [el for r, el in regions.items() if r not in ordered]
    lines = []
    for region in sequence:
        for line in (c for c in region if isinstance(c.tag, str) and _local(c) == "TextLine"):
            equiv = next((c for c in line if isinstance(c.tag, str) and _local(c) == "TextEquiv"), None)
            uni = next((c for c in equiv if isinstance(c.tag, str) and _local(c) == "Unicode"), None) if equiv is not None else None
            if uni is not None and (uni.text or "").strip():
                lines.append(uni.text)
    return lines


def _span_texts(db, derived, kind: str) -> list[str]:
    rows = {r.id: r for r in db.query_in(Segment, "id", [s.segment_id for s in derived.spans])}
    return [derived.text[s.start:s.end] for s in derived.spans if rows[s.segment_id].kind == kind]


def test_a_two_column_page_reads_down_each_column_not_across_both(db):
    doc_id = _import(db, CLM)
    derived = document_text(db, doc_id)
    assert _span_texts(db, derived, "word") == _alto_words_in_file_order(CLM)


def test_vertical_chinese_reads_in_the_files_column_order(db):
    doc_id = _import(db, CHINESE)
    derived = document_text(db, doc_id)
    assert _span_texts(db, derived, "line") == _page_lines_in_file_order(CHINESE)


def test_a_syriac_page_that_states_no_direction_is_right_to_left(db):
    doc_id = _import(db, SYRIAC)
    derived = document_text(db, doc_id)
    syriac = [b for b in derived.blocks if any("\u0700" <= ch <= "\u074f" for ch in b.text)]
    assert syriac, "no Syriac text came back"
    assert {b.direction for b in syriac} == {"rtl"}
    # The folio number "1v" is Latin letters: left-to-right, by the same rule.
    assert {b.direction for b in derived.blocks if b.text.strip() == "1v"} <= {"ltr"}


def test_the_syriac_lines_follow_the_files_reading_order(db):
    doc_id = _import(db, SYRIAC)
    derived = document_text(db, doc_id)
    assert _span_texts(db, derived, "line") == _page_lines_in_file_order(SYRIAC)


@pytest.mark.parametrize("path, kind, truth", [
    (CLM, "word", _alto_words_in_file_order),
    (CHINESE, "line", _page_lines_in_file_order),
])
def test_the_export_writes_the_page_in_the_same_order(db, path, kind, truth):
    """The export read the library's rows in whatever order the database returned them."""
    doc_id = _import(db, path)
    page, _choices = page_from_library(db, doc_id)
    written = [seg.readings[0][1] for seg in page.segments if seg.kind == kind and seg.readings]
    assert written == truth(path)
