"""The 2026-10-30 Air: "Model BAAI/bge-m3 is not supported in TextEmbedding", 31,385 times, one per document.

fastembed 0.8.0's catalogue lacks bge-m3; the engine registers it (`add_custom_model`) in its own process, but the
model loads in a child the seed forked at engine start, before any registration ran. The child must register the
model itself. And a model whose files are here and still will not load is said once and parks the lane: no download
mends it, and a retry per document is 31k warnings.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import textwrap

import pytest

from fichero_server.db import embed_process, embeddings

#: A child process that stands for the seed's: its fastembed never saw the engine's registration.
_CHILD = textwrap.dedent("""
    import json, sys
    from fastembed import TextEmbedding
    before = any(m.model.lower() == "baai/bge-m3" for m in TextEmbedding._list_supported_models())
    from fichero_server.db import embed_process
    embed_process.register_custom_model(sys.argv[1])
    after = any(m.model.lower() == "baai/bge-m3" for m in TextEmbedding._list_supported_models())
    print(json.dumps({"before": before, "after": after}))
""")


def test_a_fresh_process_learns_bge_m3_before_it_loads():
    """What the seed's child sees: fastembed's own catalogue (no bge-m3), then the model registered by the loader."""
    out = subprocess.run([sys.executable, "-c", _CHILD, embeddings.BGE_M3_EMBEDDING_SPACE.fastembed_model_name],
                         capture_output=True, text=True, timeout=120, env={**os.environ, "FICHERO_EMBED_IN_PROCESS": "1"})
    assert out.returncode == 0, out.stderr[-800:]
    import json

    seen = json.loads(out.stdout.strip().splitlines()[-1])
    assert seen["before"] is False, "fastembed now ships bge-m3: the registration can go"
    assert seen["after"] is True


def test_a_model_that_will_not_load_is_said_once_and_not_tried_per_document(monkeypatch, caplog):
    """The files are cached, the load fails (the Air's ValueError): one ERROR in the log, and the next embed is refused
    at once with the same words -- no new child, no 120 s back-off to expire."""
    loads = []

    class _Refuses:
        def __init__(self, model_name, cache_dir, threads):
            loads.append(model_name)
            raise embed_process.EmbedderUnavailable(
                embed_process.load_failure_words("ValueError: Model BAAI/bge-m3 is not supported in TextEmbedding", cached=True))

    monkeypatch.setattr(embed_process, "RemoteEmbedder", _Refuses)
    monkeypatch.setattr(embed_process, "in_process", lambda: False)
    monkeypatch.setattr(embeddings, "_LOAD_FAILURES", {})
    monkeypatch.setattr(embeddings, "_LOAD_FAILURE_SAID", set())
    monkeypatch.setattr(embeddings, "_EMBEDDER_CACHE", {})
    monkeypatch.setattr(embeddings, "LOAD_FAILURE_BACKOFF_SECONDS", 0.0)  # even with no back-off: a defect holds
    with caplog.at_level(logging.DEBUG):
        for _ in range(5):
            with pytest.raises(embed_process.EmbedderUnavailable) as raised:
                embeddings._get_shared_embedder("BAAI/bge-m3", "/nowhere")
    assert loads == ["BAAI/bge-m3"], "the load was tried again for a later document"
    assert embed_process.is_a_load_defect(str(raised.value))
    said = [r for r in caplog.records if r.levelno >= logging.ERROR and "bge-m3" in r.getMessage()]
    assert len(said) == 1, [r.getMessage() for r in said]
    embeddings.forget_load_failures()  # a download finished or a person asked: tried afresh
    with pytest.raises(embed_process.EmbedderUnavailable):
        embeddings._get_shared_embedder("BAAI/bge-m3", "/nowhere")
    assert len(loads) == 2


def test_a_missing_download_still_backs_off_and_retries(monkeypatch):
    """The other failure -- not downloaded yet -- keeps its shape: refused for the back-off, then tried again."""
    monkeypatch.setattr(embeddings, "_LOAD_FAILURES", {"m": (0.0, "The search model is not downloaded yet: it is being fetched")})
    monkeypatch.setattr(embeddings, "LOAD_FAILURE_BACKOFF_SECONDS", 0.0)
    assert embeddings.load_failure_in_force("m") is None
    monkeypatch.setattr(embeddings, "LOAD_FAILURE_BACKOFF_SECONDS", 10**9)
    assert embeddings.load_failure_in_force("m")


def test_a_load_defect_fails_the_embed_job_rather_than_deferring_it(monkeypatch):
    """`wait_for_the_search_model` defers a job while a download runs; for a model that will not load it fails the job
    with the sentence, so Activity shows it once and the lane is not asked every two minutes per page."""
    from fichero_server.importers import derivatives

    class _NoDb:
        def execute(self, *a, **k):
            raise AssertionError("no row should be touched")

    with pytest.raises(RuntimeError, match="could not be loaded"):
        derivatives.wait_for_the_search_model(_NoDb(), embed_process.load_failure_words("ValueError: nope", cached=True))
