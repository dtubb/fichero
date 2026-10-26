"""#6131: a failed re-embed after a folder's description became its content is not swallowed in put_in_content: the content
is saved, then the failure goes up to describe_folders, which puts it on the step's flags (the seam test forbids only-log)."""
from __future__ import annotations

import pytest

from fichero_server.recipes import catalogue_step


class _Doc:
    metadata: dict = {}
    page_content = ""


class _Db:
    def __init__(self):
        self.saved = []

    def get(self, _model, _id):
        return self.doc

    def save(self, doc):
        self.saved.append(doc)


def test_the_content_is_saved_and_a_failed_reembed_goes_up(monkeypatch):
    monkeypatch.setattr("fichero_server.workflows.curation_guard.page_content_is_user_edited", lambda doc: False)
    monkeypatch.setattr("fichero_server.workflows.curation_guard.page_text_is_derived", lambda db, i: False)

    def boom(_db, _ids):
        raise RuntimeError("model lane down")

    monkeypatch.setattr("fichero_server.actions.page_text_cache.queue_reembed", boom)
    db, doc = _Db(), _Doc()
    db.doc = doc
    with pytest.raises(catalogue_step.ReembedNotQueued, match="model lane down"):
        catalogue_step.put_in_content(db, "f1", "A description.", "art1")
    assert doc.page_content == "A description." and db.saved == [doc]


def test_a_failed_save_is_not_a_reembed_failure_and_still_fails(monkeypatch):
    monkeypatch.setattr("fichero_server.workflows.curation_guard.page_content_is_user_edited", lambda doc: False)
    monkeypatch.setattr("fichero_server.workflows.curation_guard.page_text_is_derived", lambda db, i: False)

    class _FailingDb(_Db):
        def save(self, doc):
            raise OSError("disk full")

    db = _FailingDb()
    db.doc = _Doc()
    with pytest.raises(OSError, match="disk full"):
        catalogue_step.put_in_content(db, "f1", "A description.", "art1")
