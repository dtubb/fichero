"""PDF /Annots import (bbox step 3's missing half, 2026-08-25): highlights
and notes made in Preview/Acrobat become Fichero annotations with normalized
node-frame anchors — the source's own annotation layer survives import."""

from unittest.mock import MagicMock

import fitz
import pytest

from fichero_server.importers.pdf_annotations import (
    extract_pdf_annotations,
    import_pdf_annotations,
)


@pytest.fixture()
def annotated_pdf(tmp_path):
    path = tmp_path / "marked.pdf"
    pdf = fitz.open()
    page = pdf.new_page(width=500, height=1000)
    page.insert_text((50, 100), "una linea de texto para resaltar")
    highlight = page.add_highlight_annot(fitz.Rect(50, 90, 250, 110))
    highlight.set_info(content="key passage", title="Daniel")
    highlight.update()
    note = page.add_text_annot(fitz.Point(400, 500), "check this date")
    note.update()
    pdf.save(path)
    pdf.close()
    return str(path)


def test_extracts_normalized_topleft_fractions(annotated_pdf):
    annots = extract_pdf_annotations(annotated_pdf)
    kinds = sorted(a["kind"] for a in annots)
    assert kinds == ["highlight", "note"]

    highlight = next(a for a in annots if a["kind"] == "highlight")
    x, y, w, h = highlight["rect"]
    # 500x1000 page, rect ~(50,90)-(250,110): x ≈ 0.1, y ≈ 0.09, w ≈ 0.4.
    assert 0.05 < x < 0.15 and 0.05 < y < 0.13
    assert 0.3 < w < 0.5 and 0 < h < 0.1
    assert highlight["text"] == "key passage"
    assert highlight["author"] == "Daniel"
    assert highlight["quads"], "text markup carries its per-line quads"

    note = next(a for a in annots if a["kind"] == "note")
    assert note["text"] == "check this date"


def test_import_lands_on_the_page_child(annotated_pdf):
    db = MagicMock()
    saved = []
    db.save.side_effect = saved.append
    parent = MagicMock(id="parent-1")
    page_child = MagicMock(id="page-1")

    count = import_pdf_annotations(
        db, parent, annotated_pdf, page_children_by_index={0: page_child}
    )

    assert count == 2 == len(saved)
    for annotation in saved:
        assert annotation.document_id == "page-1"
        assert annotation.page_id == "page-1"
        assert annotation.anchor is not None
        assert annotation.anchor.rendition_id is None  # the node's own frame
    authors = {a.created_by for a in saved}
    assert "Daniel" in authors  # the PDF's own provenance survives


def test_unannotated_pdf_is_a_cheap_empty(tmp_path):
    path = tmp_path / "plain.pdf"
    pdf = fitz.open()
    pdf.new_page()
    pdf.save(path)
    pdf.close()
    assert extract_pdf_annotations(str(path)) == []
    assert import_pdf_annotations(MagicMock(), MagicMock(id="p"), str(path)) == 0
