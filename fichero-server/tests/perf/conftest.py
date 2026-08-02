"""Performance-test fixtures for the shared authenticated FastAPI app."""

import sys
from pathlib import Path

import pytest

from fichero_server.api.auth import initialize_token


def _root_conftest_helper(name: str):
    """Reach a helper already defined in the loaded ``tests/conftest.py``.

    Both this file and its parent are literally named ``conftest.py`` with
    no package (`__init__.py`) between them, so a plain ``from conftest
    import ...`` here collides with pytest's OWN module registration for
    THIS file (pytest binds the name ``conftest`` to whichever of the two
    it loaded first) and ends up importing this module from itself —
    circular. Re-executing the parent by file path instead (the technique
    ``test_conftest_temp_cleanup.py`` uses) would work but reruns its
    top-level side effects a SECOND time, including
    ``@app.middleware("http")`` — double-registering the query-count
    ratchet's counting middleware and silently doubling every count it
    records. pytest loads parent conftests before child ones, so
    ``tests/conftest.py`` is already a fully-initialized entry in
    ``sys.modules`` by the time this file runs — find it by file path
    instead of re-running it.
    """
    root_path = (Path(__file__).resolve().parent.parent / "conftest.py").resolve()
    for module in list(sys.modules.values()):
        if getattr(module, "__file__", None) and Path(module.__file__).resolve() == root_path:
            return getattr(module, name)
    raise RuntimeError(
        f"tests/conftest.py not found in sys.modules — expected it loaded before "
        f"{__file__} (pytest loads parent conftests first)"
    )


reclaim_tmp_path_contents = _root_conftest_helper("reclaim_tmp_path_contents")


@pytest.fixture(autouse=True)
def _perf_test_auth_all_testclients(monkeypatch):
    """Preserve bootstrap auth when unit collection enabled shared middleware."""
    from starlette.testclient import TestClient

    token_header = f"Bearer {initialize_token()}"
    original_request = TestClient.request

    def _request_with_default_auth(self, *args, **kwargs):
        self.headers.setdefault("Authorization", token_header)
        return original_request(self, *args, **kwargs)

    monkeypatch.setattr(TestClient, "request", _request_with_default_auth)
    yield


@pytest.fixture(autouse=True)
def _reclaim_seeded_library_disk(tmp_path):
    """Bound the perf suite's LIVE disk footprint (#4434 follow-up).

    Each perf test seeds a full library (images, DuckDB, LanceDB vectors)
    under its own ``tmp_path`` via the shared ``test_package``/``app_db``
    fixtures — nothing frees that content until session end otherwise (14 GB
    held simultaneously by already-passed tests, observed 2026-08-01). See
    ``reclaim_tmp_path_contents`` in ``tests/conftest.py`` for why this
    empties the directory's contents rather than removing it outright (a
    full removal recycles pytest's numbered directory name and hands a later
    test a stale path-keyed cache entry — the e767147e5 incident).

    Requesting only ``tmp_path`` (not ``client``/``db``/``test_package``)
    keeps this autouse fixture's setup EARLY relative to the test's own
    fixtures, so per pytest's LIFO teardown order it runs LAST — after
    ``test_package``'s ``db_manager.close_all()`` and ``app_db``'s
    ``db.close()`` have already released every connection into this
    directory.
    """
    yield
    reclaim_tmp_path_contents(tmp_path)
