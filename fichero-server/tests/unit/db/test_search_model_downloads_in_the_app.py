"""The search model downloads in the app (#5865 follow-up): a missing model queues a `download-model` row (progress
in Activity), the finished download clears the embedder's back-off, and an offline Mac is told so in words."""
from __future__ import annotations

import socket

from fichero_server.db import embed_process, embeddings
from fichero_server.execution import jobs
from fichero_server.importers import derivatives
from fichero_server.llm import local_models, model_downloads
from fichero_server.models import Document


def test_a_missing_model_queues_its_download(db, monkeypatch):
    doc = Document(name="p", page_content="some words")
    db.save(doc)
    jobs.load_kinds()
    monkeypatch.setattr(db, "embed", lambda target: (_ for _ in ()).throw(embed_process.EmbedderUnavailable("x")))
    queued = []
    monkeypatch.setattr(embed_process, "_cached", lambda *a: False)
    monkeypatch.setattr(local_models, "enqueue_download", lambda d, runtime, name, **k: queued.append((runtime, name)))
    derivatives._fetch_the_search_model(db)
    assert queued == [("embeddings", embeddings.search_embedder())]


def test_the_search_model_is_a_downloadable_embedding():
    assert embeddings.search_embedder() in local_models.EMBEDDINGS_MODELS


def test_a_finished_download_clears_the_back_off(monkeypatch, tmp_path):
    embeddings._LOAD_FAILURES["m"] = (0.0, "words")
    fake = type("TE", (), {"__init__": lambda self, **k: None})
    monkeypatch.setattr("fastembed.TextEmbedding", fake)
    mgr = local_models.LocalModelManager()
    mgr.download_embeddings_model(embeddings.search_embedder())
    assert embeddings._LOAD_FAILURES == {}


def test_an_offline_mac_is_said_in_words():
    broken = model_downloads.DownloadInterrupted("search", socket.gaierror(8, "nodename nor servname provided"))
    assert model_downloads.looks_offline(broken)
    assert "offline" in str(model_downloads.DownloadInterrupted("search", broken.cause, offline=True))
    assert not model_downloads.looks_offline(model_downloads.DownloadInterrupted("search", ConnectionResetError()))


def test_a_refused_embed_is_done_once_the_model_arrives(db, monkeypatch):
    """Spec `activity.pane.blocked-under-its-blocker` (#6593): the refused embed is BLOCKED on the download (not deferred
    every two minutes); the download's end unblocks it and it runs. (Stale before: it stubbed `db.embed`, which the stage
    no longer calls, and expected the +120 s deferral.)"""
    from tests.unit.jobs.test_runs_are_jobs import _wait_for

    doc = Document(name="p", page_content="some words")
    db.save(doc)
    jobs.load_kinds()
    arrived = []

    def tree(doc, _db, library=None):
        if not arrived:
            raise embed_process.EmbedderUnavailable("Search can't index yet: its model isn't downloaded.")
        from fichero_server.db import EmbedOutcome

        return EmbedOutcome(embedded=True, document_id=doc.id)  # a real outcome: an empty one reads as a failed page

    monkeypatch.setattr(derivatives, "_embed_document_tree", tree)
    monkeypatch.setattr(embed_process, "_cached", lambda *a: False)
    monkeypatch.setattr(local_models, "enqueue_download", lambda *a, **k: "the-download")
    job_id = jobs.enqueue(db, derivatives.EMBED_KIND, doc.id)
    assert _wait_for(lambda: jobs.read_job(db, job_id)["state"] == "waiting"
                     and db.execute_fetchone("SELECT blocked_by FROM jobs WHERE id = ?", [job_id])[0] == "the-download", 60), jobs.read_job(db, job_id)
    arrived.append(1)  # the download finished
    embeddings.forget_load_failures()
    assert jobs.unblock_on_download(db, "the-download", f"embeddings:{embeddings.search_embedder()}") == 1
    assert _wait_for(lambda: jobs.read_job(db, job_id)["state"] == "done", 60), jobs.read_job(db, job_id)


def test_offline_three_retries_make_one_download_row(db, monkeypatch):
    jobs.load_kinds()
    monkeypatch.setattr(embed_process, "_cached", lambda *a: False)
    # This counts the download rows queued; a download a lane picks up must not write into the models folder.
    monkeypatch.setattr(local_models.LocalModelManager, "_fetch_embeddings_into_one_folder", lambda *a, **k: None)
    for _ in range(3):  # three embed retries, 120 s apart, the Mac offline throughout
        derivatives._fetch_the_search_model(db)
    subject = f"embeddings:{embeddings.search_embedder()}"
    rows = db.execute_fetchall("SELECT state FROM jobs WHERE kind = ? AND subject = ?", [local_models.DOWNLOAD_KIND, subject])
    assert len(rows) == 1


def test_no_new_row_after_one_failed_and_it_stays_the_blocker(db, monkeypatch):
    """A failed download is never queued again by itself (decision 15); it stays the blocker."""
    jobs.load_kinds()
    monkeypatch.setattr(embed_process, "_cached", lambda *a: False)
    first = derivatives._fetch_the_search_model(db)
    db.execute("UPDATE jobs SET state = 'failed', finished_at = current_timestamp WHERE kind = ?",
               [local_models.DOWNLOAD_KIND])
    for _ in range(3):
        assert derivatives._fetch_the_search_model(db) == first
    assert len(db.execute_fetchall("SELECT 1 FROM jobs WHERE kind = ?", [local_models.DOWNLOAD_KIND])) == 1


def test_a_cached_model_queues_no_download(db, monkeypatch):
    jobs.load_kinds()
    monkeypatch.setattr(embed_process, "_cached", lambda *a: True)
    derivatives._fetch_the_search_model(db)
    assert db.execute_fetchall("SELECT 1 FROM jobs WHERE kind = ?", [local_models.DOWNLOAD_KIND]) == []


def test_a_database_error_while_queueing_the_download_still_blocks_the_embed(db, monkeypatch):
    """467 MED: the queue step runs before the block; an error in it must not turn the wait into a failure. The row is
    blocked on the typed need when no job supplies the blocker."""
    import duckdb

    from tests.unit.jobs.test_runs_are_jobs import _wait_for

    doc = Document(name="p", page_content="some words")
    db.save(doc)
    jobs.load_kinds()
    words = "Search can't index yet: its model isn't downloaded."
    monkeypatch.setattr(derivatives, "_embed_document_tree",
                        lambda *a, **k: (_ for _ in ()).throw(embed_process.EmbedderUnavailable(words)))
    monkeypatch.setattr(embed_process, "_cached", lambda *a: False)
    monkeypatch.setattr(local_models, "enqueue_download", lambda *a, **k: (_ for _ in ()).throw(duckdb.Error("table locked")))
    job_id = jobs.enqueue(db, derivatives.EMBED_KIND, doc.id)
    need = f"model:embeddings:{embeddings.search_embedder()}"
    assert _wait_for(lambda: db.execute_fetchone("SELECT blocked_by FROM jobs WHERE id = ?", [job_id])[0] == need, 60), jobs.read_job(db, job_id)
    assert jobs.read_job(db, job_id)["state"] == "waiting"
