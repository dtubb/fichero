"""#5188: a test run never downloads an embedding model.

Saving an entity or claim auto-embeds it, and FastEmbed downloads an uncached model from Hugging
Face (or its fallback URL). With a fresh HOME that was 7 files and ~110 s during seeding, and on a
machine without the network it silently degraded. The conftest sets HF_HUB_OFFLINE; if that line is
removed or FastEmbed stops honouring it, loading an uncached model reaches for the network and
this test fails, naming the host it tried.
"""

import os
import socket

import pytest


def test_the_suite_runs_offline_for_models():
    assert os.environ.get("HF_HUB_OFFLINE") == "1", "tests/conftest.py must set HF_HUB_OFFLINE (#5188)"


def test_an_uncached_model_fails_to_load_without_touching_the_network(tmp_path, monkeypatch):
    from fichero_server.db import embeddings

    tried: list[object] = []

    def refuse(address, *args, **kwargs):
        tried.append(address)
        raise OSError(f"test tried the network: {address}")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", lambda self, address: refuse(address))
    monkeypatch.setattr(embeddings, "_EMBEDDER_CACHE", {})

    with pytest.raises(Exception):
        embeddings._get_shared_embedder("intfloat/multilingual-e5-large", str(tmp_path / "empty-cache"))
    assert tried == [], f"loading an uncached model reached for the network: {tried}"
