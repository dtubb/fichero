"""#6129 acceptance: after an embed finishes and the idle spell passes, the embedder is released and its process's memory
goes back. Needs the embedding model on this machine; skipped where it is not installed (nothing here downloads it)."""
from __future__ import annotations

import os
import subprocess
import time

import pytest

from fichero_server.db import embed_process, embeddings


def _rss_bytes(pid: int) -> int:
    done = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True)
    return int(done.stdout.strip() or 0) * 1024


def _installed_space():
    from fichero_server.llm.local_models import MODELS_BASE

    cache_dir = MODELS_BASE / "embeddings"
    for space in embeddings.SUPPORTED_EMBEDDING_SPACES.values():
        if cache_dir.is_dir() and embed_process._cached(space.fastembed_model_name, str(cache_dir)):
            return space, str(cache_dir)
    return None


def test_the_embedders_process_gives_its_memory_back_when_it_is_released(monkeypatch):
    found = _installed_space()
    if found is None:
        pytest.skip("no embedding model is installed on this machine")
    space, cache_dir = found
    monkeypatch.delenv("FICHERO_EMBED_IN_PROCESS", raising=False)
    embeddings._register_fastembed_model_for_space(space)  # as the database does before it embeds
    with embeddings.leased_embedder(space.fastembed_model_name, cache_dir) as embedder:
        list(embedder.embed(["a short text"]))
        pid = embedder._process.pid
        held = _rss_bytes(pid)
    assert held > 500 * 1024**2, "the model is in the child's memory while it is held"
    assert embeddings.release_idle_embedders(idle_seconds=0, reason="test") == [space.fastembed_model_name]
    for _ in range(50):
        if _rss_bytes(pid) == 0:
            break
        time.sleep(0.1)
    assert _rss_bytes(pid) < held * 0.2, "the process, and so its memory, is gone after the release"
    assert not embeddings.embedder_loaded()
    assert os.getpid() != pid
