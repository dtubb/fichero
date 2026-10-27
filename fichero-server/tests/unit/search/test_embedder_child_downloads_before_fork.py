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


# The M4 rerun (2026-10-26 22:55, integration 7337332c2): a PARTIAL bge-m3 folder left by the earlier crashed child
# passed the folder check, the child loaded offline and failed ("Could not load model BAAI/bge-m3 from any source"),
# no download was queued (the folder looked cached), and make-a-vector failed 10 of 10.

def _snapshot(tmp_path, files):
    snap = tmp_path / "models--BAAI--bge-m3" / "snapshots" / "abc"
    for name in files:
        (snap / name).parent.mkdir(parents=True, exist_ok=True)
        (snap / name).write_bytes(b"x")
    return snap


def test_a_partial_cache_is_not_cached(tmp_path):
    _snapshot(tmp_path, ["config.json", "tokenizer.json", "onnx/model.onnx"])  # model.onnx_data never arrived
    assert not embed_process._cached("BAAI/bge-m3", str(tmp_path))


def test_a_link_to_a_blob_that_never_arrived_is_not_cached(tmp_path):
    snap = _snapshot(tmp_path, ["config.json", "tokenizer.json", "onnx/model.onnx", "onnx/sentencepiece.bpe.model"])
    (snap / "onnx" / "model.onnx_data").symlink_to(tmp_path / "blobs-missing")
    assert not embed_process._cached("BAAI/bge-m3", str(tmp_path))


def test_every_file_of_the_model_is_cached(tmp_path):
    _snapshot(tmp_path, ["config.json", "tokenizer.json", "onnx/model.onnx", "onnx/model.onnx_data",
                         "onnx/sentencepiece.bpe.model"])
    assert embed_process._cached("BAAI/bge-m3", str(tmp_path))


def test_a_batch_that_meets_a_missing_model_waits_instead_of_failing_each_page(db, monkeypatch):
    from fichero_server.models import DocType, Document

    docs = [Document(name=f"p{i}.jpg", doc_type=DocType.file, page_content=f"A page of the diary, entry {i}, long enough to embed for search.") for i in range(3)]

    def unavailable(*_a, **_k):
        raise embed_process.EmbedderUnavailable("The search model could not be loaded: Could not load model")

    monkeypatch.setattr(type(db), "_embed_texts", unavailable)
    with pytest.raises(embed_process.EmbedderUnavailable):
        db.embed_many(docs)
