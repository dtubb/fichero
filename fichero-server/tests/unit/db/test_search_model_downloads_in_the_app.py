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
