"""A page tiled into strips must keep ALL its text, in order (2026-08-04).

``zoom`` in tile mode splits one page into N strips and pairs every strip with
the SAME document. ``process_vision`` then ran the vision tool N times for one
page and each result did ``doc.page_content = content`` — an assignment. Last
strip won: nine of ten transcriptions were produced, paid for, and discarded.
Daniel: "the final transcript is not all bits put back together."

These pin the fix and, as importantly, its two failure modes:

* the pieces must be joined in FILE order, not completion order (the fan-out is
  concurrent, so appending inside the per-file path would scramble the page —
  worse than truncating it, because scrambled text still looks plausible);
* a document with ONE file must behave exactly as before, since this path is
  shared by every vision tool.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fichero_server.models import Document, Status


@pytest.fixture
def temp_db(tmp_path):
    from fichero_server.db import Database

    db = Database(tmp_path / "fichero.duckdb")
    yield db
    db.close()


def _write(temp_db, indices_by_doc, texts):
    from fichero_server.workflows.tools.vision_base import _write_joined_page_content

    with patch("fichero_server.db.db_manager.get_database", return_value=temp_db):
        _write_joined_page_content(
            indices_by_doc=indices_by_doc,
            texts=texts,
            library_path=str(temp_db.path.parent),
        )


def test_joins_every_strip_in_file_order(temp_db):
    doc = Document(name="page.png", path="/tmp/page.png")
    temp_db.save(doc)

    # Deliberately NOT in ascending order in the mapping: the writer must sort
    # by index, because the fan-out completes out of order.
    _write(temp_db, {doc.id: [2, 0, 1]}, ["first", "second", "third"])

    assert temp_db.get(Document, doc.id).page_content == "first\nsecond\nthird"


def test_keeps_every_piece_not_just_the_last(temp_db):
    """The regression itself: ten strips must not collapse to one."""
    doc = Document(name="page.png", path="/tmp/page.png")
    temp_db.save(doc)

    texts = [f"line {n}" for n in range(10)]
    _write(temp_db, {doc.id: list(range(10))}, texts)

    content = temp_db.get(Document, doc.id).page_content
    for text in texts:
        assert text in content, f"{text!r} was dropped — this is the bug"
    assert content == "\n".join(texts)


def test_blank_strips_are_dropped_without_reordering(temp_db):
    doc = Document(name="page.png", path="/tmp/page.png")
    temp_db.save(doc)

    _write(temp_db, {doc.id: [0, 1, 2, 3]}, ["alpha", "   ", "", "omega"])

    assert temp_db.get(Document, doc.id).page_content == "alpha\nomega"


def test_all_blank_leaves_existing_content_untouched(temp_db):
    """Nothing to say is not the same as "erase what is there"."""
    doc = Document(name="page.png", path="/tmp/page.png", page_content="previous")
    temp_db.save(doc)

    _write(temp_db, {doc.id: [0, 1]}, ["", "  "])

    assert temp_db.get(Document, doc.id).page_content == "previous"


def test_user_edited_page_is_never_overwritten(temp_db):
    doc = Document(name="page.png", path="/tmp/page.png", page_content="my careful edit")
    temp_db.save(doc)

    with patch(
        "fichero_server.workflows.curation_guard.page_content_is_user_edited",
        return_value=True,
    ):
        _write(temp_db, {doc.id: [0, 1]}, ["machine A", "machine B"])

    assert temp_db.get(Document, doc.id).page_content == "my careful edit"


def test_marks_processing_so_the_run_boundary_owns_completion(temp_db):
    doc = Document(name="page.png", path="/tmp/page.png")
    temp_db.save(doc)

    _write(temp_db, {doc.id: [0]}, ["only"])

    assert temp_db.get(Document, doc.id).status == Status.processing


def test_missing_document_does_not_stop_the_others(temp_db):
    """A vanished document must not fail a run whose artifacts all saved.

    Asserted via a SIBLING rather than by "it didn't raise": what matters is
    that the remaining documents still get their text, which is the behaviour a
    bare `no exception` test would not have caught if the loop aborted early.
    """
    survivor = Document(name="p.png", path="/tmp/p.png")
    temp_db.save(survivor)

    _write(temp_db, {"no-such-doc": [0], survivor.id: [1, 2]}, ["gone", "kept a", "kept b"])

    assert temp_db.get(Document, survivor.id).page_content == "kept a\nkept b"


def test_several_documents_each_get_their_own_join(temp_db):
    first = Document(name="p1.png", path="/tmp/p1.png")
    second = Document(name="p2.png", path="/tmp/p2.png")
    temp_db.save(first)
    temp_db.save(second)

    _write(
        temp_db,
        {first.id: [0, 1], second.id: [2, 3]},
        ["1a", "1b", "2a", "2b"],
    )

    assert temp_db.get(Document, first.id).page_content == "1a\n1b"
    assert temp_db.get(Document, second.id).page_content == "2a\n2b"
