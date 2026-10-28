"""An embedder one test leaves loaded must not be there for the next (#6129): the autouse fixture in tests/conftest.py."""
from fichero_server.db import embeddings


def test_an_embedder_a_test_loaded_is_dropped_and_one_still_in_use_is_left_to_its_thread(monkeypatch, request):
    """Drives the fixture's own generator, so nothing is left in use for the session (and no test is a bare setup for another)."""
    import inspect

    # The engine's own conftest, by its file: `sys.modules["conftest"]` is whichever package-less directory's conftest
    # loaded last (tests/unit/jobs's, run before this file), which has no such fixture.
    conftest = next(p for p in request.config.pluginmanager.get_plugins()
                    if str(getattr(p, "__file__", "")).endswith("fichero-server/tests/conftest.py"))
    fixture = inspect.unwrap(conftest._no_embedder_leaks_between_tests)
    monkeypatch.setattr(embeddings, "_EMBEDDER_CACHE", dict(embeddings._EMBEDDER_CACHE))
    monkeypatch.setattr(embeddings, "_EMBEDDER_IN_USE", {"busy-test-model": 1})
    before = set(embeddings._EMBEDDER_CACHE)
    run = fixture()
    next(run)
    embeddings._EMBEDDER_CACHE["busy-test-model"] = object()
    embeddings._EMBEDDER_CACHE["idle-test-model"] = object()
    next(run, None)
    assert "busy-test-model" in embeddings._EMBEDDER_CACHE
    assert "idle-test-model" not in embeddings._EMBEDDER_CACHE
    assert set(embeddings._EMBEDDER_CACHE) - {"busy-test-model"} == before  # the cache is otherwise as it was
