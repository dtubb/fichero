"""An embedder one test leaves loaded must not be there for the next (#6129): the autouse fixture in tests/conftest.py."""
from fichero_server.db import embeddings


def test_a_test_loads_an_embedder():
    embeddings._EMBEDDER_CACHE["leaky-test-model"] = object()


def test_the_next_test_does_not_find_it():
    assert "leaky-test-model" not in embeddings._EMBEDDER_CACHE
