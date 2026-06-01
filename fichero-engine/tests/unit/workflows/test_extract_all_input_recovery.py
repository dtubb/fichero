"""Regression tests for extract_all input recovery (#1166)."""

from __future__ import annotations

from fichero.workflows.tools.extract_all import _recover_text_and_records


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
