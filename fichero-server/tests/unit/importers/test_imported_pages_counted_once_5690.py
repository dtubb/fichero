"""`activity.waiting-says-why` and the import queue's count (#5690): "Processing imported pages" counts pages, each
once.

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md. WHY (2026-10-11, the MCP onboarding walk):
a 92-page project's import queue counted 178: every page with its own text was counted when queued and again by
its embed (the page itself among the embed's targets). A PDF's pages are still added to the count, one each.
"""
from __future__ import annotations

from types import SimpleNamespace

from fichero_server.importers import derivatives
from fichero_server.models import FileType

LIB = "/tmp/counted-once-5690.fichero"


class _Db:
    def __init__(self, children=()):
        self.children = list(children)

    def query(self, _model, parent_id=None):
        return self.children

    def has_embedding(self, _doc_id):
        return True  # already embedded: the count is what is under test, not the embedding


def _page(doc_id, file_type=FileType.image):
    return SimpleNamespace(id=doc_id, page_content="vendió Juan una casa", file_type=file_type)


def _count():
    state = derivatives._progress.get(derivatives._key(LIB))
    return (state["done"], state["total"]) if state else None


def test_a_page_with_its_own_text_is_one_page():
    derivatives._progress.pop(derivatives._key(LIB), None)
    derivatives._progress_add(LIB, 1)
    derivatives._embed_document_tree(_page("p1"), _Db(), LIB)
    assert _count() == (0, 1), "its embed is the same page, not another"
    derivatives._progress_tick(LIB)  # the stage's own end
    assert _count() is None, "done: 1 of 1"


def test_a_pdfs_pages_are_added_one_each():
    derivatives._progress.pop(derivatives._key(LIB), None)
    derivatives._progress_add(LIB, 1)
    pdf = _page("book", FileType.pdf)
    derivatives._embed_document_tree(pdf, _Db([_page("b1"), _page("b2")]), LIB)
    assert _count() == (2, 3), "the book and its two pages, two of them done"
    derivatives._progress.pop(derivatives._key(LIB), None)
