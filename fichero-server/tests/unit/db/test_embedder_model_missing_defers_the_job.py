"""P2 / 436: a search model that cannot be loaded is loaded ONCE per back-off window, and the embed JOB waits with the
sentence as its reason; it does not end done with a count in the document's metadata."""
from __future__ import annotations

import pytest

from fichero_server.db import embed_process, embeddings
from fichero_server.execution import jobs
from fichero_server.importers import derivatives
from fichero_server.models import Document

WORDS = "Search can't index yet: its model isn't downloaded, and fetching it failed. Check the internet connection."


@pytest.fixture(autouse=True)
def clean():
    embeddings.forget_load_failures()
    yield
    embeddings.forget_load_failures()


def test_a_failed_load_is_tried_once_for_two_pages(monkeypatch):
    loads = []

    def refuse(*a, **k):
        loads.append(1)
        raise embed_process.EmbedderUnavailable(WORDS)

    monkeypatch.setattr(embed_process, "in_process", lambda: False)
    monkeypatch.setattr(embed_process, "RemoteEmbedder", refuse)
    for _ in range(2):
        with pytest.raises(embed_process.EmbedderUnavailable, match="Search can't index yet"):
            embeddings._get_shared_embedder("some/model", "/tmp/none")
    assert loads == [1], "the second page was answered from the remembered failure, with no new child or fetch"


def test_the_embed_job_waits_with_the_sentence_as_its_reason(db, monkeypatch):
    doc = Document(name="p", page_content="some words")
    db.save(doc)
    jobs.load_kinds()
    monkeypatch.setattr(db, "embed", lambda target: (_ for _ in ()).throw(embed_process.EmbedderUnavailable(WORDS)))
    job_id = jobs.enqueue(db, derivatives.EMBED_KIND, doc.id)
    from tests.unit.jobs.test_runs_are_jobs import _wait_for

    assert _wait_for(lambda: jobs.read_job(db, job_id)["reason"] == WORDS, 60), jobs.read_job(db, job_id)
    assert jobs.read_job(db, job_id)["state"] == "waiting"
