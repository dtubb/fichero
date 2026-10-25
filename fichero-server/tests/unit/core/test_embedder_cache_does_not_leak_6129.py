"""An embedder one test leaves loaded must not be there for the next (#6129): the autouse fixture in tests/conftest.py."""
from fichero_server.db import embeddings


def test_a_test_loads_an_embedder():
    embeddings._EMBEDDER_CACHE["leaky-test-model"] = object()


def test_the_next_test_does_not_find_it():
    assert "leaky-test-model" not in embeddings._EMBEDDER_CACHE


def test_an_embedder_still_in_use_is_left_to_its_thread(monkeypatch):
    """Drives the fixture's own generator, so nothing is left in use for the session."""
    import inspect
    import sys

    fixture = inspect.unwrap(sys.modules["conftest"]._no_embedder_leaks_between_tests) \
        if "conftest" in sys.modules else None
    if fixture is None:
        from tests import conftest
        fixture = inspect.unwrap(conftest._no_embedder_leaks_between_tests)
    monkeypatch.setattr(embeddings, "_EMBEDDER_CACHE", dict(embeddings._EMBEDDER_CACHE))
    monkeypatch.setattr(embeddings, "_EMBEDDER_IN_USE", {"busy-test-model": 1})
    run = fixture()
    next(run)
    embeddings._EMBEDDER_CACHE["busy-test-model"] = object()
    embeddings._EMBEDDER_CACHE["idle-test-model"] = object()
    next(run, None)
    assert "busy-test-model" in embeddings._EMBEDDER_CACHE
    assert "idle-test-model" not in embeddings._EMBEDDER_CACHE
