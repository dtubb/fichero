"""Regression tests for extract_all input recovery (#1166)."""

from __future__ import annotations

from fichero_server.models import DocType, Document, FileType
from fichero_server.workflows.tools.extract_all import (
    _records_from_selected_documents,
    _recover_text_and_records,
)


def test_recover_text_from_records_when_text_port_empty():
    text, records = _recover_text_and_records(
        {
            "text": "",
            "records": [
                {"doc_id": "page-1", "text": "First page text"},
                {"doc_id": "page-2", "text": "Second page text"},
            ],
        },
        {},
    )

    assert text == "First page text\n\nSecond page text"
    assert [record["doc_id"] for record in records] == ["page-1", "page-2"]


def test_recover_text_from_transcribe_outputs_when_resolver_saw_empty():
    text, records = _recover_text_and_records(
        {"text": None, "records": []},
        {
            "outputs": {
                "transcribe": {
                    "records": [{"doc_id": "page-1", "text": "Recovered OCR"}],
                },
            },
        },
    )

    assert text == "Recovered OCR"
    assert records == [{"index": 0, "doc_id": "page-1", "text": "Recovered OCR"}]


def test_recover_text_from_parallel_page_records_when_outputs_empty():
    text, records = _recover_text_and_records(
        {"text": None, "records": []},
        {
            "parallel_results": {
                "transcribe": [
                    {
                        "index": 0,
                        "success": True,
                        "result": {
                            "page_records": [
                                {"doc_id": "page-1", "text": "Parallel page"}
                            ],
                        },
                    },
                ],
            },
        },
    )

    assert text == "Parallel page"
    assert records == [{"index": 0, "doc_id": "page-1", "text": "Parallel page"}]


def test_recover_text_from_parallel_records_when_outputs_empty():
    """Prefer canonical records from parallel fan-out results (#1469)."""
    text, records = _recover_text_and_records(
        {"text": None, "records": []},
        {
            "parallel_results": {
                "transcribe": [
                    {
                        "index": 0,
                        "success": True,
                        "result": {
                            "records": [
                                {"doc_id": "page-a", "text": "Parallel A"},
                                {"doc_id": "page-b", "text": "Parallel B"},
                            ],
                        },
                    },
                ],
            },
        },
    )

    assert text == "Parallel A\n\nParallel B"
    assert records == [
        {"index": 0, "doc_id": "page-a", "text": "Parallel A"},
        {"index": 1, "doc_id": "page-b", "text": "Parallel B"},
    ]


def test_records_from_selected_documents_uses_pdf_text_layer_for_truncated_pages(
    db, test_package, tmp_path, monkeypatch
):
    source_file = tmp_path / "truncated.pdf"
    source_file.write_bytes(b"%PDF-1.4\n")

    parent = Document(
        id="pdf-parent",
        name="Parent PDF",
        path=str(source_file),
        doc_type=DocType.file,
        file_type=FileType.pdf,
    )
    page = Document(
        id="pdf-page-1",
        parent_id=parent.id,
        name="Parent PDF p. 1",
        doc_type=DocType.page,
        sequence=1,
        page_content="Short OCR stub",
        metadata={
            "page_number": 1,
            "transcription": "Short OCR stub",
            "text_length": 500,
        },
    )
    db.save(parent)
    db.save(page)

    monkeypatch.setattr(
        "fichero_server.workflows.tools.vision_base._try_pdf_text_layer",
        lambda path: ["Recovered full page text"] if path == str(source_file) else [],
    )

    records = _records_from_selected_documents(
        {
            "library_path": str(test_package),
            "selected_doc_ids": [parent.id],
        }
    )

    assert records == [
        {
            "index": 0,
            "doc_id": page.id,
            "text": "Recovered full page text",
        }
    ]


def test_records_from_selected_documents_falls_back_to_page_content_when_transcription_blank(
    db, test_package
):
    page = Document(
        id="page-content-fallback",
        name="Loose page",
        doc_type=DocType.page,
        page_content="Recovered from page_content",
        metadata={"transcription": "   "},
    )
    db.save(page)

    records = _records_from_selected_documents(
        {
            "library_path": str(test_package),
            "selected_doc_ids": [page.id],
        }
    )

    assert records == [
        {
            "index": 0,
            "doc_id": page.id,
            "text": "Recovered from page_content",
        }
    ]


def test_records_from_selected_documents_deduplicates_selected_paths_and_sorts_pdf_pages(
    db, test_package, tmp_path
):
    source_file = tmp_path / "ordered.pdf"
    source_file.write_bytes(b"%PDF-1.4\n")

    folder = Document(
        id="folder-root",
        name="Folder",
        path=str(tmp_path),
        doc_type=DocType.folder,
    )
    parent = Document(
        id="ordered-pdf",
        parent_id=folder.id,
        name="Ordered PDF",
        path=str(source_file),
        doc_type=DocType.file,
        file_type=FileType.pdf,
    )
    page_two = Document(
        id="ordered-page-2",
        parent_id=parent.id,
        name="Ordered PDF p. 2",
        doc_type=DocType.page,
        sequence=2,
        metadata={"transcription": "Second page", "text_length": 11},
    )
    page_one = Document(
        id="ordered-page-1",
        parent_id=parent.id,
        name="Ordered PDF p. 1",
        doc_type=DocType.page,
        sequence=1,
        metadata={"transcription": "First page", "text_length": 10},
    )
    db.save(folder)
    db.save(parent)
    db.save(page_two)
    db.save(page_one)

    records = _records_from_selected_documents(
        {
            "library_path": str(test_package),
            "selected_doc_ids": [folder.id, parent.id, page_one.id],
        }
    )

    assert [record["doc_id"] for record in records] == [page_one.id, page_two.id]
    assert [record["text"] for record in records] == ["First page", "Second page"]
