"""`safety.trash.one-delete-path` (#5243): every way the app deletes a document sends the same `document.delete` call.

WHY: the sidebar, the Library pane and Shortcuts each declared their own private copy of the action's parameter type, and
the document store kept two deletes that went to the plain route and wrote no step to undo. One shape, one place.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[3] / "fichero" / "fichero"


def _swift() -> dict[Path, str]:
    return {p: p.read_text(encoding="utf-8") for p in APP.rglob("*.swift")}


def test_document_delete_has_one_parameter_type_in_the_app():
    defs = [p for p, text in _swift().items() if re.search(r"struct DocumentDelete\w*(Params|Payload)\b", text)]
    assert [p.name for p in defs] == ["UndoableChange.swift"], defs


def test_no_app_code_deletes_a_document_outside_the_audited_action():
    """The plain DELETE route writes no step to undo; only the engine-facing service may name it."""
    plain = [p.name for p, text in _swift().items() if re.search(r"\.deleteDocument\(", text) and p.name != "DocumentService.swift"]
    assert plain == [], plain
