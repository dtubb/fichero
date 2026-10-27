"""`recipes-run.engine.embedder-child-never-downloads` (#6218): the search model's forked child never fetches the model.
A model not in the cache is refused before any fork, so the job waits while the app's download (a row in Activity, in
the engine itself) fetches it, then embeds; the child always loads offline.
WHY: the M4 run (2026-10-26, integration 35e91f42b): the forked child began "Fetching 7 files" from the Hub, a LanceDB
thread died with "Bad file descriptor" after the fork, and make-a-vector failed 10 of 10: the run ended failed."""
from __future__ import annotations

import multiprocessing

import pytest

from fichero_server.actions import page_text_cache
from fichero_server.db import embed_process
from fichero_server.execution import jobs
from fichero_server.importers import derivatives


def test_a_model_not_in_the_cache_is_refused_before_any_fork(tmp_path, monkeypatch):
    def no_fork(*_a, **_k):
        raise AssertionError("forked a child to download the model")

    monkeypatch.setattr(multiprocessing, "get_context", no_fork)
    with pytest.raises(embed_process.EmbedderUnavailable, match="not downloaded"):
        embed_process.RemoteEmbedder("intfloat/multilingual-e5-large", str(tmp_path), 1)


def test_the_child_always_loads_offline(tmp_path):
    assert embed_process._child_env("intfloat/multilingual-e5-large", str(tmp_path))["HF_HUB_OFFLINE"] == "1"


def test_make_a_vector_waits_for_the_download_instead_of_failing(db, monkeypatch):
    from fichero_server.db import EmbedOutcome
    from fichero_server.models import DocType, Document

    doc = Document(name="p.jpg", doc_type=DocType.file, page_content="text")
    db.save(doc)
    fetched = []
    monkeypatch.setattr(derivatives, "_fetch_the_search_model", lambda _db: fetched.append(True))
    monkeypatch.setattr(type(db), "embed_unless_current", lambda self, d: EmbedOutcome(
        embedded=False, reason="embedder_unavailable", document_id=d.id, error="The search model is not downloaded yet"))
    with pytest.raises(jobs.JobDeferred):
        page_text_cache._reembed(db, doc.id)
    assert fetched == [True]
