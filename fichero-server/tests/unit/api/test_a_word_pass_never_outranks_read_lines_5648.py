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


def _words_in_lines(db, doc_id: str) -> tuple[list[str], dict[str, list[str]]]:
    """A pass of two lines with no readings, each holding three read words: line id -> its word ids."""
    pass_id = registry.invoke(db, "segment.pass_create", {"document_id": doc_id, "name": "apple"}, APPLE).result["id"]
    lines, words = [], {}
    for i in range(2):
        line = registry.invoke(db, "segment.create", {
            "document_id": doc_id, "pass_id": pass_id, "kind": "line",
            "anchor": SourceAnchor(document_id=doc_id, rect=[0.1, 0.1 + 0.1 * i, 0.6, 0.05]).model_dump(mode="json"),
        }, APPLE).result["segment_ids"][0]
        lines.append(line)
        for j in range(3):
            word = registry.invoke(db, "segment.create", {
                "document_id": doc_id, "pass_id": pass_id, "kind": "word", "parent_segment_id": line,
                "anchor": SourceAnchor(document_id=doc_id, rect=[0.1 + 0.2 * j, 0.1 + 0.1 * i, 0.15, 0.05]).model_dump(mode="json"),
            }, APPLE).result["segment_ids"][0]
            registry.invoke(db, "representation.create", {
                "document_id": doc_id, "segment_id": word, "kind": "transcription", "content": f"w{i}{j}"}, APPLE)
            words.setdefault(line, []).append(word)
    return lines, words


def test_a_word_pass_is_listed_by_its_lines_5648(db):
    """Ruled 2026-10-17: words that sit in lines are listed one row per line, the line's words joined."""
    from fichero_server.tool_context import tool_context

    doc_id = _page(db)
    lines, _words = _words_in_lines(db, doc_id)
    shown = tool_context(db, doc_id)
    assert shown.segment_ids == lines
    assert [row.split(" | ")[-1] for row in shown.text.splitlines()] == ["w00 w01 w02", "w10 w11 w12"]


def test_a_correction_to_a_grouped_line_is_a_reading_of_the_line_and_the_words_keep_theirs_5648(db):
    from fichero_server.llm.working_lines import correct_lines
    from fichero_server.models import Artifact, ContentRepresentation

    doc_id = _page(db)
    lines, words = _words_in_lines(db, doc_id)
    review = Artifact(document_id=doc_id, artifact_type="transcription_review", provider="x", model="y", content="")
    db.save(review)
    made, said = correct_lines(db, document_id=doc_id, text=f"{lines[0]} | certain | w00 w01 corrected",
                               artifact_id=review.id, run_id="run-r", library_path=None)
    assert len(made) == 1 and said.startswith("1 of 2"), said
    (reading,) = db.query(ContentRepresentation, segment_id=lines[0])
    assert reading.content == "w00 w01 corrected"
    assert [r.content for w in words[lines[0]] for r in db.query(ContentRepresentation, segment_id=w)] == [
        "w00", "w01", "w02"]
