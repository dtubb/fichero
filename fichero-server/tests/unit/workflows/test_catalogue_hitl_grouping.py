"""Tests for catalogue HITL grouping ambiguity heuristics (#1097)."""

from fichero_server.models import Document, DocType, FileType, Status
from fichero_server.workflows.tools.catalogue import _grouping_is_ambiguous


def _doc(doc_id: str, file_type: FileType, case_id: str | None = None) -> Document:
    return Document(
        id=doc_id,
        name=doc_id,
        doc_type=DocType.file,
        file_type=file_type,
        status=Status.pending,
        case_id=case_id,
    )


def test_grouping_is_ambiguous_when_unassigned_and_mixed_types() -> None:
    groups = {
        None: [_doc(f"u{i}", FileType.image) for i in range(20)],
        "case-a": [_doc(f"c{i}", FileType.pdf, case_id="case-a") for i in range(10)],
    }
    assert _grouping_is_ambiguous(groups, min_items=25) is True


def test_grouping_not_ambiguous_when_small_batch() -> None:
    groups = {None: [_doc(f"u{i}", FileType.image) for i in range(8)]}
    assert _grouping_is_ambiguous(groups, min_items=25) is False

