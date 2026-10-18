"""A pass of words never outranks a pass of read lines as the working pass (#5648, ruled 2026-10-17).

WHY: an Apple Vision run on a page Kraken had read made its 656 word boxes the working pass, newest first, so the
review was sent one row per word (43k tokens) and a local model timed out. Lines with readings are what a reader and a
review work on; a newer pass of words sits after them, and stays the working pass where it is all there is.
"""

from __future__ import annotations

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import working_pass
from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.models.anchors import SourceAnchor

pytestmark = pytest.mark.source_model

KRAKEN = ActionContext(actor="kraken", run_id="run-1", library_path=None, is_bootstrap=True)
APPLE = ActionContext(actor="apple-vision", run_id="run-2", library_path=None, is_bootstrap=True)


def _page(db) -> str:
    doc = Document(name="c01_012.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/p/c01_012.jpg", status=Status.completed)
    db.save(doc)
    return doc.id


def _pass(db, doc_id: str, kind: str, count: int, ctx: ActionContext, read: bool) -> str:
    pass_id = registry.invoke(db, "segment.pass_create", {"document_id": doc_id, "name": ctx.actor}, ctx).result["id"]
    for i in range(count):
        segment = registry.invoke(db, "segment.create", {
            "document_id": doc_id, "pass_id": pass_id, "kind": kind,
            "anchor": SourceAnchor(document_id=doc_id, rect=[0.1, 0.05 + 0.05 * i, 0.6, 0.04]).model_dump(mode="json"),
        }, ctx).result["segment_ids"][0]
        if read:
            registry.invoke(db, "representation.create", {
                "document_id": doc_id, "segment_id": segment, "kind": "transcription", "content": f"{kind} {i}"}, ctx)
    return pass_id


def test_a_newer_pass_of_words_does_not_take_the_page_from_read_lines_5648(db):
    doc_id = _page(db)
    lines = _pass(db, doc_id, "line", 2, KRAKEN, read=True)
    _pass(db, doc_id, "word", 6, APPLE, read=True)
    assert working_pass(db, doc_id).pass_id == lines


def test_a_pass_of_words_is_still_the_working_pass_beside_lines_nobody_read_5648(db):
    doc_id = _page(db)
    _pass(db, doc_id, "line", 2, KRAKEN, read=False)
    words = _pass(db, doc_id, "word", 6, APPLE, read=True)
    assert working_pass(db, doc_id).pass_id == words
